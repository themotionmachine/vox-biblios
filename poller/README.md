# Vox Biblios synthesis poller (phase 3 of #5)

A host-side daemon that turns queued submissions into published episodes. It
drains the [control plane](../worker/) queue, runs the `vox-biblios` CLI locally
(where the TTS models live), uploads the resulting MP3, and reports the result:

```
POST /api/worker/claim              -> next queued item (or 204)
vox-biblios process <input> \
    --output-dir <tmp> --json       -> synthesize locally (no AWS/R2 from the CLI)
PUT  /api/worker/items/:id/audio    -> upload the MP3 to R2 via the worker
POST /api/worker/items/:id/complete -> create the episode (status: published)
  or /api/worker/items/:id/fail     -> record the error (status: failed, retryable)
```

The CLI runs in **local mode** (`--output-dir`), so the synthesis core is
untouched and the poller does the publishing. The CLI has no dependency on this
directory; this directory depends only on the CLI being installed.

Stdlib only — no `pip install` for the poller itself.

## Configuration

Read from the environment first, then `~/.config/vox-biblios/config.env` (the
same file the CLI uses), so no secrets live in the launchd plist:

| Variable | Default | Purpose |
|---|---|---|
| `CONTROL_PLANE_TOKEN` | — (required) | bearer token; matches the worker's `API_TOKEN` secret |
| `CONTROL_PLANE_URL` | `https://vb.activationlayer.org` | control-plane base URL |
| `VOX_BIBLIOS_BIN` | `~/.local/bin/vox-biblios`, else `vox-biblios` on PATH | CLI to invoke |
| `POLL_INTERVAL` | `30` | seconds to wait when the queue is empty |
| `SYNTH_TIMEOUT` | `3600` | seconds before one synthesis is killed |

The production token was written to `config.env` as `CONTROL_PLANE_TOKEN` when
the worker was deployed, so on this host no extra setup is needed.

## Run

Foreground (for testing — Ctrl-C to stop; finishes the current item first):

```sh
python3 poller/voxbiblios_poller.py
# force a fast provider for a smoke test:
TTS_PROVIDER=say CONTROL_PLANE_URL=http://localhost:8787 \
  CONTROL_PLANE_TOKEN=dev-local-token python3 poller/voxbiblios_poller.py
```

As a launchd agent (starts at login, restarts on crash):

```sh
poller/install.sh             # copy script out of repo, render plist, load, start
poller/install.sh uninstall   # stop and remove

tail -f ~/Library/Logs/voxbiblios-poller.log
launchctl print gui/$(id -u)/com.voxbiblios.poller | grep state
```

`install.sh` copies the script to `~/.local/share/vox-biblios/` and runs it from
there — **not** from the repo. Two macOS launchd realities forced this and the
choices around it; they are non-obvious and worth knowing before you change the
setup:

- **TCC / protected folders.** A launchd agent has no consent grant for
  `~/Desktop`, `~/Documents`, or `~/Downloads`. If the script lives under one
  (this repo is under `~/Desktop`), the interpreter *hangs* trying to read it at
  startup — no error, no log, just a stuck process. Running the script from
  `~/.local/share` avoids it.
- **Minimal PATH.** launchd hands the process `/usr/bin:/bin:/usr/sbin:/sbin`,
  which excludes Homebrew. The CLI shells out to `ffmpeg` (and the poller probes
  duration with `ffprobe`) by bare name, so the poller prepends
  `/opt/homebrew/bin`, `/usr/local/bin`, and `~/.local/bin` to PATH at startup.
- **Logging.** launchd's `StandardOutPath` redirection is unreliable when the
  agent is bootstrapped from an SSH session, so the daemon writes its own log
  (`POLLER_LOG_FILE`, set by the plist). `RunAtLoad` also doesn't fire reliably
  over SSH, so `install.sh` issues an explicit `launchctl kickstart`.

## Behavior notes

- **One item = one episode.** A URL is scraped (its title becomes the episode
  title); a text submission is synthesized from stdin and titled from the
  submission's `title` field (falling back to `Episode <id>` if absent — stdin
  synthesis would otherwise title it "stdin"). Text-item descriptions currently
  read "Generated from stdin.txt", a cosmetic artifact of the CLI's stdin label.
- **Drains, then waits.** After a success it claims again immediately; it only
  sleeps `POLL_INTERVAL` when the queue is empty.
- **Crash-safe handoff.** If a control-plane call fails mid-item the item is
  left `synthesizing`; the worker reclaims stale claims after 30 minutes, so the
  next pass retries it. Synthesis that legitimately exceeds 30 minutes could be
  double-claimed — fine for a single poller; add a heartbeat before running
  several. Genuine synthesis failures are reported via `/fail` and are retryable
  from the UI.
- **Clean shutdown.** SIGTERM/SIGINT finish the in-flight item, then exit.
