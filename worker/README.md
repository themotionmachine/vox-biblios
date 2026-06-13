# Vox Biblios control plane

Cloudflare Worker (Hono + D1 + R2) implementing phase 2 of [#5](https://github.com/themotionmachine/vox-biblios/issues/5):
a submission queue, episode metadata in D1, and a server-rendered RSS feed at
`https://vb.activationlayer.org/feed.xml`. Synthesis still happens on the host
machine — a poller (phase 3) drives `vox-biblios process --json` against the
worker API below.

This directory is self-contained. The CLI (`vox_biblios/`) has **no**
dependency on it; CLI-only direct mode keeps working exactly as before.
A feed is either CLI-managed (RSS written by `podgen` to R2) or app-managed
(this Worker renders RSS from D1) — never both. The control plane writes audio
only under the `cp/` prefix of the shared `vox-biblios` bucket.

## Routes

Public (no auth):

| Route | Purpose |
|---|---|
| `GET /feed.xml` | RSS 2.0 + iTunes tags, rendered from D1 |
| `GET /healthz` | liveness |
| `GET /login?token=…` | sets an auth cookie for browser use before Cloudflare Access is configured |

Authenticated — any of: `Authorization: Bearer <API_TOKEN>`, the `/login`
cookie, or a valid Cloudflare Access JWT (once `ACCESS_TEAM_DOMAIN` /
`ACCESS_AUD` vars are set):

| Route | Purpose |
|---|---|
| `GET /` | minimal UI: submit form, queue status, episode list |
| `POST /api/queue` | submit `{url}` or `{text, title?}` (+ optional `feed` slug) → `201 {id, status}` |
| `GET /api/queue?status=&limit=&feed=` | list queue items (optionally one feed) |
| `GET /api/queue/:id` | one item (poll this for status) |
| `POST /api/queue/:id/retry` | `failed → queued` |
| `DELETE /api/queue/:id` | delete a `queued`/`failed` item |
| `GET /api/episodes?feed=` | list episodes (optionally one feed) |
| `POST /api/episodes/:id` | edit `{title?, description?, published_at?}` (JSON or form) → updated episode. `published_at` (UTC) is the reorder lever — clients sort by it |
| `GET /api/stats` | counts (feeds, episodes, queue by status), stale-synthesizing count, last publish / oldest queued — drives the UI status bar |
| `POST /api/episodes/:id/delete` | UI delete (form): removes episode, its MP3 from R2, and the queue row |
| `DELETE /api/episodes/:id` | same as above for API clients → `{deleted}` |
| `GET /feed.xml` | RSS for the **default** feed (`vox-biblios`) — kept stable for existing subscribers |
| `GET /feed/<slug>.xml` | RSS for a specific feed |
| `GET /api/feeds` | list feeds |
| `POST /api/feeds` | create `{slug, title, …}` (JSON or form); slug `^[a-z0-9-]+$`, unique |
| `POST/PATCH /api/feeds/:slug` | edit feed metadata |
| `DELETE /api/feeds/:slug?force=1` | delete a feed; refuses (409) if non-empty unless `force` (cascades episodes + R2) |

Poller contract (phase 3):

| Route | Purpose |
|---|---|
| `POST /api/worker/claim` | atomically claim oldest `queued` item (or a stale >30 min `synthesizing` one) → `200` item, or `204` if none |
| `PUT /api/worker/items/:id/audio` | raw MP3 body (Content-Length required) → stored at `cp/episodes/<id>.mp3` |
| `POST /api/worker/items/:id/complete` | `{title?, description?, duration_secs?}` → creates episode, item `published` |
| `POST /api/worker/items/:id/fail` | `{error}` → item `failed` (retryable from UI) |

Status lifecycle: `queued → synthesizing → published | failed` (failed → queued via retry).

### Multi-feed

The control plane can host several app-managed feeds. A submission targets a feed
by `slug`; omit it and it goes to the default (`vox-biblios`), so `/feed.xml` and
bare submits behave exactly as before. Each feed has its own RSS at
`/feed/<slug>.xml`; the UI has a feed switcher and a Feeds panel (add/edit/delete).

**This is a control-plane concept only.** The `vox-biblios` CLI and the poller
have no notion of feeds — the CLI runs unchanged (`--output-dir` mode, no `--feed`
flag), and the poller just synthesizes whatever it claims; the Worker handles all
feed association from the queue item's `feed_id`. Keep the invariant: a feed is
CLI-managed *or* app-managed, never both.

To submit from a phone, build the iOS share-sheet shortcut in
[`../docs/ios-shortcut.md`](../docs/ios-shortcut.md) — it POSTs the shared URL or
text to `/api/queue` with the bearer token (the parked "vb-from-iOS" idea).

## Local development

```sh
npm install
npm run migrate:local
npx wrangler dev          # http://localhost:8787
```

`.dev.vars` (gitignored) provides `API_TOKEN=dev-local-token` for local auth.

## Deploy

Needs a Cloudflare API token with more scope than the `~/.zshrc` one
(see repo CLAUDE.md). Mint at dash.cloudflare.com → My Profile → API Tokens:

- **Account · Workers Scripts · Edit**
- **Account · D1 · Edit**
- **Account · Workers R2 Storage · Edit**
- **Zone (activationlayer.org) · Workers Routes · Edit**
- **Zone (activationlayer.org) · DNS · Edit** (custom-domain record)
- optional: **Account · Access: Apps and Policies · Edit** (lets the Access app be created via API)

```sh
export CLOUDFLARE_API_TOKEN=…   # the new scoped token
export CLOUDFLARE_ACCOUNT_ID=b273bc272420a7fc8581de76e71520a1

npx wrangler deploy             # first deploy auto-provisions the D1 database
npm run migrate:remote          # apply schema + seed default feed

# production API token (poller + iOS shortcut); also save it to
# ~/.config/vox-biblios/config.env as CONTROL_PLANE_TOKEN
openssl rand -hex 32 > /tmp/vb-api-token
npx wrangler secret put API_TOKEN < /tmp/vb-api-token
rm /tmp/vb-api-token

curl https://vb.activationlayer.org/healthz
curl https://vb.activationlayer.org/feed.xml
```

## Cloudflare Access (browser SSO)

Until Access is configured, the UI is reachable via `/login?token=<API_TOKEN>`
(sets an HttpOnly cookie) and the API via bearer token — nothing is open.

### Design: humans use SSO, machines keep the bearer token

Access enforces at Cloudflare's **edge**, before the Worker runs. If the whole
hostname were gated, the browser would work but the bearer-token clients (poller,
iOS shortcut, `curl`) would be **blocked at the edge** — a bearer token means
nothing to Access. So:

- **`/api/*` is bypassed at the edge** (Access · Bypass · Everyone). Requests
  reach the Worker, which still enforces them: machines via `Authorization:
  Bearer`, and the browser via the `CF_Authorization` session cookie that Access
  set at login (the Worker validates that JWT in `auth.ts`, accepting either the
  injected `Cf-Access-Jwt-Assertion` header *or* the cookie).
- **`/feed.xml` and `/healthz` are bypassed** (podcast clients and uptime checks
  can't SSO).
- **Everything else (the `/` UI) requires Access** — an Allow policy for your
  email. This is the app whose Audience (AUD) tag the Worker validates against.

### Dashboard setup (Zero Trust)

The deploy token has no Access scope, and Zero Trust/identity-provider setup is
dashboard-only, so do this in the Cloudflare dashboard (Zero Trust → Access):

1. If you've never used Zero Trust on this account, pick a **team name** — that
   becomes your team domain `https://<team>.cloudflareaccess.com`.
2. **Identity provider**: *One-time PIN* is on by default (emails a code, zero
   config). Add Google/etc. under Settings → Authentication if preferred.
3. **Bypass apps first** (so machines never get blocked mid-cutover) — add a
   self-hosted application for each of `vb.activationlayer.org/api`,
   `.../feed.xml`, `.../healthz`, each with one policy: **Bypass · Everyone**.
4. **Allow app last** — add a self-hosted application for the bare host
   `vb.activationlayer.org` with an **Allow** policy including your email. Copy
   its **Application Audience (AUD) tag**.

### Wire up the Worker

Set both vars in `wrangler.jsonc` and redeploy:

- `ACCESS_TEAM_DOMAIN` = `https://<team>.cloudflareaccess.com` (no trailing slash;
  must match the JWT `iss`)
- `ACCESS_AUD` = the Allow app's Application Audience tag

The old `/login?token=…` path keeps working as break-glass and can be retired
once SSO is verified.
