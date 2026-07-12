"""
Directory indexer for local file directories.

Handles indexing of local directories containing documents (PDF, PPTX, DOCX, MD, TXT).
Supports Tika-based extraction and enrichment pipeline (text cleaning + LLM classification).
"""
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path

from qdrant_client.models import Filter, FieldCondition, MatchValue
import structlog

from app.models import Source
from app.services.ingestion.enrichment import EnrichmentConfig, EnrichmentService

from ..path_utils import compute_folder_ancestors, normalise_excludes, path_under
from .base import BaseIndexer
from .file_extraction import extract_file_text, sanitize_text
from .tika import extract_text_with_tika, TIKA_SUPPORTED_EXTENSIONS

logger = structlog.get_logger()


class DirectoryIndexer(BaseIndexer):
    """Indexer for local directories of documents."""

    SUPPORTED_EXTENSIONS = {".md", ".txt", ".html", ".json", ".pdf", ".pptx", ".docx"}

    def __init__(self, db):
        super().__init__(db)
        self._enrichment_service = EnrichmentService()

    async def index(self, source: Source) -> None:
        """Index a local directory of documents with embeddings.

        KB-aware mode (source bound to 1+ libraries):
        - Uses primary library's collection + embedding config (all bound
          libraries share the same model by contract)
        - Creates Document records in Postgres per library
        - Skips unchanged files (content_hash comparison against primary library)
        - Adds document_id, library_id to chunk payloads
        - Fans out chunks to all bound libraries' Qdrant collections

        Legacy mode (no library bindings): behaves exactly as before.
        """
        if getattr(source, "parent_source_id", None):
            # Sub-sources are views over a root's chunks; they do not run their
            # own indexing path. Surfacing this as an error catches misuse from
            # the API/MCP layer before it reaches Qdrant.
            raise ValueError(
                "Cannot index a sub-source directly — index its parent root instead"
            )

        path = Path(source.source_path)
        if not path.exists():
            raise ValueError(f"Directory not found: {source.source_path}")

        # Pre-canonicalise watcher-level excludes so we can prune the walk.
        path_excludes = normalise_excludes(getattr(source, "path_excludes", None))

        # Load all libraries this source belongs to
        await self._load_kb_for_source(source)
        kbs = self._get_kbs(source)
        kb_aware = bool(kbs)
        primary_kb = kbs[0] if kbs else None

        emb_provider, emb_model, vector_size = await self._get_embedding_config(source)

        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")

        # Primary collection is always the source's own (what search reads);
        # bound libraries receive mirror copies.
        collection_name = self._get_collection_for_source(source)
        mirror_targets: list[tuple[str, str]] = self._get_library_mirror_collections(source)

        logger.info(
            "Starting directory indexing",
            source_id=source.id,
            path=source.source_path,
            provider=emb_provider,
            model=emb_model,
            kb_aware=kb_aware,
            collection=collection_name,
        )

        await self._store_embedding_config(source, emb_provider, emb_model, vector_size)

        if kb_aware:
            await self._ensure_collection_exists(collection_name, vector_size)
            for mirror_coll, _ in mirror_targets:
                await self._ensure_collection_exists(mirror_coll, vector_size)
        else:
            await self._setup_collection(collection_name, vector_size)

        text_splitter = self._get_text_splitter()
        enrich_cfg = self._build_enrichment_config(source)

        # Document service used only for the unchanged-skip lookup (the
        # actual upsert is delegated to BaseIndexer._upsert_kb_documents).
        doc_service = None
        if kb_aware:
            from app.services.library import DocumentService
            doc_service = DocumentService(self.db)

        def _is_excluded(fp: Path) -> bool:
            if not path_excludes:
                return False
            return any(path_under(fp, ex) for ex in path_excludes)

        files_to_process = [
            f for f in path.rglob("*")
            if f.suffix.lower() in self.SUPPORTED_EXTENSIONS
            and f.is_file()
            and not _is_excluded(f)
        ]
        total_files = len(files_to_process)

        source.progress_total = total_files
        source.progress = 0
        source.progress_message = f"Found {total_files} files to index"
        source.progress_updated_at = datetime.utcnow()
        await self.db.flush()

        doc_count = 0
        chunk_count = 0
        skipped_count = 0
        dimensions_captured = False
        batch_chunks = []
        batch_metadata = []

        # Per-file timeout: skip files that hang during extraction or embedding
        FILE_TIMEOUT_SECONDS = 180  # 3 minutes per file

        for file_path in files_to_process:
            try:
                ext = file_path.suffix.lower()
                filename = file_path.name
                document_id = self._generate_document_id(source.id, str(file_path)) if kb_aware else None

                # Extract text: Tika first for supported types, then fallback
                try:
                    content = await asyncio.wait_for(
                        self._extract_content(file_path, ext),
                        timeout=FILE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning("File extraction timed out, skipping",
                                   file=str(file_path), timeout=FILE_TIMEOUT_SECONDS)
                    await self._update_progress(source, doc_count + 1, f"Timeout: {filename}")
                    continue
                if not content or not content.strip():
                    logger.warning("Empty content, skipping", file=str(file_path))
                    await self._update_progress(source, doc_count + 1, f"Skipped (empty): {filename}")
                    continue

                content_hash = hashlib.sha256(content.encode()).hexdigest()

                # KB-aware: check if document already exists in primary library
                # and is unchanged. Mirror libraries inherit the skip.
                if kb_aware and doc_service and primary_kb:
                    existing = await doc_service.get_document_by_document_id(
                        primary_kb.id, document_id
                    )
                    if existing and existing.content_hash == content_hash:
                        skipped_count += 1
                        await self._update_progress(source, doc_count + 1, f"Unchanged: {filename}")
                        continue
                    # If changed, delete old chunks from all library collections
                    if existing:
                        for coll in [collection_name, *[m[0] for m in mirror_targets]]:
                            try:
                                self.client.delete(
                                    collection_name=coll,
                                    points_selector=Filter(must=[
                                        FieldCondition(key="document_id", match=MatchValue(value=document_id))
                                    ]),
                                )
                            except Exception as e:
                                logger.warning("Failed to delete stale chunks",
                                               document_id=document_id, collection=coll, error=str(e))

                # Enrichment: text cleaning + classification
                classification_payload = {}
                doc_type = "standard"
                enrichment_fields: dict = {}
                if enrich_cfg.enabled or enrich_cfg.document_type_detection:
                    enrich_result = await self._enrichment_service.enrich(
                        text=content,
                        filename=filename,
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

                # Split and prepare chunks
                chunks = text_splitter.split_text(content)
                relative_path = str(file_path.relative_to(path))
                folder = str(file_path.parent.relative_to(path)) if file_path.parent != path else ""

                # Pre-compute canonical folder_ancestors once per file — every
                # chunk from this file shares the same ancestor list.
                folder_ancestors = compute_folder_ancestors(file_path, root=path)

                for i, chunk in enumerate(chunks):
                    chunk_id = hashlib.md5(f"{file_path}:{i}".encode()).hexdigest()

                    nested_meta = {
                        "file_type": ext.lstrip("."),
                        "document_type": doc_type,
                        "folder": folder,
                    }
                    if classification_payload:
                        for key, val in classification_payload.items():
                            nested_meta[key] = val

                    meta = {
                        "id": chunk_id,
                        "source": relative_path,
                        "source_id": source.id,
                        "chunk_index": i,
                        "title": file_path.stem,
                        "metadata": nested_meta,
                        "folder_ancestors": folder_ancestors,
                    }
                    # KB-aware: add document_id and primary library_id to payload
                    if kb_aware and document_id and primary_kb:
                        meta["document_id"] = document_id
                        meta["library_id"] = primary_kb.id

                    batch_metadata.append(meta)
                    batch_chunks.append(chunk)

                    if len(batch_chunks) >= self.BATCH_SIZE:
                        _, actual_dims = await asyncio.wait_for(
                            self._process_embedding_batch(
                                collection_name, batch_chunks, batch_metadata,
                                emb_provider, emb_model,
                                mirror_targets=mirror_targets or None,
                            ),
                            timeout=300,  # 5 min for a batch of 50 chunks
                        )
                        if not dimensions_captured and actual_dims:
                            await self._update_embedding_dimensions(source, actual_dims)
                            dimensions_captured = True
                        chunk_count += len(batch_chunks)
                        source.document_count = doc_count
                        source.chunk_count = chunk_count
                        source.progress = doc_count
                        source.progress_message = f"Indexing: {doc_count}/{total_files} files, {chunk_count} chunks"
                        source.progress_updated_at = datetime.utcnow()
                        await self.db.commit()
                        batch_chunks = []
                        batch_metadata = []

                # Persist per-source DocumentContent (raw text + classification)
                # so re-embedding and taxonomy coverage analytics work. Keyed by
                # absolute path — the same key the directory watcher uses.
                await self._save_scraped_content(
                    source=source,
                    url=str(file_path),
                    title=file_path.stem,
                    content=content,
                    file_path=str(file_path),
                    file_type=ext.lstrip("."),
                    document_type=doc_type,
                    **enrichment_fields,
                )

                # KB-aware: create/update Document records for every library
                # this source belongs to (one row per library).
                if kb_aware:
                    await self._upsert_kb_documents(
                        source=source,
                        kbs=kbs,
                        document_id=document_id,
                        title=file_path.stem,
                        full_text=content,
                        content_hash=content_hash,
                        file_path=str(file_path),
                        file_type=ext.lstrip("."),
                        document_type=doc_type,
                        classification=classification_payload or None,
                        chunk_count=len(chunks),
                    )

                doc_count += 1
                await self._update_progress(source, doc_count, f"Processing: {filename}")
                logger.info("Processed file", file=filename, chunks=len(chunks), doc_type=doc_type,
                            classified=bool(classification_payload), kb_aware=kb_aware)

            except Exception as e:
                logger.warning("Failed to process file", file=str(file_path), error=str(e))
                await self._update_progress(source, doc_count + 1, f"Failed: {file_path.name}")
                batch_chunks = []
                batch_metadata = []

        # Process remaining batch
        if batch_chunks:
            try:
                _, actual_dims = await asyncio.wait_for(
                    self._process_embedding_batch(
                        collection_name, batch_chunks, batch_metadata,
                        emb_provider, emb_model,
                        mirror_targets=mirror_targets or None,
                    ),
                    timeout=300,
                )
                if not dimensions_captured and actual_dims:
                    await self._update_embedding_dimensions(source, actual_dims)
                chunk_count += len(batch_chunks)
                source.document_count = doc_count
                source.chunk_count = chunk_count
                await self.db.commit()
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("Final embedding batch failed", error=str(e),
                               dropped_chunks=len(batch_chunks))

        await self._finalize_indexing(
            source, doc_count, chunk_count, total_files, item_type="documents"
        )

        logger.info(
            "Directory indexing complete",
            source_id=source.id,
            documents=doc_count,
            chunks=chunk_count,
            skipped=skipped_count,
            kb_aware=kb_aware,
            enrichment=enrich_cfg.enabled,
        )

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Kept for backward compatibility — delegates to file_extraction.sanitize_text."""
        return sanitize_text(text)

    async def _extract_content(self, file_path: Path, ext: str) -> str | None:
        """Extract text from a file via the shared extractor."""
        return await extract_file_text(file_path, ext)

    def _build_enrichment_config(self, source: Source) -> EnrichmentConfig:
        """Build enrichment config from source settings."""
        return EnrichmentConfig(
            enabled=getattr(source, 'enrichment_enabled', False),
            taxonomy_id=getattr(source, 'enrichment_taxonomy_id', None),
            classification_provider=getattr(source, 'enrichment_model', '').split('/')[0] if getattr(source, 'enrichment_model', None) else 'ollama',
            classification_model=getattr(source, 'enrichment_model', None) or 'qwen2.5:7b-instruct',
            document_type_detection=True,
        )
