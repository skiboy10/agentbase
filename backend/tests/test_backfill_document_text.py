"""
Unit tests for the #100 document-text repair script's stitch logic.

``stitch_chunks`` reassembles a document from splitter chunks that repeat
``chunk_overlap`` characters at their boundaries; the overlap must be emitted
exactly once, out-of-order input must be re-ordered by chunk_index, and
non-contiguous chunks fall back to a paragraph join.

Fixtures use non-repeating text: with periodic content a suffix/prefix scan
can legitimately match a longer window than the real splitter overlap, which
is a property of the text, not a bug in the stitcher.
"""
from scripts.backfill_document_text import stitch_chunks

# 1000 chars of non-repeating text ("0000 0001 0002 ...").
TEXT = "".join(f"{i:04d} " for i in range(200))


def test_overlapping_chunks_deduplicate_boundary():
    a, b = TEXT[:400], TEXT[300:800]  # 100-char overlap
    assert stitch_chunks([(0, a), (1, b)]) == TEXT[:800]


def test_chunks_reordered_by_index():
    parts = [(1, TEXT[200:400]), (0, TEXT[:250]), (2, TEXT[350:500])]
    assert stitch_chunks(parts) == TEXT[:500]


def test_non_contiguous_chunks_join_as_paragraphs():
    result = stitch_chunks([(0, "first section"), (1, "unrelated section")])
    assert result == "first section\n\nunrelated section"


def test_empty_and_single():
    assert stitch_chunks([]) == ""
    assert stitch_chunks([(0, "only")]) == "only"
