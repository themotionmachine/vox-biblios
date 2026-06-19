"""
Tests for ``vox_biblios.core.text_processor``.

Deterministic, dependency-light coverage of the chunker (never exceeds max
size, sane boundaries) and the pure preprocessing removers. Uses the suite's
neutralized nltk (see conftest) — the untrained punkt tokenizer matches prod.
"""
from vox_biblios.core.text_processor import TextProcessor


def _processor(max_size=10_000):
    return TextProcessor(max_chunk_size=max_size)


# --- chunk() -----------------------------------------------------------------

def test_chunk_empty_returns_empty_list():
    assert _processor().chunk("") == []


def test_chunk_short_text_single_chunk():
    chunks = _processor(max_size=1000).chunk("One sentence. Two sentence.")
    assert len(chunks) == 1
    assert chunks[0] == "One sentence. Two sentence."


def test_chunk_never_exceeds_max_size():
    # Many short sentences that must be split across several chunks.
    text = " ".join(f"Sentence number {i} here." for i in range(200))
    max_size = 80
    chunks = _processor(max_size=max_size).chunk(text, max_size=max_size)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= max_size


def test_chunk_oversized_single_word_is_force_split():
    # A single token longer than max must still be broken to <= max (last resort).
    max_size = 20
    long_word = "x" * 105
    chunks = _processor(max_size=max_size).chunk(long_word, max_size=max_size)
    assert chunks
    for c in chunks:
        assert len(c) <= max_size
    assert "".join(chunks) == long_word


def test_chunk_max_size_arg_is_capped_by_processor_default():
    # chunk() uses min(max_size, processor default); the smaller wins.
    text = " ".join(f"Word{i} ok." for i in range(100))
    chunks = _processor(max_size=50).chunk(text, max_size=10_000)
    for c in chunks:
        assert len(c) <= 50


def test_chunk_preserves_all_words():
    text = " ".join(f"alpha{i}" for i in range(60)) + "."
    chunks = _processor(max_size=40).chunk(text, max_size=40)
    joined = " ".join(chunks)
    for i in range(60):
        assert f"alpha{i}" in joined


# --- preprocess() and pure removers -----------------------------------------

def test_remove_urls():
    p = _processor()
    out = p._remove_urls("See https://example.com/path and www.foo.org now.")
    assert "http" not in out
    assert "www." not in out
    assert "See" in out and "now." in out


def test_remove_numeric_citations():
    p = _processor()
    assert p._remove_citations("As shown [12] and also [1, 2] here.") == \
        "As shown  and also  here."


def test_remove_author_year_citations():
    p = _processor()
    out = p._remove_citations("The claim (Smith, 2020) holds.")
    assert "Smith" not in out
    assert "2020" not in out


def test_remove_long_numbers():
    p = _processor()
    assert p._remove_long_numbers("call 12345678 today") == "call  today"
    # short numbers survive
    assert p._remove_long_numbers("only 1234 here") == "only 1234 here"


def test_remove_garbage_lines_drops_tables_and_separators():
    p = _processor()
    text = "Real prose here.\n----------\n| a | b |\nPage 12\nMore prose."
    out = p._remove_garbage_lines(text)
    assert "Real prose here." in out
    assert "More prose." in out
    assert "----------" not in out
    assert "| a | b |" not in out
    assert "Page 12" not in out


def test_remove_garbage_keeps_blank_lines_for_structure():
    p = _processor()
    text = "Para one.\n\nPara two."
    assert p._remove_garbage_lines(text) == text


def test_remove_bibliography_strips_trailing_references():
    p = _processor()
    body = "\n".join(["Intro paragraph."] * 10)
    text = body + "\n\nReferences\n\nSmith, J. (2020). A book. Publisher."
    out = p._remove_bibliography(text)
    assert "Intro paragraph." in out
    assert "Smith, J." not in out
    assert "References" not in out


def test_preprocess_is_idempotent_on_clean_text():
    p = _processor()
    clean = "A clean sentence. Another clean sentence."
    once = p.preprocess(clean)
    assert p.preprocess(once) == once


def test_preprocess_normalizes_whitespace_and_punctuation_spacing():
    p = _processor()
    out = p.preprocess("Word   with [12] spaces .")
    assert "   " not in out
    assert " ." not in out
