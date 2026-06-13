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

export async function getDefaultFeed(db: D1Database): Promise<Feed | null> {
  return db.prepare("SELECT * FROM feeds ORDER BY id LIMIT 1").first<Feed>();
}

export async function listEpisodes(db: D1Database, feedId: number, limit = 100): Promise<Episode[]> {
  const { results } = await db
    .prepare("SELECT * FROM episodes WHERE feed_id = ? ORDER BY published_at DESC, id DESC LIMIT ?")
    .bind(feedId, limit)
    .all<Episode>();
  return results;
}

export async function listQueueItems(
  db: D1Database,
  status: QueueStatus | null,
  limit = 50,
): Promise<QueueItem[]> {
  const stmt = status
    ? db.prepare("SELECT * FROM queue_items WHERE status = ? ORDER BY created_at DESC LIMIT ?").bind(status, limit)
    : db.prepare("SELECT * FROM queue_items ORDER BY created_at DESC LIMIT ?").bind(limit);
  const { results } = await stmt.all<QueueItem>();
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
