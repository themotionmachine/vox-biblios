#!/usr/bin/env python3
"""
Vox Biblios synthesis poller (phase 3 of issue #5).

A thin host-side daemon that drains the control-plane queue:

    claim  ->  vox-biblios process <input> --output-dir <tmp> --json
           ->  upload the MP3      (PUT  /api/worker/items/:id/audio)
           ->  report published    (POST /api/worker/items/:id/complete)
        or ->  report failed       (POST /api/worker/items/:id/fail)

It shells out to the `vox-biblios` CLI in local mode (`--output-dir`), so the
synthesis core is untouched and the CLI keeps no dependency on this file. Only
the Python standard library is used, so the daemon has no install step beyond
the CLI itself.

Config is read from the environment, falling back to the same
~/.config/vox-biblios/config.env the CLI uses:

    CONTROL_PLANE_URL     default https://vb.activationlayer.org
    CONTROL_PLANE_TOKEN   required (bearer; stored as CONTROL_PLANE_TOKEN in config.env)
    VOX_BIBLIOS_BIN       default: ~/.local/bin/vox-biblios, else `vox-biblios` on PATH
    POLL_INTERVAL         seconds to wait when the queue is empty (default 30)
    SYNTH_TIMEOUT         seconds before a single synthesis is killed (default 3600)
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

CONFIG_ENV = Path(os.path.expanduser("~/.config/vox-biblios/config.env"))

# When run under launchd, StandardOutPath redirection is unreliable (it does not
# wire up in an SSH-initiated GUI domain), so the daemon owns its log file
# directly rather than trusting the inherited stdout fd. Set via POLLER_LOG_FILE.
_logfh = None


def _open_log(path: Optional[str]) -> None:
    global _logfh
    if not path:
        return
    p = Path(os.path.expanduser(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    _logfh = open(p, "a", buffering=1, encoding="utf-8")  # line-buffered


def _augment_path() -> None:
    """launchd gives a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin), so Homebrew
    tools the CLI shells out to — notably ffmpeg/ffprobe — are not found. Prepend
    the usual locations (and ~/.local/bin) so both our ffprobe lookup and the
    inherited subprocess environment can find them."""
    extra = ["/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.local/bin")]
    current = os.environ.get("PATH", "").split(os.pathsep)
    prepend = [d for d in extra if os.path.isdir(d) and d not in current]
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend + current)


def log(msg: str) -> None:
    """Timestamped log to stdout (for foreground runs) and, if configured, to the
    poller's own log file (for launchd)."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    line = f"{ts} {msg}"
    print(line, flush=True)
    if _logfh is not None:
        _logfh.write(line + "\n")
        _logfh.flush()


def _load_config_env(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser for config.env (handles `export` and quotes)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            values[key] = val
    return values


class Config:
    def __init__(self) -> None:
        file_cfg = _load_config_env(CONFIG_ENV)

        def get(name: str, default: Optional[str] = None) -> Optional[str]:
            return os.environ.get(name) or file_cfg.get(name) or default

        self.base_url = (get("CONTROL_PLANE_URL", "https://vb.activationlayer.org") or "").rstrip("/")
        self.token = get("CONTROL_PLANE_TOKEN")
        self.bin = self._resolve_bin(get("VOX_BIBLIOS_BIN"))
        self.poll_interval = float(get("POLL_INTERVAL", "30") or 30)
        self.synth_timeout = float(get("SYNTH_TIMEOUT", "3600") or 3600)
        self.log_file = get("POLLER_LOG_FILE")  # app-owned log; None = stdout only

    @staticmethod
    def _resolve_bin(explicit: Optional[str]) -> str:
        if explicit:
            return explicit
        local = Path(os.path.expanduser("~/.local/bin/vox-biblios"))
        if local.is_file():
            return str(local)
        found = shutil.which("vox-biblios")
        return found or "vox-biblios"


class SynthFailure(Exception):
    """Synthesis failed in a way that should mark the queue item `failed`."""


class TransportError(Exception):
    """A control-plane HTTP call failed; leave the item for stale-claim recovery."""


# ---- control-plane HTTP client ----

class Client:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict[str, Any]] = None,
        data: Optional[bytes] = None,
        content_type: Optional[str] = None,
        timeout: float = 30.0,
    ) -> tuple[int, bytes]:
        url = f"{self.cfg.base_url}{path}"
        # A descriptive User-Agent: urllib's default ("Python-urllib/x.y") trips
        # Cloudflare's Browser Integrity Check (403, error 1010) on the zone.
        headers = {
            "Authorization": f"Bearer {self.cfg.token}",
            "User-Agent": "vox-biblios-poller/1.0",
        }
        body = data
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx with a body — return it so callers can branch on status.
            return e.code, e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TransportError(f"{method} {path}: {e}") from e

    def claim(self) -> Optional[dict[str, Any]]:
        status, body = self._request("POST", "/api/worker/claim")
        if status == 204:
            return None
        if status != 200:
            raise TransportError(f"claim returned {status}: {body[:200]!r}")
        return json.loads(body)

    def upload_audio(self, item_id: str, part: int, audio_path: Path) -> dict[str, Any]:
        """Upload one part's audio. Returns the worker's {audio_key, audio_bytes}."""
        data = audio_path.read_bytes()
        status, body = self._request(
            "PUT",
            f"/api/worker/items/{item_id}/audio?part={part}",
            data=data,
            content_type="audio/mpeg",
            timeout=300.0,
        )
        if status != 200:
            raise TransportError(f"upload returned {status}: {body[:200]!r}")
        return json.loads(body)

    def complete(
        self,
        item_id: str,
        parts: list[dict[str, Any]],
        tts_provider: Optional[str] = None,
        tts_voice: Optional[str] = None,
    ) -> None:
        """Publish an item as one episode per part (a normal article has one part)."""
        payload: dict[str, Any] = {"parts": parts}
        # Record what we actually synthesized with, for the episode's audit trail.
        if tts_provider:
            payload["tts_provider"] = tts_provider
        if tts_voice:
            payload["tts_voice"] = tts_voice
        status, body = self._request("POST", f"/api/worker/items/{item_id}/complete", json_body=payload)
        if status != 201:
            raise TransportError(f"complete returned {status}: {body[:200]!r}")

    def fail(self, item_id: str, error: str) -> None:
        status, body = self._request("POST", f"/api/worker/items/{item_id}/fail", json_body={"error": error})
        if status != 200:
            raise TransportError(f"fail returned {status}: {body[:200]!r}")


# ---- synthesis ----

def _extract_json(stdout: str) -> dict[str, Any]:
    """Pull the first complete JSON object out of CLI stdout, ignoring any noise
    a TTS backend may have printed around it."""
    start = stdout.find("{")
    if start == -1:
        raise SynthFailure(f"no JSON in CLI output: {stdout[-500:]!r}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(stdout[start:])
    except json.JSONDecodeError as e:
        raise SynthFailure(f"unparsable CLI output: {e}: {stdout[-500:]!r}") from e
    return obj


def synthesize(cfg: Config, item: dict[str, Any], tmp_dir: Path) -> list[dict[str, Any]]:
    """Run the CLI in local mode and return one part-episode per output MP3.

    A normal article yields a single entry; a very long one yields several
    (the CLI splits it). Each entry is {mp3, title, description}.
    """
    kind = item["kind"]
    cmd = [cfg.bin, "process"]
    stdin_text: Optional[str] = None

    if kind == "url":
        cmd.append(item["payload"])
    elif kind == "text":
        cmd.append("-")  # read text from stdin
        stdin_text = item["payload"]
    else:
        raise SynthFailure(f"unknown item kind: {kind!r}")

    cmd += ["--output-dir", str(tmp_dir), "--json"]

    # The control plane resolves queue-override → feed-default → host-default and
    # hands back the effective voice on claim. Pass it through; when absent the
    # CLI falls back to its own configured default.
    provider = item.get("effective_tts_provider")
    voice = item.get("effective_tts_voice")
    if provider:
        cmd += ["--provider", provider]
    if voice:
        cmd += ["--voice", voice]

    log(f"synthesizing {item['id'][:8]} ({kind}) via: {' '.join(cmd[:2])} … --output-dir {tmp_dir}"
        + (f" (voice {provider or '?'}:{voice})" if voice else ""))
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=cfg.synth_timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise SynthFailure(f"synthesis timed out after {cfg.synth_timeout:.0f}s") from e
    except FileNotFoundError as e:
        raise SynthFailure(f"vox-biblios CLI not found at {cfg.bin!r}") from e

    result = _extract_json(proc.stdout)
    status = result.get("status")
    episodes = result.get("episodes") or []

    if status != "success" or not episodes:
        failures = result.get("failures") or []
        parts = []
        if failures:
            parts.append("; ".join(f"{f.get('source')}: {f.get('error')}" for f in failures))
        elif result.get("error"):
            parts.append(str(result["error"]))
        # The structured failure is often terse ("synthesis failed"); the real
        # cause (traceback, provider error) is on stderr, so always attach a tail.
        if proc.stderr and proc.stderr.strip():
            parts.append("stderr: " + proc.stderr.strip()[-1500:])
        detail = " | ".join(parts) or "no episode produced"
        raise SynthFailure(f"CLI status={status!r} rc={proc.returncode}: {detail}")

    n = len(episodes)
    out: list[dict[str, Any]] = []
    for ep in episodes:
        mp3 = Path(ep["url"])  # in --output-dir mode this is the local file path
        if not mp3.is_file():
            raise SynthFailure(f"CLI reported success but MP3 missing: {mp3}")

        part_no = ep.get("part")
        parts_total = ep.get("parts") or n
        if kind == "url":
            # The scraped title already carries any '… Part k of N' suffix.
            title = ep.get("title")
        else:
            # Text/stdin synthesis titles itself 'stdin'; prefer the submitter's
            # title, re-applying the part suffix when the CLI split the text.
            base = item.get("title") or ep.get("title")
            title = (f"{base} — Part {part_no} of {parts_total}"
                     if base and parts_total and parts_total > 1 and part_no else base)
        out.append({"mp3": mp3, "title": title, "description": ep.get("description") or ""})
    return out


def probe_duration(mp3: Path) -> Optional[int]:
    """Best-effort audio duration in whole seconds via ffprobe; None if unavailable."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)],
            capture_output=True, text=True, timeout=30,
        )
        return int(round(float(out.stdout.strip())))
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


# ---- main loop ----

_running = True


def _handle_signal(signum, _frame) -> None:
    global _running
    _running = False
    log(f"received signal {signum}; finishing current item then exiting")


def process_one(cfg: Config, client: Client, item: dict[str, Any]) -> None:
    item_id = item["id"]
    tmp_dir = Path(tempfile.mkdtemp(prefix="vb-poller-"))
    try:
        episodes = synthesize(cfg, item, tmp_dir)
        parts: list[dict[str, Any]] = []
        for i, ep in enumerate(episodes):
            up = client.upload_audio(item_id, i, ep["mp3"])
            parts.append({
                "audio_key": up["audio_key"],
                "audio_bytes": up.get("audio_bytes"),
                "title": ep["title"],
                "description": ep["description"],
                "duration_secs": probe_duration(ep["mp3"]),
            })
        client.complete(
            item_id, parts,
            tts_provider=item.get("effective_tts_provider"),
            tts_voice=item.get("effective_tts_voice"),
        )
        total_bytes = sum(p.get("audio_bytes") or 0 for p in parts)
        suffix = f" in {len(parts)} parts" if len(parts) > 1 else ""
        log(f"published {item_id[:8]}{suffix} ({total_bytes} bytes): {parts[0]['title'] or '(untitled)'}")
    except SynthFailure as e:
        log(f"FAILED {item_id[:8]}: {e}")
        client.fail(item_id, str(e))  # may raise TransportError; bubble up to loop
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run(cfg: Config) -> int:
    if not cfg.token:
        log("ERROR: CONTROL_PLANE_TOKEN not set (env or config.env). Exiting.")
        return 1

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    client = Client(cfg)
    log(f"poller started: {cfg.base_url} via {cfg.bin} (poll {cfg.poll_interval:.0f}s)")

    while _running:
        try:
            item = client.claim()
        except TransportError as e:
            log(f"claim failed (will retry): {e}")
            _sleep(cfg.poll_interval)
            continue

        if item is None:
            _sleep(cfg.poll_interval)
            continue

        try:
            process_one(cfg, client, item)
        except TransportError as e:
            # Network/control-plane error mid-item: don't lose work. The item
            # stays `synthesizing` and the control plane reclaims it after its
            # stale window, so another pass retries it.
            log(f"transport error on {item['id'][:8]} (left for stale-claim recovery): {e}")
            _sleep(cfg.poll_interval)
        # On success, loop immediately to drain the queue without waiting.

    log("poller stopped")
    return 0


def main() -> int:
    _augment_path()
    cfg = Config()
    _open_log(cfg.log_file)
    try:
        return _run(cfg)
    except Exception:
        import traceback
        log("FATAL: unhandled exception:\n" + traceback.format_exc())
        raise


def _sleep(seconds: float) -> None:
    """Sleep in short slices so signals are handled promptly."""
    end = time.monotonic() + seconds
    while _running and time.monotonic() < end:
        time.sleep(min(1.0, end - time.monotonic()))


if __name__ == "__main__":
    sys.exit(main())
