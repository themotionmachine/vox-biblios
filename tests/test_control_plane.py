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


# --- list_feeds ---------------------------------------------------------------

def test_list_feeds_request_shape_and_parse(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org", "t")
    payload = {"feeds": [{"slug": "science", "title": "Science"}]}
    rec = _Recorder(status=200, body=json.dumps(payload).encode())
    monkeypatch.setattr(c, "_request", rec)
    assert c.list_feeds() == payload
    call = rec.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/api/feeds"
    assert call["json_body"] is None


def test_list_feeds_non_200_raises(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org", "t")
    monkeypatch.setattr(c, "_request", _Recorder(status=503, body=b""))
    with pytest.raises(ControlPlaneError):
        c.list_feeds()


# --- create_feed --------------------------------------------------------------

@pytest.fixture
def feed_client(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org/", "secret-token")
    rec = _Recorder(status=201, body=b'{"feed": {"slug": "science", "title": "Science"}}')
    monkeypatch.setattr(c, "_request", rec)
    return c, rec


def test_create_feed_required_only_payload(feed_client):
    c, rec = feed_client
    body = c.create_feed("science", "Science")
    assert body == {"feed": {"slug": "science", "title": "Science"}}
    call = rec.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/feeds"
    assert call["json_body"] == {"slug": "science", "title": "Science"}


def test_create_feed_omits_none_optionals(feed_client):
    c, rec = feed_client
    c.create_feed("science", "Science", description=None, link=None)
    assert rec.calls[0]["json_body"] == {"slug": "science", "title": "Science"}


def test_create_feed_includes_optionals(feed_client):
    c, rec = feed_client
    c.create_feed(
        "science",
        "Science",
        description="All things science",
        link="https://example.com",
        author="Ryan",
        image_url="https://example.com/cover.png",
        language="en",
        explicit=True,
    )
    assert rec.calls[0]["json_body"] == {
        "slug": "science",
        "title": "Science",
        "description": "All things science",
        "link": "https://example.com",
        "author": "Ryan",
        "image_url": "https://example.com/cover.png",
        "language": "en",
        "explicit": True,
    }


def test_create_feed_explicit_false_is_sent(feed_client):
    # explicit=False is a real value, not absent — it must be sent.
    c, rec = feed_client
    c.create_feed("science", "Science", explicit=False)
    assert rec.calls[0]["json_body"]["explicit"] is False


def test_create_feed_includes_voice_pair(feed_client):
    c, rec = feed_client
    c.create_feed("science", "Science", tts_provider="kokoro", tts_voice="af_heart")
    body = rec.calls[0]["json_body"]
    assert body["tts_provider"] == "kokoro"
    assert body["tts_voice"] == "af_heart"


def test_create_feed_omits_voice_when_none(feed_client):
    c, rec = feed_client
    c.create_feed("science", "Science")
    body = rec.calls[0]["json_body"]
    assert "tts_provider" not in body
    assert "tts_voice" not in body


def test_create_feed_non_201_raises(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org", "t")
    monkeypatch.setattr(c, "_request", _Recorder(status=400, body=b'{"error": "title is required"}'))
    with pytest.raises(ControlPlaneError) as exc:
        c.create_feed("science", "")
    assert "400" in str(exc.value)
    assert "title is required" in str(exc.value)


def test_create_feed_409_surfaces_message(monkeypatch):
    c = ControlPlaneClient("https://cp.example.org", "t")
    monkeypatch.setattr(
        c, "_request",
        _Recorder(status=409, body=b'{"error": "feed \'science\' already exists"}'),
    )
    with pytest.raises(ControlPlaneError) as exc:
        c.create_feed("science", "Science")
    msg = str(exc.value)
    assert "409" in msg
    assert "already exists" in msg
