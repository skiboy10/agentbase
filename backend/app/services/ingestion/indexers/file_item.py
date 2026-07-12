"""
Single-file (item) indexer for incremental re-index inside a directory source.

Used by the directory watcher when a watched file changes. Instead of
re-indexing the entire source (which can mean tens of thousands of chunks for
one PDF touch), this indexer:

  1. Extracts text for exactly one file.
  2. Compares its content_hash against the stored DocumentContent.
  3. If changed, deletes that file's prior chunks from every Qdrant collection
     the parent source is bound to and writes fresh chunks.
  4. Upserts the per-source DocumentContent and per-library Document rows.

The full-source DirectoryIndexer remains the path for first-time indexing and
explicit re-index jobs.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from qdrant_client.models import Filter, FieldCondition, MatchValue
from sqlalchemy import select
import structlog

from app.models import Source

from ..enrichment import EnrichmentConfig, EnrichmentService
from ..path_utils import compute_folder_ancestors, normalise_excludes, path_under
from .base import BaseIndexer
from .file_extraction import extract_file_text

logger = structlog.get_logger()


# Same default file-type set as DirectoryIndexer. Keep them aligned so what the
# directory walker indexes is exactly what the watcher will re-index per-file.
SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".json", ".pdf", ".pptx", ".docx"}

# Per-file extraction safety net (matches DirectoryIndexer).
FILE_TIMEOUT_SECONDS = 180


class FileItemIndexer(BaseIndexer):
    """Indexer that processes one file at a time inside an existing directory source."""

    def __init__(self, db):
        super().__init__(db)
        self._enrichment_service = EnrichmentService()

    async def index_one(self, source: Source, file_path: str) -> dict:
        """Index a single file under ``source.source_path``.

        Returns a stats dict::

            {
                "status": "indexed" | "skipped_unchanged" | "skipped_unsupported"
                          | "skipped_empty" | "skipped_outside_root" | "skipped_missing",
                "file_path": str,
                "chunk_count": int,            # chunks written this call (0 if skipped)
                "deleted_chunks": int,         # prior chunks removed before re-write
            }

        Never raises for routine "skip" cases — they're reported in ``status``.
        Hard errors (extraction failure, embedding API failure, etc.) propagate.
        """
        if source.source_type != "directory":
            raise ValueError(
                f"FileItemIndexer only supports directory sources, got {source.source_type}"
            )
        if getattr(source, "parent_source_id", None):
            # Defensive — Phase 2 introduces sub-sources; they have no own chunks.
            raise ValueError("Cannot re-index a file under a sub-source; use the root source id")

        root = Path(source.source_path)
        fp = Path(file_path)

        if not fp.exists():
            logger.info("File no longer exists, nothing to index", file=file_path)
            return {
                "status": "skipped_missing",
                "file_path": file_path,
                "chunk_count": 0,
                "deleted_chunks": 0,
            }

        try:
            fp.resolve().relative_to(root.resolve())
        except ValueError:
            logger.warning(
                "File outside source root, refusing",
                file=file_path,
                root=str(root),
                source_id=source.id,
            )
            return {
                "status": "skipped_outside_root",
                "file_path": file_path,
                "chunk_count": 0,
                "deleted_chunks": 0,
            }

        ext = fp.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return {
                "status": "skipped_unsupported",
                "file_path": file_path,
                "chunk_count": 0,
                "deleted_chunks": 0,
            }

        # Respect root-level path_excludes — if this file lives under any
        # excluded prefix, don't index it (matches the directory walker).
        path_excludes = normalise_excludes(getattr(source, "path_excludes", None))
        if path_excludes and any(path_under(fp, ex) for ex in path_excludes):
            return {
                "status": "skipped_unsupported",
                "file_path": file_path,
                "chunk_count": 0,
                "deleted_chunks": 0,
            }

        # Load libraries this source belongs to + resolve embedding model.
        await self._load_kb_for_source(source)
        kbs = self._get_kbs(source)
        kb_aware = bool(kbs)
        primary_kb = kbs[0] if kbs else None

        emb_provider, emb_model, vector_size = await self._get_embedding_config(source)
        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")
        await self._store_embedding_config(source, emb_provider, emb_model, vector_size)

        collection_name = self._get_collection_for_source(source)
        mirror_targets: list[tuple[str, str]] = self._get_library_mirror_collections(source)
        all_collections = [collection_name, *(c for c, _ in mirror_targets)]

        # Make sure all target collections exist before we delete + upsert.
        await self._setup_collection(collection_name, vector_size, recreate=False)
        for mirror_coll, _ in mirror_targets:
            await self._setup_collection(mirror_coll, vector_size, recreate=False)

        # Extract content with timeout (mirrors DirectoryIndexer behaviour).
        try:
            content = await asyncio.wait_for(
                extract_file_text(fp, ext),
                timeout=FILE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("File extraction timed out", file=file_path)
            return {
                "status": "skipped_empty",
                "file_path": file_path,
                "chunk_count": 0,
                "deleted_chunks": 0,
            }

        if not content or not content.strip():
            return {
                "status": "skipped_empty",
                "file_path": file_path,
                "chunk_count": 0,
                "deleted_chunks": 0,
            }

        content_hash = self._compute_content_hash(content)

        # Unchanged short-circuit: compare against stored DocumentContent.
        from app.models import ScrapedContent  # alias of DocumentContent
        stmt = select(ScrapedContent).where(
            ScrapedContent.source_id == source.id,
            ScrapedContent.url == file_path,
        )
        existing_doc = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing_doc and existing_doc.content_hash == content_hash:
            logger.debug("File unchanged, skipping re-index", file=file_path)
            return {
                "status": "skipped_unchanged",
                "file_path": file_path,
                "chunk_count": existing_doc and existing_doc.content_length and 0 or 0,
                "deleted_chunks": 0,
            }

        # Delete prior chunks for this file from every collection. The directory
        # write path stores the file's path relative to source root in the
        # "source" payload; match the same key.
        try:
            chunk_key = str(fp.relative_to(root))
        except ValueError:
            chunk_key = str(fp)

        deleted_chunks = 0
        for coll in all_collections:
            try:
                # Count first for diagnostics. exact=True is required:
                # exact=False uses segment heuristics that overcount by
                # orders of magnitude when the field has no keyword index
                # (or the index hasn't caught up yet), corrupting the
                # Source.chunk_count value we derive from this count.
                count_res = self.client.count(
                    collection_name=coll,
                    count_filter=Filter(must=[
                        FieldCondition(key="source", match=MatchValue(value=chunk_key))
                    ]),
                    exact=True,
                )
                deleted_chunks += count_res.count or 0
                self.client.delete(
                    collection_name=coll,
                    points_selector=Filter(must=[
                        FieldCondition(key="source", match=MatchValue(value=chunk_key))
                    ]),
                )
            except Exception as e:
                logger.warning(
                    "Failed to delete prior chunks for file",
                    file=file_path,
                    collection=coll,
                    error=str(e),
                )

        # Optional enrichment
        classification_payload: dict = {}
        doc_type = "standard"
        enrichment_fields: dict = {}
        enrich_cfg = self._build_enrichment_config(source)
        if enrich_cfg.enabled or enrich_cfg.document_type_detection:
            enrich_result = await self._enrichment_service.enrich(
                text=content,
                filename=fp.name,
                config=enrich_cfg,
                db=self.db,
            )
            content = enrich_result["cleaned_text"]
            doc_type = enrich_result["document_type"]
            if enrich_result.get("classification"):
                classification_payload = enrich_result["classification"]
                enrichment_fields = {
                    "classification": classification_payload,
                    "classification_method": enrich_result.get("classification_method"),
                    "taxonomy_id": enrich_result.get("taxonomy_id"),
                    "classification_taxonomy_version": enrich_result.get("taxonomy_version"),
                }
            # Recompute hash after enrichment changes the cleaned text
            content_hash = self._compute_content_hash(content)

        # Chunk + embed in batches.
        splitter = self._get_text_splitter()
        chunks = splitter.split_text(content)
        if not chunks:
            return {
                "status": "skipped_empty",
                "file_path": file_path,
                "chunk_count": 0,
                "deleted_chunks": deleted_chunks,
            }

        relative_path = chunk_key
        folder = (
            str(fp.parent.relative_to(root))
            if fp.parent != root and fp.parent.is_relative_to(root)
            else ""
        )
        folder_ancestors = compute_folder_ancestors(fp, root=root)

        document_id = (
            self._generate_document_id(source.id, str(fp)) if kb_aware else None
        )

        written = 0
        dimensions_captured = False
        batch_chunks: list[str] = []
        batch_metadata: list[dict] = []

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{fp}:{i}".encode()).hexdigest()

            nested_meta = {
                "file_type": ext.lstrip("."),
                "document_type": doc_type,
                "folder": folder,
            }
            if classification_payload:
                for key, val in classification_payload.items():
                    nested_meta[key] = val

            meta: dict = {
                "id": chunk_id,
                "source": relative_path,
                "source_id": source.id,
                "chunk_index": i,
                "title": fp.stem,
                "metadata": nested_meta,
                "folder_ancestors": folder_ancestors,
            }
            if kb_aware and document_id and primary_kb:
                meta["document_id"] = document_id
                meta["library_id"] = primary_kb.id

            batch_chunks.append(chunk)
            batch_metadata.append(meta)

            if len(batch_chunks) >= self.BATCH_SIZE:
                _, actual_dims = await self._process_embedding_batch(
                    collection_name,
                    batch_chunks,
                    batch_metadata,
                    emb_provider,
                    emb_model,
                    mirror_targets=mirror_targets or None,
                )
                if not dimensions_captured and actual_dims:
                    await self._update_embedding_dimensions(source, actual_dims)
                    dimensions_captured = True
                written += len(batch_chunks)
                batch_chunks = []
                batch_metadata = []

        if batch_chunks:
            _, actual_dims = await self._process_embedding_batch(
                collection_name,
                batch_chunks,
                batch_metadata,
                emb_provider,
                emb_model,
                mirror_targets=mirror_targets or None,
            )
            if not dimensions_captured and actual_dims:
                await self._update_embedding_dimensions(source, actual_dims)
            written += len(batch_chunks)

        # Upsert the per-source DocumentContent row.
        await self._save_scraped_content(
            source=source,
            url=file_path,
            title=fp.stem,
            content=content,
            file_path=str(fp),
            file_type=ext.lstrip("."),
            document_type=doc_type,
            **enrichment_fields,
        )

        # Per-library Document rows.
        if kb_aware and document_id:
            await self._upsert_kb_documents(
                source=source,
                kbs=kbs,
                document_id=document_id,
                title=fp.stem,
                full_text=content,
                content_hash=content_hash,
                file_path=str(fp),
                file_type=ext.lstrip("."),
                document_type=doc_type,
                classification=classification_payload or None,
                chunk_count=written,
            )

        # Bump source aggregate counts. document_count is a soft estimate — we
        # don't know whether this file existed before from chunk_count alone,
        # so leave it untouched on update and only bump on first-time creation.
        if not existing_doc:
            source.document_count = (source.document_count or 0) + 1
        # Net delta in chunks: written - deleted_chunks (per-collection delete is
        # aggregated across libraries, so divide by collection count to estimate
        # the per-collection delta; we're best-effort here).
        per_coll_deleted = deleted_chunks // max(len(all_collections), 1)
        source.chunk_count = max(
            0,
            (source.chunk_count or 0) + written - per_coll_deleted,
        )
        source.last_indexed = datetime.utcnow()
        source.progress_message = f"Re-indexed file: {fp.name} ({written} chunks)"
        source.progress_updated_at = datetime.utcnow()
        await self.db.flush()

        logger.info(
            "Indexed single file",
            source_id=source.id,
            file=file_path,
            chunks_written=written,
            chunks_deleted=deleted_chunks,
        )

        return {
            "status": "indexed",
            "file_path": file_path,
            "chunk_count": written,
            "deleted_chunks": deleted_chunks,
        }

    def _build_enrichment_config(self, source: Source) -> EnrichmentConfig:
        """Mirror DirectoryIndexer._build_enrichment_config."""
        return EnrichmentConfig(
            enabled=getattr(source, "enrichment_enabled", False),
            taxonomy_id=getattr(source, "enrichment_taxonomy_id", None),
            classification_provider=(
                getattr(source, "enrichment_model", "").split("/")[0]
                if getattr(source, "enrichment_model", None) else "ollama"
            ),
            classification_model=getattr(source, "enrichment_model", None) or "qwen2.5:7b-instruct",
            document_type_detection=True,
        )
