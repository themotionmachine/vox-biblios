"""
Tests for ``vox_biblios.adapters.control_plane.ControlPlaneClient``.

Locks the request payload shapes (``{url}`` vs ``{text, title?}``, optional
``feed``) and error handling (``ControlPlaneError`` on non-201). ``_request`` is
replaced with a recorder so no real network is touched.
"""
import json

import pytest

from vox_biblios.adapters.control_plane import ControlPlaneClient, ControlPlaneError


class _Recorder:
    """Stand-in for ControlPlaneClient._request that records calls."""

    def __init__(self, status=201, body=None):
        self.status = status
        self.body = body if body is not None else b'{"id": "abc", "status": "queued"}'
        self.calls = []

    def __call__(self, method, path, *, json_body=None, timeout=30.0):
        self.calls.append({"method": method, "path": path, "json_body": json_body})
        return self.status, self.body


@pytest.fixture
def client(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org/", "secret-token")
    rec = _Recorder()
    monkeypatch.setattr(c, "_request", rec)
    return c, rec


def test_base_url_trailing_slash_stripped():
    c = ControlPlaneClient("https://cp.example.org/", "t")
    assert c.base_url == "https://cp.example.org"


def test_submit_url_payload_shape(client):
    c, rec = client
    body = c.submit_url("https://example.com/article")
    assert body == {"id": "abc", "status": "queued"}
    call = rec.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/queue"
    assert call["json_body"] == {"url": "https://example.com/article"}


def test_submit_url_with_feed(client):
    c, rec = client
    c.submit_url("https://example.com/a", feed="science")
    assert rec.calls[0]["json_body"] == {"url": "https://example.com/a", "feed": "science"}


def test_submit_text_payload_shape(client):
    c, rec = client
    c.submit_text("hello world")
    assert rec.calls[0]["json_body"] == {"text": "hello world"}


def test_submit_text_with_title_and_feed(client):
    c, rec = client
    c.submit_text("body", title="My Title", feed="news")
    assert rec.calls[0]["json_body"] == {"text": "body", "title": "My Title", "feed": "news"}


def test_submit_text_omits_empty_title(client):
    c, rec = client
    c.submit_text("body", title=None)
    assert "title" not in rec.calls[0]["json_body"]


def test_non_201_raises_control_plane_error(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org", "t")
    monkeypatch.setattr(
        c, "_request", _Recorder(status=400, body=b'{"error": "bad feed"}')
    )
    with pytest.raises(ControlPlaneError) as exc:
        c.submit_url("https://example.com/a")
    msg = str(exc.value)
    assert "400" in msg
    assert "bad feed" in msg


def test_stats_non_200_raises(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org", "t")
    monkeypatch.setattr(c, "_request", _Recorder(status=503, body=b""))
    with pytest.raises(ControlPlaneError):
        c.stats()


def test_stats_returns_parsed_body(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org", "t")
    payload = {"queued": 3, "episodes": 10}
    monkeypatch.setattr(
        c, "_request", _Recorder(status=200, body=json.dumps(payload).encode())
    )
    assert c.stats() == payload
