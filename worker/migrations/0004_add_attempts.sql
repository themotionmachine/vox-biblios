-- Migration number: 0004 	 retry cap: bound synthesis attempts per queue item
--
-- Each claim of a queue item increments `attempts`. A stale `synthesizing` item
-- that has reached the cap is retired to `failed` instead of being re-claimed,
-- so a permanently-failing item (e.g. one whose audio can't be uploaded) can no
-- longer loop forever re-synthesizing. Existing rows start at 0.

ALTER TABLE queue_items ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
