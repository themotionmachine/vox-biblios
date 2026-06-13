export interface Feed {
  id: number;
  slug: string;
  title: string;
  description: string;
  link: string;
  author: string;
  image_url: string;
  language: string;
  explicit: number;
  created_at: string;
}

export interface Episode {
  id: number;
  feed_id: number;
  guid: string;
  title: string;
  description: string;
  audio_key: string;
  audio_bytes: number;
  duration_secs: number | null;
  published_at: string;
  created_at: string;
}

export type QueueStatus = "queued" | "synthesizing" | "published" | "failed";

export interface QueueItem {
  id: string;
  feed_id: number;
  kind: "url" | "text";
  payload: string;
  title: string | null;
  status: QueueStatus;
  error: string | null;
  episode_id: number | null;
  audio_key: string | null;
  audio_bytes: number | null;
  claimed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Slug of the feed that backs /feed.xml and feed-less submissions. */
export const DEFAULT_FEED_SLUG = "vox-biblios";

export async function getFeedBySlug(db: D1Database, slug: string): Promise<Feed | null> {
  return db.prepare("SELECT * FROM feeds WHERE slug = ?").bind(slug).first<Feed>();
}

export async function listFeeds(db: D1Database): Promise<Feed[]> {
  const { results } = await db.prepare("SELECT * FROM feeds ORDER BY id").all<Feed>();
  return results;
}

export async function getDefaultFeed(db: D1Database): Promise<Feed | null> {
  return (
    (await getFeedBySlug(db, DEFAULT_FEED_SLUG)) ??
    (await db.prepare("SELECT * FROM feeds ORDER BY id LIMIT 1").first<Feed>())
  );
}

/** Resolve a feed from an optional slug; falls back to the default feed. */
export async function resolveFeed(db: D1Database, slug?: string | null): Promise<Feed | null> {
  return slug ? getFeedBySlug(db, slug) : getDefaultFeed(db);
}

export interface FeedInput {
  slug: string;
  title: string;
  description?: string;
  link?: string;
  author?: string;
  image_url?: string;
  language?: string;
  explicit?: boolean;
}

export async function createFeed(db: D1Database, f: FeedInput): Promise<Feed | null> {
  return db
    .prepare(
      `INSERT INTO feeds (slug, title, description, link, author, image_url, language, explicit)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING *`,
    )
    .bind(
      f.slug,
      f.title,
      f.description ?? "",
      f.link ?? "",
      f.author ?? "",
      f.image_url ?? "",
      f.language ?? "en",
      f.explicit ? 1 : 0,
    )
    .first<Feed>();
}

export async function updateFeed(
  db: D1Database,
  slug: string,
  fields: Partial<Omit<FeedInput, "slug">>,
): Promise<Feed | null> {
  const map: Record<string, string | number | undefined> = {
    title: fields.title,
    description: fields.description,
    link: fields.link,
    author: fields.author,
    image_url: fields.image_url,
    language: fields.language,
    explicit: fields.explicit === undefined ? undefined : fields.explicit ? 1 : 0,
  };
  const cols: string[] = [];
  const binds: (string | number)[] = [];
  for (const [k, v] of Object.entries(map)) {
    if (v !== undefined) {
      cols.push(`${k} = ?`);
      binds.push(v);
    }
  }
  if (cols.length === 0) return getFeedBySlug(db, slug);
  return db
    .prepare(`UPDATE feeds SET ${cols.join(", ")} WHERE slug = ? RETURNING *`)
    .bind(...binds, slug)
    .first<Feed>();
}

/**
 * Delete a feed. Refuses (returns "not-empty") if it still has episodes or queue
 * items unless `force`. With force, deletes in FK-safe order (queue_items →
 * episodes → feeds) and returns the episodes' audio_keys for R2 cleanup. Returns
 * null if no such feed.
 */
export async function deleteFeed(
  db: D1Database,
  slug: string,
  opts: { force: boolean },
): Promise<{ audio_keys: string[] } | "not-empty" | null> {
  const feed = await getFeedBySlug(db, slug);
  if (!feed) return null;
  const { results: eps } = await db
    .prepare("SELECT audio_key FROM episodes WHERE feed_id = ?")
    .bind(feed.id)
    .all<{ audio_key: string }>();
  const queued = await db
    .prepare("SELECT COUNT(*) AS n FROM queue_items WHERE feed_id = ?")
    .bind(feed.id)
    .first<{ n: number }>();
  if ((eps.length > 0 || (queued?.n ?? 0) > 0) && !opts.force) return "not-empty";
  await db.batch([
    db.prepare("DELETE FROM queue_items WHERE feed_id = ?").bind(feed.id),
    db.prepare("DELETE FROM episodes WHERE feed_id = ?").bind(feed.id),
    db.prepare("DELETE FROM feeds WHERE id = ?").bind(feed.id),
  ]);
  return { audio_keys: eps.map((e) => e.audio_key) };
}

export async function listEpisodes(db: D1Database, feedId: number, limit = 100): Promise<Episode[]> {
  const { results } = await db
    .prepare("SELECT * FROM episodes WHERE feed_id = ? ORDER BY published_at DESC, id DESC LIMIT ?")
    .bind(feedId, limit)
    .all<Episode>();
  return results;
}

export async function getEpisode(db: D1Database, id: number): Promise<Episode | null> {
  return db.prepare("SELECT * FROM episodes WHERE id = ?").bind(id).first<Episode>();
}

export async function updateEpisode(
  db: D1Database,
  id: number,
  meta: { title: string; description: string; published_at?: string },
): Promise<Episode | null> {
  // published_at is the only ordering signal podcast clients honor, so editing it
  // is how an episode is "reordered" in the feed.
  if (meta.published_at !== undefined) {
    return db
      .prepare(`UPDATE episodes SET title = ?, description = ?, published_at = ? WHERE id = ? RETURNING *`)
      .bind(meta.title, meta.description, meta.published_at, id)
      .first<Episode>();
  }
  return db
    .prepare(`UPDATE episodes SET title = ?, description = ? WHERE id = ? RETURNING *`)
    .bind(meta.title, meta.description, id)
    .first<Episode>();
}

export interface Stats {
  feeds: number;
  episodes: number;
  by_status: Record<QueueStatus, number>;
  stale_synthesizing: number;
  last_published_at: string | null;
  oldest_queued_at: string | null;
}

/** At-a-glance health, derived entirely from D1 (no poller changes needed). */
export async function getStats(db: D1Database): Promise<Stats> {
  const by_status: Record<QueueStatus, number> = { queued: 0, synthesizing: 0, published: 0, failed: 0 };
  const r = await db.batch<{ v: number | string | null }>([
    db.prepare("SELECT status, COUNT(*) AS v FROM queue_items GROUP BY status"),
    db.prepare("SELECT COUNT(*) AS v FROM feeds"),
    db.prepare("SELECT COUNT(*) AS v FROM episodes"),
    db.prepare("SELECT COUNT(*) AS v FROM queue_items WHERE status = 'synthesizing' AND claimed_at < datetime('now', '-30 minutes')"),
    db.prepare("SELECT MAX(published_at) AS v FROM episodes"),
    db.prepare("SELECT MIN(created_at) AS v FROM queue_items WHERE status = 'queued'"),
  ]);
  for (const row of (r[0]?.results ?? []) as Array<{ status: QueueStatus; v: number }>) {
    by_status[row.status] = row.v;
  }
  return {
    feeds: Number(r[1]?.results[0]?.v ?? 0),
    episodes: Number(r[2]?.results[0]?.v ?? 0),
    by_status,
    stale_synthesizing: Number(r[3]?.results[0]?.v ?? 0),
    last_published_at: (r[4]?.results[0]?.v as string | null) ?? null,
    oldest_queued_at: (r[5]?.results[0]?.v as string | null) ?? null,
  };
}

/**
 * Delete an episode and the queue item that produced it (its episode_id points
 * here), returning the R2 audio_key so the caller can remove the object. The two
 * deletes run as one batch so the feed and queue can't diverge. The queue row is
 * dropped first because queue_items.episode_id REFERENCES episodes(id) and D1
 * enforces foreign keys — deleting the episode while the row still points at it
 * would fail. Returns null if no episode matched.
 */
export async function deleteEpisode(
  db: D1Database,
  id: number,
): Promise<{ audio_key: string } | null> {
  const results = await db.batch<{ audio_key: string }>([
    db.prepare("DELETE FROM queue_items WHERE episode_id = ?").bind(id),
    db.prepare("DELETE FROM episodes WHERE id = ? RETURNING audio_key").bind(id),
  ]);
  const row = results[1]?.results[0];
  return row ? { audio_key: row.audio_key } : null;
}

export async function listQueueItems(
  db: D1Database,
  status: QueueStatus | null,
  limit = 50,
  feedId?: number | null,
): Promise<QueueItem[]> {
  const where: string[] = [];
  const binds: (string | number)[] = [];
  if (status) {
    where.push("status = ?");
    binds.push(status);
  }
  if (feedId != null) {
    where.push("feed_id = ?");
    binds.push(feedId);
  }
  const clause = where.length ? `WHERE ${where.join(" AND ")} ` : "";
  const { results } = await db
    .prepare(`SELECT * FROM queue_items ${clause}ORDER BY created_at DESC LIMIT ?`)
    .bind(...binds, limit)
    .all<QueueItem>();
  return results;
}

export async function getQueueItem(db: D1Database, id: string): Promise<QueueItem | null> {
  return db.prepare("SELECT * FROM queue_items WHERE id = ?").bind(id).first<QueueItem>();
}

export async function insertQueueItem(
  db: D1Database,
  item: { id: string; feed_id: number; kind: "url" | "text"; payload: string; title: string | null },
): Promise<void> {
  await db
    .prepare("INSERT INTO queue_items (id, feed_id, kind, payload, title) VALUES (?, ?, ?, ?, ?)")
    .bind(item.id, item.feed_id, item.kind, item.payload, item.title)
    .run();
}

/**
 * Atomically claim the next item of work: the oldest queued item, or a
 * synthesizing item whose claim is stale (poller died mid-episode).
 * Single UPDATE...RETURNING statement, so concurrent pollers cannot
 * claim the same item twice.
 */
export async function claimNextQueueItem(db: D1Database, staleMinutes = 30): Promise<QueueItem | null> {
  return db
    .prepare(
      `UPDATE queue_items
       SET status = 'synthesizing', claimed_at = datetime('now'), updated_at = datetime('now')
       WHERE id = (
         SELECT id FROM queue_items
         WHERE status = 'queued'
            OR (status = 'synthesizing' AND claimed_at < datetime('now', ?))
         ORDER BY created_at ASC
         LIMIT 1
       )
       RETURNING *`,
    )
    .bind(`-${staleMinutes} minutes`)
    .first<QueueItem>();
}

export async function setQueueItemAudio(
  db: D1Database,
  id: string,
  audioKey: string,
  audioBytes: number,
): Promise<void> {
  await db
    .prepare(
      "UPDATE queue_items SET audio_key = ?, audio_bytes = ?, updated_at = datetime('now') WHERE id = ?",
    )
    .bind(audioKey, audioBytes, id)
    .run();
}

export async function completeQueueItem(
  db: D1Database,
  item: QueueItem,
  meta: { title: string; description: string; duration_secs: number | null },
): Promise<Episode> {
  if (!item.audio_key) throw new Error("queue item has no uploaded audio");
  const episode = await db
    .prepare(
      `INSERT INTO episodes (feed_id, guid, title, description, audio_key, audio_bytes, duration_secs)
       VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *`,
    )
    .bind(
      item.feed_id,
      item.id,
      meta.title,
      meta.description,
      item.audio_key,
      item.audio_bytes ?? 0,
      meta.duration_secs,
    )
    .first<Episode>();
  if (!episode) throw new Error("episode insert returned no row");
  await db
    .prepare(
      `UPDATE queue_items
       SET status = 'published', episode_id = ?, error = NULL, updated_at = datetime('now')
       WHERE id = ?`,
    )
    .bind(episode.id, item.id)
    .run();
  return episode;
}

export async function failQueueItem(db: D1Database, id: string, error: string): Promise<boolean> {
  const row = await db
    .prepare(
      `UPDATE queue_items SET status = 'failed', error = ?, updated_at = datetime('now')
       WHERE id = ? AND status = 'synthesizing' RETURNING id`,
    )
    .bind(error, id)
    .first();
  return row !== null;
}

export async function retryQueueItem(db: D1Database, id: string): Promise<boolean> {
  const row = await db
    .prepare(
      `UPDATE queue_items
       SET status = 'queued', error = NULL, claimed_at = NULL, updated_at = datetime('now')
       WHERE id = ? AND status = 'failed' RETURNING id`,
    )
    .bind(id)
    .first();
  return row !== null;
}

export async function deleteQueueItem(db: D1Database, id: string): Promise<boolean> {
  const row = await db
    .prepare(
      "DELETE FROM queue_items WHERE id = ? AND status IN ('queued', 'failed') RETURNING id",
    )
    .bind(id)
    .first();
  return row !== null;
}
