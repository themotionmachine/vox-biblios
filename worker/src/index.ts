import { Hono, type Context } from "hono";
import { loginHandler, requireAuth } from "./auth";
import {
  claimNextQueueItem,
  completeQueueItem,
  createFeed,
  deleteEpisode,
  deleteEpisodesForItem,
  deleteFeed,
  deleteQueueItem,
  failQueueItem,
  getDefaultFeed,
  getEpisode,
  getFeedBySlug,
  getQueueItem,
  getStats,
  insertEpisode,
  insertQueueItem,
  listEpisodes,
  listFeeds,
  listQueueItems,
  markQueueItemPublished,
  resolveFeed,
  retryQueueItem,
  setQueueItemAudio,
  updateEpisode,
  updateFeed,
  DEFAULT_FEED_SLUG,
  type Episode,
  type Feed,
  type QueueStatus,
} from "./db";
import { decodeVoiceValue, parseVoiceSelection } from "./voices";
import { renderRss } from "./rss";
import { renderHome } from "./ui";

const MAX_TEXT_CHARS = 500_000;
const MAX_TITLE_CHARS = 500;
const MAX_DESC_CHARS = 10_000;
const MAX_AUDIO_BYTES = 300 * 1024 * 1024;
const AUDIO_PREFIX = "cp/episodes/";
const SLUG_RE = /^[a-z0-9-]+$/;

type AppEnv = { Bindings: Env };

const app = new Hono<AppEnv>();

app.onError((err, c) => {
  console.error(JSON.stringify({ message: "unhandled error", path: c.req.path, error: String(err) }));
  return c.json({ error: "internal error" }, 500);
});

app.notFound((c) => c.json({ error: "not found" }, 404));

// ---- public routes ----

app.get("/healthz", (c) => c.json({ ok: true }));

app.get("/login", loginHandler<AppEnv>());

async function feedResponse(c: Context<AppEnv>, feed: Feed) {
  const episodes = await listEpisodes(c.env.DB, feed.id);
  const feedUrl = new URL(c.req.path, c.req.url).toString();
  return c.body(renderRss(feed, episodes, { feedUrl, audioBase: c.env.PUBLIC_AUDIO_BASE }), 200, {
    "Content-Type": "application/rss+xml; charset=utf-8",
    "Cache-Control": "public, max-age=300",
  });
}

// Default feed — kept stable so existing podcast subscriptions never break.
app.get("/feed.xml", async (c) => {
  const feed = await getDefaultFeed(c.env.DB);
  if (!feed) return c.json({ error: "no feed configured" }, 404);
  return feedResponse(c, feed);
});

// Per-feed RSS: /feed/<slug>.xml. (Match /feed/<file> then strip .xml to avoid
// Hono's dot-in-param ambiguity; /feed.xml above is a distinct, dotless path.)
app.get("/feed/:file", async (c) => {
  const file = c.req.param("file");
  if (!file.endsWith(".xml")) return c.json({ error: "not found" }, 404);
  const feed = await getFeedBySlug(c.env.DB, file.slice(0, -4));
  if (!feed) return c.json({ error: "feed not found" }, 404);
  return feedResponse(c, feed);
});

// ---- everything below requires auth (Access JWT, bearer API_TOKEN, or login cookie) ----

const auth = requireAuth<AppEnv>();
app.use("/api/*", auth);

app.get("/", auth, async (c) => {
  const selected = await resolveFeed(c.env.DB, c.req.query("feed"));
  if (!selected) return c.json({ error: "no feed configured" }, 404);
  const [feeds, queue, episodes, stats] = await Promise.all([
    listFeeds(c.env.DB),
    listQueueItems(c.env.DB, null, 50, selected.id),
    listEpisodes(c.env.DB, selected.id, 50),
    getStats(c.env.DB),
  ]);
  return c.html(renderHome(feeds, selected, queue, episodes, stats, c.env.PUBLIC_AUDIO_BASE));
});

app.get("/api/stats", async (c) => {
  return c.json(await getStats(c.env.DB));
});

// ---- submission API ----

interface SubmitBody {
  url?: string;
  text?: string;
  title?: string;
  feed?: string;
  // Per-submission voice override (raw); validated in the handler. Both absent
  // means "inherit the feed default". The form posts a single "voice" field
  // ("provider:voice"); the JSON API takes explicit tts_provider/tts_voice.
  tts_provider?: string;
  tts_voice?: string;
}

const pickStr = (v: unknown) => (typeof v === "string" && v.trim() !== "" ? v.trim() : undefined);

async function parseSubmission(c: Context<AppEnv>): Promise<{ body: SubmitBody; isForm: boolean }> {
  const contentType = c.req.header("content-type") ?? "";
  if (contentType.includes("application/x-www-form-urlencoded") || contentType.includes("multipart/form-data")) {
    const form = await c.req.parseBody();
    const v = decodeVoiceValue(form["voice"]);
    return {
      body: {
        url: pickStr(form["url"]),
        text: pickStr(form["text"]),
        title: pickStr(form["title"]),
        feed: pickStr(form["feed"]),
        tts_provider: v.provider ?? undefined,
        tts_voice: v.voice ?? undefined,
      },
      isForm: true,
    };
  }
  const json = await c.req.json<SubmitBody>().catch(() => ({}) as SubmitBody);
  return {
    body: {
      url: pickStr(json.url),
      text: pickStr(json.text),
      title: pickStr(json.title),
      feed: pickStr(json.feed),
      tts_provider: pickStr(json.tts_provider),
      tts_voice: pickStr(json.tts_voice),
    },
    isForm: false,
  };
}

app.post("/api/queue", async (c) => {
  const { body, isForm } = await parseSubmission(c);

  if ((body.url ? 1 : 0) + (body.text ? 1 : 0) !== 1) {
    return c.json({ error: "provide exactly one of 'url' or 'text'" }, 400);
  }
  if (body.url) {
    let parsed: URL;
    try {
      parsed = new URL(body.url);
    } catch {
      return c.json({ error: "invalid url" }, 400);
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return c.json({ error: "url must be http(s)" }, 400);
    }
  }
  if (body.text && body.text.length > MAX_TEXT_CHARS) {
    return c.json({ error: `text exceeds ${MAX_TEXT_CHARS} characters` }, 400);
  }
  if (body.title && body.title.length > MAX_TITLE_CHARS) {
    return c.json({ error: `title exceeds ${MAX_TITLE_CHARS} characters` }, 400);
  }

  const voice = parseVoiceSelection(body.tts_provider, body.tts_voice);
  if (!voice.ok) return c.json({ error: voice.error }, 400);

  const feed = await resolveFeed(c.env.DB, body.feed);
  if (!feed) {
    return body.feed
      ? c.json({ error: `unknown feed '${body.feed}'` }, 400)
      : c.json({ error: "no feed configured" }, 500);
  }

  const id = crypto.randomUUID();
  await insertQueueItem(c.env.DB, {
    id,
    feed_id: feed.id,
    kind: body.url ? "url" : "text",
    payload: body.url ?? body.text ?? "",
    title: body.title ?? null,
    tts_provider: voice.value.provider,
    tts_voice: voice.value.voice,
  });

  if (isForm) return c.redirect(`/?feed=${encodeURIComponent(feed.slug)}`, 303);
  return c.json({ id, status: "queued" }, 201);
});

app.get("/api/queue", async (c) => {
  const statusParam = c.req.query("status") ?? null;
  const valid: QueueStatus[] = ["queued", "synthesizing", "published", "failed"];
  if (statusParam !== null && !valid.includes(statusParam as QueueStatus)) {
    return c.json({ error: `status must be one of ${valid.join(", ")}` }, 400);
  }
  const limit = Math.min(Number(c.req.query("limit") ?? 50) || 50, 200);
  const feedSlug = c.req.query("feed");
  let feedId: number | null = null;
  if (feedSlug) {
    const f = await getFeedBySlug(c.env.DB, feedSlug);
    if (!f) return c.json({ error: `unknown feed '${feedSlug}'` }, 400);
    feedId = f.id;
  }
  const items = await listQueueItems(c.env.DB, statusParam as QueueStatus | null, limit, feedId);
  return c.json({ items });
});

app.get("/api/queue/:id", async (c) => {
  const item = await getQueueItem(c.env.DB, c.req.param("id"));
  if (!item) return c.json({ error: "not found" }, 404);
  return c.json(item);
});

app.post("/api/queue/:id/retry", async (c) => {
  const ok = await retryQueueItem(c.env.DB, c.req.param("id"));
  if (!ok) return c.json({ error: "item not found or not in 'failed' state" }, 409);
  const contentType = c.req.header("content-type") ?? "";
  if (contentType.includes("form")) return c.redirect("/", 303);
  return c.json({ id: c.req.param("id"), status: "queued" });
});

app.delete("/api/queue/:id", async (c) => {
  const ok = await deleteQueueItem(c.env.DB, c.req.param("id"));
  if (!ok) return c.json({ error: "item not found or not deletable (only queued/failed)" }, 409);
  return c.json({ deleted: c.req.param("id") });
});

app.get("/api/episodes", async (c) => {
  const feedSlug = c.req.query("feed");
  const feed = await resolveFeed(c.env.DB, feedSlug);
  if (!feed) {
    return feedSlug
      ? c.json({ error: `unknown feed '${feedSlug}'` }, 400)
      : c.json({ error: "no feed configured" }, 500);
  }
  const limit = Math.min(Number(c.req.query("limit") ?? 100) || 100, 500);
  const episodes = await listEpisodes(c.env.DB, feed.id, limit);
  return c.json({ episodes });
});

// ---- feed management ----

interface FeedBody {
  slug?: string;
  title?: string;
  description?: string;
  link?: string;
  author?: string;
  image_url?: string;
  language?: string;
  explicit?: boolean;
  // Default voice (raw). undefined = leave unchanged on edit; null = clear to
  // the host default; string = set. provider and voice are validated together.
  tts_provider?: string | null;
  tts_voice?: string | null;
}

async function parseFeedBody(c: Context<AppEnv>): Promise<{ body: FeedBody; isForm: boolean }> {
  const contentType = c.req.header("content-type") ?? "";
  if (contentType.includes("application/x-www-form-urlencoded") || contentType.includes("multipart/form-data")) {
    const form = await c.req.parseBody();
    // The form always carries the voice <select>, so "" means "clear to default".
    const v = decodeVoiceValue(form["voice"]);
    return {
      body: {
        slug: pickStr(form["slug"]),
        title: pickStr(form["title"]),
        description: pickStr(form["description"]),
        link: pickStr(form["link"]),
        author: pickStr(form["author"]),
        image_url: pickStr(form["image_url"]),
        language: pickStr(form["language"]),
        explicit: form["explicit"] !== undefined && form["explicit"] !== "",
        tts_provider: v.provider,
        tts_voice: v.voice,
      },
      isForm: true,
    };
  }
  const j = await c.req.json<FeedBody>().catch(() => ({}) as FeedBody);
  // For JSON, an omitted key stays undefined (unchanged); a present key (incl.
  // empty/null) becomes null to clear, or its trimmed value to set.
  const jsonVoice = (key: "tts_provider" | "tts_voice"): string | null | undefined =>
    key in j ? pickStr(j[key]) ?? null : undefined;
  return {
    body: {
      slug: pickStr(j.slug),
      title: pickStr(j.title),
      description: pickStr(j.description),
      link: pickStr(j.link),
      author: pickStr(j.author),
      image_url: pickStr(j.image_url),
      language: pickStr(j.language),
      explicit: typeof j.explicit === "boolean" ? j.explicit : undefined,
      tts_provider: jsonVoice("tts_provider"),
      tts_voice: jsonVoice("tts_voice"),
    },
    isForm: false,
  };
}

/**
 * Validate a feed body's voice fields into a tri-state for create/update:
 *   - { provider, voice }  both set, both null (cleared), or both undefined
 *   - throws via the returned error when half-set or an unknown pair.
 * undefined survives only when BOTH are undefined (JSON edit left them alone).
 */
function resolveFeedVoice(
  body: FeedBody,
): { ok: true; provider: string | null | undefined; voice: string | null | undefined } | { ok: false; error: string } {
  if (body.tts_provider === undefined && body.tts_voice === undefined) {
    return { ok: true, provider: undefined, voice: undefined };
  }
  const sel = parseVoiceSelection(body.tts_provider ?? undefined, body.tts_voice ?? undefined);
  if (!sel.ok) return sel;
  return { ok: true, provider: sel.value.provider, voice: sel.value.voice };
}

app.get("/api/feeds", async (c) => {
  return c.json({ feeds: await listFeeds(c.env.DB) });
});

app.post("/api/feeds", async (c) => {
  const { body, isForm } = await parseFeedBody(c);
  const slug = body.slug;
  const title = body.title;
  if (!slug || !SLUG_RE.test(slug)) {
    return c.json({ error: "slug is required and must match ^[a-z0-9-]+$" }, 400);
  }
  if (!title) return c.json({ error: "title is required" }, 400);
  const voice = resolveFeedVoice(body);
  if (!voice.ok) return c.json({ error: voice.error }, 400);
  if (await getFeedBySlug(c.env.DB, slug)) {
    return c.json({ error: `feed '${slug}' already exists` }, 409);
  }
  const feed = await createFeed(c.env.DB, {
    slug,
    title,
    description: body.description,
    link: body.link,
    author: body.author,
    image_url: body.image_url,
    language: body.language,
    explicit: body.explicit,
    tts_provider: voice.provider ?? null,
    tts_voice: voice.voice ?? null,
  });
  if (isForm) return c.redirect(`/?feed=${encodeURIComponent(slug)}`, 303);
  return c.json({ feed }, 201);
});

async function editFeed(c: Context<AppEnv>) {
  const slug = c.req.param("slug");
  if (!slug) return c.json({ error: "invalid feed slug" }, 400);
  if (!(await getFeedBySlug(c.env.DB, slug))) return c.json({ error: "feed not found" }, 404);
  const { body, isForm } = await parseFeedBody(c);
  const voice = resolveFeedVoice(body);
  if (!voice.ok) return c.json({ error: voice.error }, 400);
  const feed = await updateFeed(c.env.DB, slug, {
    title: body.title,
    description: body.description,
    link: body.link,
    author: body.author,
    image_url: body.image_url,
    language: body.language,
    explicit: body.explicit,
    tts_provider: voice.provider,
    tts_voice: voice.voice,
  });
  if (isForm) return c.redirect(`/?feed=${encodeURIComponent(slug)}`, 303);
  return c.json({ feed });
}
app.post("/api/feeds/:slug", editFeed);
app.patch("/api/feeds/:slug", editFeed);

async function removeFeed(c: Context<AppEnv>, slug: string, force: boolean) {
  if (slug === DEFAULT_FEED_SLUG) return { code: 409, error: "cannot delete the default feed" };
  const result = await deleteFeed(c.env.DB, slug, { force });
  if (result === null) return { code: 404, error: "feed not found" };
  if (result === "not-empty") {
    return { code: 409, error: "feed has episodes/queue items; retry with ?force=1 to delete them too" };
  }
  for (const key of result.audio_keys) {
    try {
      await c.env.AUDIO.delete(key);
    } catch (err) {
      console.error(JSON.stringify({ message: "r2 delete failed", key, error: String(err) }));
    }
  }
  return { code: 200, deleted: slug, episodes_removed: result.audio_keys.length };
}

app.post("/api/feeds/:slug/delete", async (c) => {
  // UI delete cascades (the form's confirm dialog is the guard).
  const r = await removeFeed(c, c.req.param("slug"), true);
  if (r.code !== 200) return c.json({ error: r.error }, r.code as 404 | 409);
  return c.redirect("/", 303);
});

app.delete("/api/feeds/:slug", async (c) => {
  const r = await removeFeed(c, c.req.param("slug"), c.req.query("force") === "1");
  if (r.code !== 200) return c.json({ error: r.error }, r.code as 404 | 409);
  return c.json({ deleted: r.deleted, episodes_removed: r.episodes_removed });
});

// ---- episode edit / delete ----

interface EditBody {
  title?: string;
  description?: string;
  published_at?: string;
}

/** Normalize a datetime to D1's 'YYYY-MM-DD HH:MM:SS' (UTC), or null if invalid. */
function normalizeDatetime(s: string): string | null {
  const t = s.trim().replace("T", " ");
  const m = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})(:\d{2})?$/.exec(t);
  if (!m) return null;
  const normalized = m[2] ? t : `${t}:00`;
  if (Number.isNaN(Date.parse(normalized.replace(" ", "T") + "Z"))) return null;
  return normalized;
}

async function parseEdit(c: Context<AppEnv>): Promise<{ body: EditBody; isForm: boolean }> {
  const pick = (v: unknown) => (typeof v === "string" ? v.trim() : undefined);
  const contentType = c.req.header("content-type") ?? "";
  if (contentType.includes("application/x-www-form-urlencoded") || contentType.includes("multipart/form-data")) {
    const form = await c.req.parseBody();
    return {
      body: { title: pick(form["title"]), description: pick(form["description"]), published_at: pick(form["published_at"]) },
      isForm: true,
    };
  }
  const json = await c.req.json<EditBody>().catch(() => ({}) as EditBody);
  return {
    body: { title: pick(json.title), description: pick(json.description), published_at: pick(json.published_at) },
    isForm: false,
  };
}

app.post("/api/episodes/:id", async (c) => {
  const id = Number(c.req.param("id"));
  if (!Number.isInteger(id)) return c.json({ error: "invalid episode id" }, 400);

  const existing = await getEpisode(c.env.DB, id);
  if (!existing) return c.json({ error: "not found" }, 404);

  const { body, isForm } = await parseEdit(c);
  const title = body.title ?? existing.title;
  const description = body.description ?? existing.description;
  if (!title) return c.json({ error: "title cannot be empty" }, 400);
  if (title.length > MAX_TITLE_CHARS) return c.json({ error: `title exceeds ${MAX_TITLE_CHARS} characters` }, 400);
  if (description.length > MAX_DESC_CHARS) {
    return c.json({ error: `description exceeds ${MAX_DESC_CHARS} characters` }, 400);
  }
  let published_at: string | undefined;
  if (body.published_at) {
    const norm = normalizeDatetime(body.published_at);
    if (!norm) return c.json({ error: "published_at must be 'YYYY-MM-DD HH:MM(:SS)' (UTC)" }, 400);
    published_at = norm;
  }

  const episode = await updateEpisode(c.env.DB, id, { title, description, published_at });
  if (isForm) return c.redirect("/", 303);
  return c.json({ episode });
});

async function removeEpisode(c: Context<AppEnv>, id: number): Promise<boolean> {
  const deleted = await deleteEpisode(c.env.DB, id);
  if (!deleted) return false;
  // Best-effort R2 cleanup: a failed object delete must not strand the DB row,
  // which is already gone. Log and move on so the episode can't reappear.
  try {
    await c.env.AUDIO.delete(deleted.audio_key);
  } catch (err) {
    console.error(JSON.stringify({ message: "r2 delete failed", key: deleted.audio_key, error: String(err) }));
  }
  return true;
}

app.post("/api/episodes/:id/delete", async (c) => {
  const id = Number(c.req.param("id"));
  if (!Number.isInteger(id)) return c.json({ error: "invalid episode id" }, 400);
  const ok = await removeEpisode(c, id);
  if (!ok) return c.json({ error: "not found" }, 404);
  return c.redirect("/", 303);
});

app.delete("/api/episodes/:id", async (c) => {
  const id = Number(c.req.param("id"));
  if (!Number.isInteger(id)) return c.json({ error: "invalid episode id" }, 400);
  const ok = await removeEpisode(c, id);
  if (!ok) return c.json({ error: "not found" }, 404);
  return c.json({ deleted: id });
});

// ---- synthesis worker (poller) API ----

app.post("/api/worker/claim", async (c) => {
  const item = await claimNextQueueItem(c.env.DB);
  if (!item) return c.body(null, 204);
  return c.json(item);
});

app.put("/api/worker/items/:id/audio", async (c) => {
  const id = c.req.param("id");
  const item = await getQueueItem(c.env.DB, id);
  if (!item) return c.json({ error: "not found" }, 404);
  if (item.status !== "synthesizing") {
    return c.json({ error: `item is '${item.status}', expected 'synthesizing'` }, 409);
  }
  const lengthHeader = c.req.header("content-length");
  if (!lengthHeader) return c.json({ error: "Content-Length required" }, 411);
  const length = Number(lengthHeader);
  if (!Number.isFinite(length) || length <= 0 || length > MAX_AUDIO_BYTES) {
    return c.json({ error: `Content-Length must be 1..${MAX_AUDIO_BYTES}` }, 413);
  }

  // Optional `?part=k` (k >= 0) stores audio for one part of a multi-part item
  // under a distinct key; the poller passes the returned key back in `complete`.
  // Without it, the legacy single-audio path stores `<id>.mp3` on the item.
  const partRaw = c.req.query("part");
  let key = `${AUDIO_PREFIX}${id}.mp3`;
  if (partRaw !== undefined) {
    const part = Number(partRaw);
    if (!Number.isInteger(part) || part < 0) {
      return c.json({ error: "part must be a non-negative integer" }, 400);
    }
    key = `${AUDIO_PREFIX}${id}-${part}.mp3`;
  }

  const stored = await c.env.AUDIO.put(key, c.req.raw.body, {
    httpMetadata: { contentType: "audio/mpeg" },
  });
  if (!stored) return c.json({ error: "upload failed" }, 500);

  // Only the legacy single-audio path records the key on the queue item; the
  // multi-part path tracks per-part keys in the `complete` request instead.
  if (partRaw === undefined) await setQueueItemAudio(c.env.DB, id, key, stored.size);
  return c.json({ audio_key: key, audio_bytes: stored.size });
});

// One part of a multi-part item: an already-uploaded audio key plus its metadata.
interface CompletePart {
  audio_key?: string;
  audio_bytes?: number;
  title?: string;
  description?: string;
  duration_secs?: number;
}

interface CompleteBody {
  title?: string;
  description?: string;
  duration_secs?: number;
  // The voice the poller actually synthesized with, recorded on the episode(s).
  tts_provider?: string;
  tts_voice?: string;
  // Multi-part articles: one entry per part. When present (and non-empty), each
  // becomes its own episode and the single-audio fields above are ignored.
  parts?: CompletePart[];
}

const cleanDuration = (v: unknown): number | null =>
  typeof v === "number" && v > 0 ? Math.round(v) : null;

app.post("/api/worker/items/:id/complete", async (c) => {
  const id = c.req.param("id");
  const item = await getQueueItem(c.env.DB, id);
  if (!item) return c.json({ error: "not found" }, 404);
  if (item.status !== "synthesizing") {
    return c.json({ error: `item is '${item.status}', expected 'synthesizing'` }, 409);
  }

  const body = await c.req.json<CompleteBody>().catch(() => ({}) as CompleteBody);
  const ttsProvider = pickStr(body.tts_provider) ?? null;
  const ttsVoice = pickStr(body.tts_voice) ?? null;
  const fallbackDescription = item.kind === "url" ? item.payload : "";

  // Multi-part path: one episode per uploaded part.
  if (Array.isArray(body.parts) && body.parts.length > 0) {
    for (const [i, part] of body.parts.entries()) {
      if (!pickStr(part.audio_key)) {
        return c.json({ error: `part ${i} is missing audio_key` }, 400);
      }
    }
    // Clear any episodes from a prior partial completion so this is idempotent.
    await deleteEpisodesForItem(c.env.DB, id);
    const episodes: Episode[] = [];
    for (const [i, part] of body.parts.entries()) {
      const ep = await insertEpisode(c.env.DB, {
        feed_id: item.feed_id,
        guid: `${id}-${i}`,
        title: pickStr(part.title) ?? item.title?.trim() ?? `Episode ${id.slice(0, 8)} part ${i + 1}`,
        description: pickStr(part.description) ?? fallbackDescription,
        audio_key: part.audio_key as string,
        audio_bytes: typeof part.audio_bytes === "number" && part.audio_bytes > 0 ? part.audio_bytes : 0,
        duration_secs: cleanDuration(part.duration_secs),
        tts_provider: ttsProvider,
        tts_voice: ttsVoice,
      });
      episodes.push(ep);
    }
    const last = episodes[episodes.length - 1];
    if (last) await markQueueItemPublished(c.env.DB, id, last.id);
    return c.json({ episodes, status: "published" }, 201);
  }

  // Legacy single-audio path.
  if (!item.audio_key) return c.json({ error: "no audio uploaded for this item" }, 409);
  const title = body.title?.trim() || item.title?.trim() || `Episode ${id.slice(0, 8)}`;
  const description = body.description?.trim() ?? fallbackDescription;
  const episode = await completeQueueItem(c.env.DB, item, {
    title,
    description,
    duration_secs: cleanDuration(body.duration_secs),
    tts_provider: ttsProvider,
    tts_voice: ttsVoice,
  });
  return c.json({ episode, status: "published" }, 201);
});

app.post("/api/worker/items/:id/fail", async (c) => {
  const id = c.req.param("id");
  const body = await c.req.json<{ error?: unknown }>().catch(() => ({}) as { error?: unknown });
  const message =
    typeof body.error === "string" ? body.error : body.error != null ? JSON.stringify(body.error) : "unknown error";
  const ok = await failQueueItem(c.env.DB, id, message.slice(0, 10_000));
  if (!ok) return c.json({ error: "item not found or not in 'synthesizing' state" }, 409);
  return c.json({ id, status: "failed" });
});

export default app;
