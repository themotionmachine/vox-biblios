"""
Tests for PodcastManager's long-article splitting (``_split_text_into_parts``).

Pure text logic — no TTS, network, or AWS. Uses the hermetic ``fake`` provider
(registered by the ``fake_tts`` fixture) only so PodcastManager can construct.
"""
from vox_biblios.core.podcast_manager import MAX_PART_CHARS, PodcastManager


def _manager(fake_tts):
    return PodcastManager(provider=fake_tts)


def test_short_text_is_a_single_part(fake_tts):
    pm = _manager(fake_tts)
    text = "A short article. Just a couple of sentences."
    assert pm._split_text_into_parts(text) == [text]


def test_text_at_the_cap_is_not_split(fake_tts):
    pm = _manager(fake_tts)
    text = "x" * MAX_PART_CHARS
    assert pm._split_text_into_parts(text) == [text]


def test_long_text_splits_into_capped_parts(fake_tts):
    pm = _manager(fake_tts)
    # ~240k chars of sentences so the chunker has boundaries to split on, and the
    # result must be several parts (240k / 65k → at least 4).
    text = " ".join(f"Sentence number {i} carries some weight." for i in range(8000))
    parts = pm._split_text_into_parts(text)

    assert len(parts) >= 4, f"expected multiple parts, got {len(parts)}"
    for p in parts:
        assert len(p) <= MAX_PART_CHARS, f"part of {len(p)} chars exceeds the {MAX_PART_CHARS} cap"


def test_split_preserves_all_content(fake_tts):
    pm = _manager(fake_tts)
    sentences = [f"Sentence number {i} carries some weight." for i in range(8000)]
    text = " ".join(sentences)
    parts = pm._split_text_into_parts(text)

    rejoined = " ".join(parts)
    # Every sentence survives the round-trip (first, middle, last sampled).
    for i in (0, 3999, 7999):
        assert f"Sentence number {i} " in rejoined
