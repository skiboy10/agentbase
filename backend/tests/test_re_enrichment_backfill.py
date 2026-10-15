"""Unit tests for re-enrichment DocumentContent matching/merge (#26)."""
from uuid import uuid4

from app.models import DocumentContent
from app.services.ingestion.re_enrichment import (
    _basename,
    _build_document_content_index,
    _match_document_content,
    _merge_classifications,
)


def _dc(**kwargs) -> DocumentContent:
    defaults = dict(
        id=str(uuid4()),
        source_id=str(uuid4()),
        url="/tmp/acme/docs/guide.md",
        raw_content="hello",
        content_hash="abc",
        content_length=5,
    )
    defaults.update(kwargs)
    return DocumentContent(**defaults)


def test_basename_posix_and_windows():
    assert _basename("/tmp/acme/docs/guide.md") == "guide.md"
    assert _basename(r"C:\acme\docs\guide.md") == "guide.md"


def test_index_matches_relative_chunk_source():
    row = _dc(url="/data/library/product/guide.md", file_path="/data/library/product/guide.md")
    index = _build_document_content_index([row])

    # Directory indexer stores relative path in chunk payload "source"
    hit = _match_document_content(index, "product/guide.md", {})
    assert hit is not None
    assert hit.id == row.id

    hit2 = _match_document_content(index, "guide.md", {})
    assert hit2 is not None
    assert hit2.id == row.id


def test_index_matches_url_source_exactly():
    row = _dc(url="https://docs.example.com/page", file_path=None)
    index = _build_document_content_index([row])
    hit = _match_document_content(index, "https://docs.example.com/page", {})
    assert hit is not None
    assert hit.id == row.id


def test_merge_classifications_majority_vote():
    merged = _merge_classifications([
        {"platforms": ["AcmeCRM"], "doc_category": "guide"},
        {"platforms": ["AcmeCRM"], "doc_category": "guide"},
        {"platforms": ["AcmeERP"], "doc_category": "guide"},
    ])
    assert merged["platforms"] == ["AcmeCRM"]
    assert merged["doc_category"] == "guide"


def test_merge_single_classification():
    merged = _merge_classifications([{"platforms": ["AcmeCRM"]}])
    assert merged == {"platforms": ["AcmeCRM"]}
