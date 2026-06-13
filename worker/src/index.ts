import { Hono, type Context } from "hono";
import { loginHandler, requireAuth } from "./auth";
import {
  claimNextQueueItem,
  completeQueueItem,
  deleteQueueItem,
  failQueueItem,
  getDefaultFeed,
  getQueueItem,
  insertQueueItem,
  listEpisodes,
  listQueueItems,
  retryQueueItem,
  setQueueItemAudio,
  type QueueStatus,
} from "./db";
import { renderRss } from "./rss";
import { renderHome } from "./ui";

const MAX_TEXT_CHARS = 500_000;
const MAX_TITLE_CHARS = 500;
const MAX_AUDIO_BYTES = 300 * 1024 * 1024;
const AUDIO_PREFIX = "cp/episodes/";

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

app.get("/feed.xml", async (c) => {
  const feed = await getDefaultFeed(c.env.DB);
  if (!feed) return c.json({ error: "no feed configured" }, 404);
  const episodes = await listEpisodes(c.env.DB, feed.id);
  const feedUrl = new URL("/feed.xml", c.req.url).toString();
  return c.body(renderRss(feed, episodes, { feedUrl, audioBase: c.env.PUBLIC_AUDIO_BASE }), 200, {
    "Content-Type": "application/rss+xml; charset=utf-8",
    "Cache-Control": "public, max-age=300",
  });
});

// ---- everything below requires auth (Access JWT, bearer API_TOKEN, or login cookie) ----

const auth = requireAuth<AppEnv>();
app.use("/api/*", auth);

app.get("/", auth, async (c) => {
  const feed = await getDefaultFeed(c.env.DB);
  if (!feed) return c.json({ error: "no feed configured" }, 404);
  const [queue, episodes] = await Promise.all([
    listQueueItems(c.env.DB, null, 50),
    listEpisodes(c.env.DB, feed.id, 50),
  ]);
  return c.html(renderHome(feed, queue, episodes, c.env.PUBLIC_AUDIO_BASE));
});

// ---- submission API ----

interface SubmitBody {
  url?: string;
  text?: string;
  title?: string;
}

async function parseSubmission(c: Context<AppEnv>): Promise<{ body: SubmitBody; isForm: boolean }> {
  const contentType = c.req.header("content-type") ?? "";
  if (contentType.includes("application/x-www-form-urlencoded") || contentType.includes("multipart/form-data")) {
    const form = await c.req.parseBody();
    const pick = (v: unknown) => (typeof v === "string" && v.trim() !== "" ? v.trim() : undefined);
    return { body: { url: pick(form["url"]), text: pick(form["text"]), title: pick(form["title"]) }, isForm: true };
  }
  const json = await c.req.json<SubmitBody>().catch(() => ({}) as SubmitBody);
  const pick = (v: unknown) => (typeof v === "string" && v.trim() !== "" ? v.trim() : undefined);
  return { body: { url: pick(json.url), text: pick(json.text), title: pick(json.title) }, isForm: false };
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

  const feed = await getDefaultFeed(c.env.DB);
  if (!feed) return c.json({ error: "no feed configured" }, 500);

  const id = crypto.randomUUID();
  await insertQueueItem(c.env.DB, {
    id,
    feed_id: feed.id,
    kind: body.url ? "url" : "text",
    payload: body.url ?? body.text ?? "",
    title: body.title ?? null,
  });

  if (isForm) return c.redirect("/", 303);
  return c.json({ id, status: "queued" }, 201);
});

app.get("/api/queue", async (c) => {
  const statusParam = c.req.query("status") ?? null;
  const valid: QueueStatus[] = ["queued", "synthesizing", "published", "failed"];
  if (statusParam !== null && !valid.includes(statusParam as QueueStatus)) {
    return c.json({ error: `status must be one of ${valid.join(", ")}` }, 400);
  }
  const limit = Math.min(Number(c.req.query("limit") ?? 50) || 50, 200);
  const items = await listQueueItems(c.env.DB, statusParam as QueueStatus | null, limit);
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
  const feed = await getDefaultFeed(c.env.DB);
  if (!feed) return c.json({ error: "no feed configured" }, 500);
  const limit = Math.min(Number(c.req.query("limit") ?? 100) || 100, 500);
  const episodes = await listEpisodes(c.env.DB, feed.id, limit);
  return c.json({ episodes });
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

  const key = `${AUDIO_PREFIX}${id}.mp3`;
  const stored = await c.env.AUDIO.put(key, c.req.raw.body, {
    httpMetadata: { contentType: "audio/mpeg" },
  });
  if (!stored) return c.json({ error: "upload failed" }, 500);

  await setQueueItemAudio(c.env.DB, id, key, stored.size);
  return c.json({ audio_key: key, audio_bytes: stored.size });
});

interface CompleteBody {
  title?: string;
  description?: string;
  duration_secs?: number;
}

app.post("/api/worker/items/:id/complete", async (c) => {
  const id = c.req.param("id");
  const item = await getQueueItem(c.env.DB, id);
  if (!item) return c.json({ error: "not found" }, 404);
  if (item.status !== "synthesizing") {
    return c.json({ error: `item is '${item.status}', expected 'synthesizing'` }, 409);
  }
  if (!item.audio_key) return c.json({ error: "no audio uploaded for this item" }, 409);

  const body = await c.req.json<CompleteBody>().catch(() => ({}) as CompleteBody);
  const title = body.title?.trim() || item.title?.trim() || `Episode ${id.slice(0, 8)}`;
  const description = body.description?.trim() ?? (item.kind === "url" ? item.payload : "");
  const duration = typeof body.duration_secs === "number" && body.duration_secs > 0 ? Math.round(body.duration_secs) : null;

  const episode = await completeQueueItem(c.env.DB, item, { title, description, duration_secs: duration });
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
