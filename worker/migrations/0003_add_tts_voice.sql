-- Migration number: 0003 	 add per-feed default voice + per-submission override
--
-- A feed may pin a default (tts_provider, tts_voice); NULL means "fall back to
-- the synthesis host's global default" (POCKET_TTS / config.env). A queue item
-- may override the feed default for one submission; NULL means "inherit the
-- feed default". Episodes record what was actually used, for audit/display.
-- Voice names are provider-specific, so provider and voice always travel
-- together (both set, or both NULL).

ALTER TABLE feeds ADD COLUMN tts_provider TEXT;
ALTER TABLE feeds ADD COLUMN tts_voice TEXT;

ALTER TABLE queue_items ADD COLUMN tts_provider TEXT;
ALTER TABLE queue_items ADD COLUMN tts_voice TEXT;

ALTER TABLE episodes ADD COLUMN tts_provider TEXT;
ALTER TABLE episodes ADD COLUMN tts_voice TEXT;
