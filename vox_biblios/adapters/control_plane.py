"""
Thin client for the Vox Biblios control plane (Cloudflare Worker queue).

The `cloudflare` publish target submits work to the control-plane queue and
lets the host-side poller synthesize it later. This keeps the CLI decoupled
from synthesis on this path — it only speaks the queue's HTTP API, and needs
no AWS/R2 credentials. Only the Python standard library is used (mirroring the
poller), so there is no extra dependency.

Queue API (see worker/README.md):
    POST /api/queue   {url} | {text, title?}  (+ optional feed slug)  -> 201 {id, status}
    GET  /api/stats   -> queue/episode counts, staleness, oldest queued
"""
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from vox_biblios.utils.logging import get_logger

logger = get_logger(__name__)


class ControlPlaneError(Exception):
    """A control-plane HTTP call failed (transport or non-success status)."""


class ControlPlaneClient:
    """Minimal queue client. Construct with the base URL and bearer token."""

    def __init__(self, base_url: str, token: str):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> tuple[int, bytes]:
        url = f"{self.base_url}{path}"
        # A descriptive User-Agent: urllib's default ("Python-urllib/x.y") trips
        # Cloudflare's Browser Integrity Check (403, error 1010) on the zone.
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "vox-biblios-cli/1.0",
        }
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx with a body — return it so callers can surface the reason.
            return e.code, e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ControlPlaneError(f"{method} {path}: {e}") from e

    def submit_url(self, url: str, feed: Optional[str] = None) -> Dict[str, Any]:
        """Queue a URL for synthesis. Returns the parsed {id, status} body."""
        return self._submit({"url": url}, feed)

    def submit_text(self, text: str, title: Optional[str] = None,
                    feed: Optional[str] = None) -> Dict[str, Any]:
        """Queue raw text for synthesis. Returns the parsed {id, status} body."""
        payload: Dict[str, Any] = {"text": text}
        if title:
            payload["title"] = title
        return self._submit(payload, feed)

    def _submit(self, payload: Dict[str, Any], feed: Optional[str]) -> Dict[str, Any]:
        if feed:
            payload = {**payload, "feed": feed}
        status, body = self._request("POST", "/api/queue", json_body=payload)
        if status != 201:
            raise ControlPlaneError(_describe(status, body))
        return json.loads(body)

    def stats(self) -> Dict[str, Any]:
        """At-a-glance queue health (used to warn about an unattended poller)."""
        status, body = self._request("GET", "/api/stats")
        if status != 200:
            raise ControlPlaneError(_describe(status, body))
        return json.loads(body)


def _describe(status: int, body: bytes) -> str:
    """Build an error message, preferring the worker's {error} field."""
    try:
        err = json.loads(body).get("error")
    except (ValueError, AttributeError):
        err = None
    detail = err or (body[:200].decode("utf-8", "replace") if body else "")
    return f"control plane returned {status}: {detail}".rstrip(": ")
