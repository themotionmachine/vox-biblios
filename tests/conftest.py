"""
Shared fixtures and hermetic shims for the Vox Biblios test suite.

The suite must run on a headless CI runner with only a light dependency set
(pytest, colorama, python-dotenv, nltk) — no boto3, goose3, ffmpeg, macOS
``say``, or network. The shims below make importing the production modules on
the test path succeed under those constraints without touching production code.
"""
import importlib
import importlib.util
import shutil
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _neutralize_nltk_download() -> None:
    """Stop ``text_processor`` import from fetching punkt over the network.

    ``vox_biblios.core.text_processor`` calls ``nltk.download('punkt')`` at
    import time when the data isn't present. The module's sentence tokenizer is
    a fresh, *untrained* ``PunktSentenceTokenizer()`` that never loads that data
    — so a no-op download keeps tokenization behaviour identical to production
    while guaranteeing the import stays offline.
    """
    import nltk

    nltk.download = lambda *args, **kwargs: True


def _stub_missing(name: str, attrs: dict) -> None:
    """Register a stub module for ``name`` only if it can't be imported.

    Locally these scraping deps are installed, so the real modules are used; on
    the hermetic CI runner they're absent, so a stub stands in. Either way
    ``web_scraper`` (imported when ``PodcastManager`` loads) imports cleanly —
    it is never exercised on the local-folder synthesis path under test.
    """
    try:
        importlib.import_module(name)
        return
    except ImportError:
        pass
    module = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(module, attr, value)
    sys.modules[name] = module


_neutralize_nltk_download()
_stub_missing("goose3", {"Goose": object})
_stub_missing("requests", {})
_stub_missing("bs4", {"BeautifulSoup": object})
_stub_missing("trafilatura", {"extract": lambda *a, **k: None})


@pytest.fixture(scope="session")
def poller():
    """The real host-side poller module, loaded by file path.

    Loading the actual ``poller/voxbiblios_poller.py`` (rather than copying its
    logic) ties the contract test to the code that parses the CLI in
    production: if either side of the ``--json`` envelope drifts, the test
    breaks. The module is stdlib-only, so importing it is hermetic.
    """
    path = REPO_ROOT / "poller" / "voxbiblios_poller.py"
    spec = importlib.util.spec_from_file_location("voxbiblios_poller", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_tts(monkeypatch):
    """Register ``FakeTTSProvider`` into the real factory and stub ffmpeg.

    Yields the provider key to pass as ``--provider``. Two production seams are
    replaced so synthesis is hermetic:
      * the factory registry gains a ``fake`` entry resolving to
        ``tests.fakes.FakeTTSProvider`` (writes a stub file, no audio backend);
      * ``concat_audio`` (which shells out to ffmpeg) is replaced with a plain
        single-segment copy — the test asserts the JSON contract, not audio.
    """
    from vox_biblios.tts import factory

    monkeypatch.setitem(
        factory.PROVIDER_REGISTRY, "fake", ("tests.fakes", "FakeTTSProvider")
    )

    from vox_biblios.core import podcast_manager

    def _copy_concat(segment_paths, output_path):
        shutil.copyfile(str(segment_paths[0]), str(output_path))
        return Path(output_path)

    monkeypatch.setattr(podcast_manager, "concat_audio", _copy_concat)
    return "fake"
