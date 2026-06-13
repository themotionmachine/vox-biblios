-- Migration number: 0001 	 init
CREATE TABLE feeds (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en',
    explicit INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    feed_id INTEGER NOT NULL REFERENCES feeds(id),
    guid TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    audio_key TEXT NOT NULL,
    audio_bytes INTEGER NOT NULL DEFAULT 0,
    duration_secs INTEGER,
    published_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_episodes_feed ON episodes(feed_id, published_at DESC);

CREATE TABLE queue_items (
    id TEXT PRIMARY KEY,
    feed_id INTEGER NOT NULL REFERENCES feeds(id),
    kind TEXT NOT NULL CHECK (kind IN ('url', 'text')),
    payload TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'synthesizing', 'published', 'failed')),
    error TEXT,
    episode_id INTEGER REFERENCES episodes(id),
    audio_key TEXT,
    audio_bytes INTEGER,
    claimed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_queue_status ON queue_items(status, created_at);
