# iOS share-sheet shortcut (submit from anywhere)

The control plane already exposes everything needed to queue an episode from a
phone — `POST /api/queue` accepts JSON with a bearer token. This doc builds an
Apple **Shortcut** so that sharing an article (or selected text) from Safari,
Reader, or any app drops it straight into the Vox Biblios queue.

> `.shortcut` files are signed per-device, so this documents how to build the
> shortcut rather than shipping a binary to import.

## What the API expects

`POST https://vb.activationlayer.org/api/queue`

```
Authorization: Bearer <CONTROL_PLANE_TOKEN>
Content-Type: application/json

{ "url": "https://example.com/article" }        # a link
# — or —
{ "text": "raw text…", "title": "Optional title" }   # selected text
```

Success → `201 { "id": "...", "status": "queued" }`. The host poller picks it up
within `POLL_INTERVAL` (30s) and publishes it to `feed.xml`.

The token is the same value stored as `CONTROL_PLANE_TOKEN` in
`~/.config/vox-biblios/config.env` on the host. **Never commit the token**; paste
it into the shortcut once, where iCloud keeps it private to your account.

## Test it from a laptop first

```sh
# loads CONTROL_PLANE_TOKEN from the host config without printing it
set -a; . ~/.config/vox-biblios/config.env; set +a
curl -sS -X POST https://vb.activationlayer.org/api/queue \
  -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/article"}'
# -> {"id":"…","status":"queued"}
```

If that returns `201`, the shortcut will work too.

## Build the shortcut

In the **Shortcuts** app → **+** (new shortcut):

1. **Name & enable sharing.** Name it "Add to Vox Biblios". Open shortcut
   settings (ⓘ) → turn on **Show in Share Sheet** → set accepted input to
   **URLs** and **Text** (turn the rest off).

2. **Capture the share input.** Add a **Receive [Shortcut Input] from Share
   Sheet** action at the top if not already present.

3. **Branch on type.** Add an **If** action: *If* `Shortcut Input` *has any value*
   and is a **URL** → URL branch; *Otherwise* → text branch. (Simplest robust
   form: in the If, choose **Shortcut Input** → condition **contains** `http`.)

   - **URL branch:** add **Text** action with body:
     ```
     {"url":"[Shortcut Input]"}
     ```
     (insert the *Shortcut Input* variable where shown).
   - **Otherwise (text) branch:** optionally add an **Ask for Input** (Text,
     prompt "Title?") then a **Text** action:
     ```
     {"text":"[Shortcut Input]","title":"[Provided Input]"}
     ```

   Use a **Set Variable** (e.g. `payload`) inside each branch so both feed the
   same request below. *(Shortcuts escapes quotes inside variables for you; if a
   pasted article breaks the JSON, switch the text branch to build the body with
   a **Dictionary** action → **Get Contents of URL** "Request Body: JSON" instead
   of hand-writing the string.)*

4. **Send it.** Add **Get Contents of URL**:
   - URL: `https://vb.activationlayer.org/api/queue`
   - Method: **POST**
   - Headers:
     - `Authorization` = `Bearer YOUR_TOKEN_HERE`  ← paste the real token
     - `Content-Type` = `application/json`
   - Request Body: **File** → the `payload` variable (or **JSON** if you used a
     Dictionary in step 3).

5. **Confirm.** Add **Get Dictionary from Input** → **Show Notification** with
   `Queued: [status]` (or just **Show Result**) so you get feedback on send.

## Use it

Share any article from Safari → **Add to Vox Biblios** → notification confirms
`queued`. Within ~30s it's synthesized on the host and appears in the feed.

## Verify end-to-end

After running the shortcut (or the `curl` above), confirm the item flows through:

```sh
curl -s https://vb.activationlayer.org/feed.xml | grep -i '<title>'
```

The new episode title should appear once the poller has published it.
