"""
Hermetic dispatch tests for ``vox-biblios feed create|list``.

No network: the ControlPlaneClient is replaced with a fake recorder, and the
control-plane token is patched on so the guard passes. These lock the CLI
surface (flags, exit codes, --json envelopes) without touching the worker.
"""
import json

import pytest

from vox_biblios import cli
from vox_biblios.adapters import control_plane as cp_mod
from vox_biblios.adapters.control_plane import ControlPlaneError


class _FakeClient:
    """Stand-in for ControlPlaneClient that records calls and returns canned data."""

    def __init__(self, base_url=None, token=None, *, feeds=None, created=None, raise_with=None):
        self.base_url = base_url
        self.token = token
        self._feeds = feeds if feeds is not None else []
        self._created = created or {"feed": {"slug": "science", "title": "Science"}}
        self._raise_with = raise_with
        self.calls = []

    def list_feeds(self):
        self.calls.append(("list_feeds", {}))
        if self._raise_with:
            raise self._raise_with
        return {"feeds": self._feeds}

    def create_feed(self, slug, title, **kwargs):
        self.calls.append(("create_feed", {"slug": slug, "title": title, **kwargs}))
        if self._raise_with:
            raise self._raise_with
        return self._created


@pytest.fixture
def with_token(monkeypatch):
    """Make the token-missing guard pass."""
    monkeypatch.setattr(cli.config.control_plane, "token", "secret-token")
    monkeypatch.setattr(cli.config.control_plane, "url", "https://cp.example.org")


def _install_client(monkeypatch, fake):
    monkeypatch.setattr(cp_mod, "ControlPlaneClient", lambda *a, **k: fake)
    return fake


def _run(args_list):
    return cli.feed_command(cli.parse_args(args_list))


def test_feed_no_subcommand_errors(with_token):
    assert _run(["feed"]) == 1


def test_feed_list_missing_token_json(monkeypatch, capsys):
    monkeypatch.setattr(cli.config.control_plane, "token", None)
    code = _run(["feed", "list", "--json"])
    out = capsys.readouterr().out
    assert code == 1
    assert json.loads(out) == {"status": "error", "error": "CONTROL_PLANE_TOKEN not set"}


def test_feed_list_json_prints_feeds_array(monkeypatch, with_token, capsys):
    feeds = [{"slug": "science", "title": "Science"}, {"slug": "news", "title": "News"}]
    _install_client(monkeypatch, _FakeClient(feeds=feeds))
    code = _run(["feed", "list", "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out) == feeds


def test_feed_list_human_output(monkeypatch, with_token, capsys):
    _install_client(monkeypatch, _FakeClient(feeds=[{"slug": "science", "title": "Science"}]))
    code = _run(["feed", "list"])
    out = capsys.readouterr().out
    assert code == 0
    assert "science" in out
    assert "Science" in out


def test_feed_list_error_json(monkeypatch, with_token, capsys):
    _install_client(monkeypatch, _FakeClient(raise_with=ControlPlaneError("control plane returned 503")))
    code = _run(["feed", "list", "--json"])
    out = capsys.readouterr().out
    assert code == 1
    assert json.loads(out)["status"] == "error"
    assert "503" in json.loads(out)["error"]


def test_feed_create_passes_flags_to_client(monkeypatch, with_token, capsys):
    fake = _install_client(monkeypatch, _FakeClient(
        created={"feed": {"slug": "science", "title": "Science"}}))
    code = _run([
        "feed", "create", "science",
        "--title", "Science",
        "--description", "All things science",
        "--language", "en",
        "--explicit",
        "--json",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out) == {"slug": "science", "title": "Science"}
    name, kwargs = fake.calls[0]
    assert name == "create_feed"
    assert kwargs["slug"] == "science"
    assert kwargs["title"] == "Science"
    assert kwargs["description"] == "All things science"
    assert kwargs["language"] == "en"
    assert kwargs["explicit"] is True


def test_feed_create_optionals_default_none(monkeypatch, with_token, capsys):
    fake = _install_client(monkeypatch, _FakeClient())
    code = _run(["feed", "create", "science", "--title", "Science", "--json"])
    assert code == 0
    _, kwargs = fake.calls[0]
    # Unspecified optionals (incl. --explicit) reach the client as None so the
    # adapter omits them from the payload.
    assert kwargs["description"] is None
    assert kwargs["link"] is None
    assert kwargs["author"] is None
    assert kwargs["image_url"] is None
    assert kwargs["language"] is None
    assert kwargs["explicit"] is None


def test_feed_create_409_error_json(monkeypatch, with_token, capsys):
    _install_client(monkeypatch, _FakeClient(
        raise_with=ControlPlaneError("control plane returned 409: feed 'science' already exists")))
    code = _run(["feed", "create", "science", "--title", "Science", "--json"])
    out = capsys.readouterr().out
    assert code == 1
    payload = json.loads(out)
    assert payload["status"] == "error"
    assert "already exists" in payload["error"]


def test_feed_create_human_success(monkeypatch, with_token, capsys):
    _install_client(monkeypatch, _FakeClient(created={"feed": {"slug": "science", "title": "Science"}}))
    code = _run(["feed", "create", "science", "--title", "Science"])
    out = capsys.readouterr().out
    assert code == 0
    assert "science" in out
