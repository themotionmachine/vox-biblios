"""
Golden contract test for ``vox-biblios process --json``.

This is the highest-value test in the suite. The host poller shells out to
``vox-biblios process <input> --output-dir <tmp> --json`` and parses the result
(``poller/voxbiblios_poller.py`` ~256-285). If the JSON envelope emitted by the
CLI (``vox_biblios/cli.py`` ~487-501) drifts, synthesis silently breaks in
production and nothing else catches it. This test locks both ends of that
contract: it drives the real CLI path with a hermetic fake TTS backend and
feeds the emitted JSON through the *real* poller's parsing logic.
"""
import json

import pytest

from vox_biblios import cli


def _run_process(args_list):
    """Parse + run the ``process`` subcommand, returning (exit_code, stdout)."""
    args = cli.parse_args(args_list)
    code = cli.process_command(args)
    return code


@pytest.fixture
def sample_input(tmp_path):
    """A folder with one speakable text file — the local-folder synthesis path."""
    src = tmp_path / "in"
    src.mkdir()
    (src / "sample.txt").write_text(
        "The history of bookbinding spans many centuries. "
        "Early scribes copied texts by hand onto vellum. "
        "Later, movable type transformed how knowledge spread.\n",
        encoding="utf-8",
    )
    return src


def test_process_json_success_envelope(sample_input, tmp_path, fake_tts, capsys):
    """A successful run emits exactly the shape the poller expects."""
    out_dir = tmp_path / "out"
    code = _run_process([
        "process", str(sample_input),
        "--output-dir", str(out_dir),
        "--provider", fake_tts,
        "--json",
    ])
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert code == 0
    # Top-level contract.
    assert payload["status"] == "success"
    assert payload["failures"] == []
    assert "episodes" in payload
    assert len(payload["episodes"]) == 1

    # Episode contract: the fields the poller reads, plus a real file.
    episode = payload["episodes"][0]
    assert set(["title", "url", "description", "part", "parts"]).issubset(episode.keys())
    assert episode["title"] == "sample"
    assert episode["description"].startswith("Generated from")
    # A short article is a single part.
    assert episode["part"] == 1
    assert episode["parts"] == 1

    from pathlib import Path
    mp3 = Path(episode["url"])
    assert mp3.is_file(), "episodes[0]['url'] must be an existing local file"
    assert mp3.parent == out_dir, "MP3 must live in --output-dir"


def test_process_json_consumed_by_real_poller(sample_input, tmp_path, fake_tts,
                                               capsys, poller):
    """Feed the emitted JSON through the poller's own extraction + reads.

    This is the true regression guard: it exercises the production parsing code,
    so a drift on either side of the envelope fails the test rather than
    silently breaking synthesis.
    """
    out_dir = tmp_path / "out"
    _run_process([
        "process", str(sample_input),
        "--output-dir", str(out_dir),
        "--provider", fake_tts,
        "--json",
    ])
    stdout = capsys.readouterr().out

    # The poller tolerates noise around the JSON; _extract_json pulls it out.
    result = poller._extract_json(stdout)

    # Mirror exactly what synthesize() reads from the result (poller ~256-283).
    status = result.get("status")
    episodes = result.get("episodes") or []
    assert status == "success"
    assert episodes, "poller treats empty episodes as a synthesis failure"

    ep = episodes[0]
    from pathlib import Path
    mp3 = Path(ep["url"])
    assert mp3.is_file()
    assert ep.get("title") == "sample"
    assert isinstance(ep.get("description"), str)


def test_process_json_extract_tolerates_leading_noise(poller):
    """The poller scans for the first JSON object; guard that assumption."""
    noisy = "loading model...\nsome banner\n" + json.dumps(
        {"status": "success", "episodes": [{"url": "/x", "title": "t",
                                            "description": "d"}]}
    ) + "\ntrailing line\n"
    result = poller._extract_json(noisy)
    assert result["status"] == "success"
    assert result["episodes"][0]["title"] == "t"
