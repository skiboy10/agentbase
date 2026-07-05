"""
Regression tests for FileIndexer finalize behavior (#175, #129).

Before the fix, FileIndexer.index() and index_new_files() finalized by
directly assigning Source fields and unconditionally stamping
``status = "indexed"`` — bypassing BaseIndexer._finalize_indexing() and its
zero-output guards. A re-index whose every file failed after extraction
(issue #129: "Complete: 0 files, 1 pages, 0 chunks") therefore reported
success while the recreated Qdrant collection sat empty, silently destroying
previously-good indexed content. The same bypass skipped the freshness
recompute and produced inconsistent Source counter writes (#175).

These tests drive FileIndexer.index() with the heavy dependencies
(extraction, embedding, Qdrant setup) monkeypatched, and assert the finalize
contract: failures flip status to "error", successes populate chunk_count.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source
from app.services.ingestion.indexers.file import FileIndexer


async def _make_file_source(db: AsyncSession) -> Source:
    src = Source(
        id=str(uuid.uuid4()),
        name="Finalize Test PDF",
        source_type="file",
        source_path="/app/uploads/finalize-test.pdf",
        status="pending",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:4b",
        embedding_dimensions=1024,
        collection_name=f"test_finalize_{uuid.uuid4().hex[:8]}",
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return src


def _stub_indexer(indexer: FileIndexer, monkeypatch, extract_result) -> None:
    """Monkeypatch everything around the finalize logic under test."""
    files = [{"path": "/app/uploads/finalize-test.pdf", "original_name": "finalize-test.pdf"}]
    monkeypatch.setattr(indexer, "_get_files_to_index", lambda source: files)
    monkeypatch.setattr(
        indexer, "_get_embedding_config", AsyncMock(return_value=("ollama", "qwen3-embedding:4b", 1024))
    )
    monkeypatch.setattr(indexer.embedding_registry, "get_provider", lambda name: object())
    monkeypatch.setattr(indexer, "_store_embedding_config", AsyncMock())
    monkeypatch.setattr(indexer, "_setup_collection", AsyncMock())
    monkeypatch.setattr(indexer, "_ensure_collection_exists", AsyncMock())
    monkeypatch.setattr(indexer, "_setup_indexing_logs", AsyncMock())
    monkeypatch.setattr(indexer, "_get_log_for_file", AsyncMock(return_value=None))
    monkeypatch.setattr(
        indexer,
        "_build_enrichment_config",
        lambda source: SimpleNamespace(enabled=False, document_type_detection=False),
    )
    monkeypatch.setattr(indexer, "_extract_file_content", AsyncMock(return_value=extract_result))
    monkeypatch.setattr(
        indexer, "_process_embedding_batch", AsyncMock(return_value=(1, 1024))
    )


class TestFileIndexerFinalize:
    @pytest.mark.asyncio
    async def test_all_files_failed_flips_status_to_error(
        self, db_session: AsyncSession, monkeypatch
    ):
        """#129: extraction succeeded but the file later failed → the source
        must NOT report "indexed" with 0 chunks; the guard flips it to error."""
        src = await _make_file_source(db_session)
        indexer = FileIndexer(db_session)
        # Extraction "succeeds" with a page but empty text → the empty-text
        # guard raises, the file fails, successful_files stays 0.
        _stub_indexer(indexer, monkeypatch, extract_result=("   ", "title", 1))

        await indexer.index(src)

        assert src.status == "error"
        assert src.chunk_count == 0
        assert src.error_message is not None

    @pytest.mark.asyncio
    async def test_successful_index_populates_chunk_count(
        self, db_session: AsyncSession, monkeypatch
    ):
        """#175: the finalize path must populate Source.chunk_count."""
        src = await _make_file_source(db_session)
        indexer = FileIndexer(db_session)
        _stub_indexer(indexer, monkeypatch, extract_result=("word " * 500, "title", 3))

        await indexer.index(src)

        assert src.status == "indexed"
        assert src.error_message is None
        assert src.document_count == 1
        assert src.chunk_count > 0
        assert "Complete:" in src.progress_message

    @pytest.mark.asyncio
    async def test_index_new_files_accumulates_counts(
        self, db_session: AsyncSession, monkeypatch
    ):
        """Incremental indexing must accumulate counters through the same
        finalize contract instead of overwriting them."""
        src = await _make_file_source(db_session)
        src.status = "indexed"
        src.document_count = 2
        src.chunk_count = 10
        await db_session.commit()

        indexer = FileIndexer(db_session)
        _stub_indexer(indexer, monkeypatch, extract_result=("word " * 500, "title", 1))

        new_files = [{"path": "/app/uploads/finalize-test.pdf", "original_name": "finalize-test.pdf"}]
        await indexer.index_new_files(src, new_files)

        assert src.status == "indexed"
        assert src.document_count == 3
        assert src.chunk_count > 10
