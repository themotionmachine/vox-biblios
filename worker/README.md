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
| `POST /api/queue` | submit `{url}` or `{text, title?}` (JSON or form-encoded) → `201 {id, status}` |
| `GET /api/queue?status=&limit=` | list queue items |
| `GET /api/queue/:id` | one item (poll this for status) |
| `POST /api/queue/:id/retry` | `failed → queued` |
| `DELETE /api/queue/:id` | delete a `queued`/`failed` item |
| `GET /api/episodes` | list episodes |
| `POST /api/episodes/:id` | edit `{title?, description?}` (JSON or form) → updated episode |
| `POST /api/episodes/:id/delete` | UI delete (form): removes episode, its MP3 from R2, and the queue row |
| `DELETE /api/episodes/:id` | same as above for API clients → `{deleted}` |

Poller contract (phase 3):

| Route | Purpose |
|---|---|
| `POST /api/worker/claim` | atomically claim oldest `queued` item (or a stale >30 min `synthesizing` one) → `200` item, or `204` if none |
| `PUT /api/worker/items/:id/audio` | raw MP3 body (Content-Length required) → stored at `cp/episodes/<id>.mp3` |
| `POST /api/worker/items/:id/complete` | `{title?, description?, duration_secs?}` → creates episode, item `published` |
| `POST /api/worker/items/:id/fail` | `{error}` → item `failed` (retryable from UI) |

Status lifecycle: `queued → synthesizing → published | failed` (failed → queued via retry).

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

To add SSO: Zero Trust → Access → Applications → add a self-hosted app for
`vb.activationlayer.org`, allow-policy for your email. Add a second app for
`vb.activationlayer.org/feed.xml` with a **Bypass · Everyone** policy (podcast
clients can't SSO), and similarly bypass `/healthz` if desired. Then set the
`ACCESS_TEAM_DOMAIN` (e.g. `https://<team>.cloudflareaccess.com`) and
`ACCESS_AUD` (the app's Application Audience tag) vars in `wrangler.jsonc` and
redeploy — the Worker then validates the Access JWT on protected routes.
