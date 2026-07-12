"""
File indexer for PDF and text documents.

Handles indexing of uploaded files (PDF, TXT, MD), including multi-file sources.
Supports Tika-based extraction for PDF/PPTX/DOCX and enrichment pipeline
(text cleaning + LLM classification) when configured on the knowledge source.
"""
import aiofiles
import hashlib
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete
import structlog

from app.models import Source, IndexingLog
from app.services.ingestion.enrichment import EnrichmentConfig, EnrichmentService

from .base import BaseIndexer
from .tika import extract_text_with_tika, TIKA_SUPPORTED_EXTENSIONS

logger = structlog.get_logger()


class FileIndexer(BaseIndexer):
    """Indexer for file uploads - PDF, TXT, MD (supports multiple files per source)."""

    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.markdown', '.pptx', '.docx'}

    def __init__(self, db):
        super().__init__(db)
        self._enrichment_service = EnrichmentService()

    async def index(self, source: Source) -> None:
        """Index uploaded files with embeddings.

        Supports both:
        - Multi-file sources (selected_files JSON array)
        - Legacy single-file sources (source_path only)

        Extraction order for PDF/PPTX/DOCX:
        1. Tika (if available) for richer text extraction
        2. pypdf fallback for PDF if Tika unavailable
        """
        # Parse files from selected_files JSON or fall back to source_path
        files = self._get_files_to_index(source)
        if not files:
            raise ValueError("No files selected for indexing")

        total_files = len(files)

        # Load all libraries this source belongs to (KB-aware mode)
        await self._load_kb_for_source(source)
        kbs = self._get_kbs(source)
        kb_aware = bool(kbs)
        primary_kb = kbs[0] if kbs else None

        logger.info(
            "Starting multi-file indexing",
            source_id=source.id,
            file_count=total_files,
            kb_aware=kb_aware,
        )

        # Get embedding configuration
        emb_provider, emb_model, vector_size = await self._get_embedding_config(source)

        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")

        # Store embedding config on source
        await self._store_embedding_config(source, emb_provider, emb_model, vector_size)

        # Primary collection: KB collection if bound, else source's own
        collection_name = self._get_collection_for_source(source)
        # Mirror targets for additional libraries
        mirror_targets: list[tuple[str, str]] = self._get_library_mirror_collections(source)

        if kb_aware:
            await self._ensure_collection_exists(collection_name, vector_size)
            for mirror_coll, _ in mirror_targets:
                await self._ensure_collection_exists(mirror_coll, vector_size)
        else:
            await self._setup_collection(collection_name, vector_size)

        # Clear existing indexing logs and create new ones for each file
        await self._setup_indexing_logs(source, files)

        text_splitter = self._get_text_splitter()

        # Initialize progress tracking
        source.progress_total = total_files
        source.progress = 0
        source.progress_message = f"Processing {total_files} file(s)..."
        source.progress_updated_at = datetime.utcnow()
        await self.db.flush()

        total_chunks = 0
        total_pages = 0
        successful_files = 0
        dimensions_captured = False

        # Process each file
        for file_idx, file_info in enumerate(files):
            file_path = file_info["path"]
            original_name = file_info.get("original_name", Path(file_path).name)

            # Update log status to processing
            log = await self._get_log_for_file(source.id, file_path)
            if log:
                log.status = "processing"
                await self.db.flush()

            try:
                # Validate file type
                ext = Path(file_path).suffix.lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    raise ValueError(f"Unsupported file type '{ext}': {original_name}. Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}")

                # Extract content based on file type
                source.progress_message = f"Extracting: {original_name} ({file_idx + 1}/{total_files})"
                source.progress_updated_at = datetime.utcnow()
                await self.db.flush()

                file_text, file_title, file_pages = await self._extract_file_content(
                    file_path, original_name, ext
                )
                if file_text is None or not file_text.strip():
                    # Empty extraction must fail loudly: silently producing 0
                    # chunks lets a re-index wipe previously-good content (#129).
                    raise ValueError(f"Extracted no text from: {original_name}")

                total_pages += file_pages

                # --- Enrichment: text cleaning + classification ---
                classification_payload: dict = {}
                doc_type = "standard"
                enrichment_fields: dict = {}
                enrich_cfg = self._build_enrichment_config(source)
                if enrich_cfg.enabled or enrich_cfg.document_type_detection:
                    enrich_result = await self._enrichment_service.enrich(
                        text=file_text,
                        filename=original_name,
                        config=enrich_cfg,
                        db=self.db,
                    )
                    file_text = enrich_result["cleaned_text"]
                    doc_type = enrich_result["document_type"]
                    if enrich_result.get("classification"):
                        classification_payload = enrich_result["classification"]
                        enrichment_fields = {
                            "classification": classification_payload,
                            "classification_method": enrich_result.get("classification_method"),
                            "taxonomy_id": enrich_result.get("taxonomy_id"),
                            "classification_taxonomy_version": enrich_result.get("taxonomy_version"),
                        }

                # Split text into chunks
                chunks = text_splitter.split_text(file_text)
                file_chunk_count = len(chunks)
                logger.info(
                    "Processing file",
                    source_id=source.id,
                    file=original_name,
                    pages=file_pages,
                    chunks=file_chunk_count,
                    document_type=doc_type,
                )

                # Embed chunks in batches
                title = file_title or Path(file_path).stem
                batch_chunks = []
                batch_metadata = []

                # KB-aware: stable document_id from (source_id, file_path)
                document_id = (
                    self._generate_document_id(source.id, file_path) if kb_aware else None
                )

                for i, chunk in enumerate(chunks):
                    chunk_id = hashlib.md5(f"{file_path}:{i}".encode()).hexdigest()

                    batch_chunks.append(chunk)
                    meta: dict = {
                        "id": chunk_id,
                        "source": Path(file_path).name,  # Used for filtering in Qdrant
                        "source_id": source.id,
                        "chunk_index": i,
                        "title": title,
                        "original_name": original_name,
                        "document_type": doc_type,
                    }
                    # Inject classification into chunk metadata for Qdrant payload
                    if classification_payload:
                        meta["classification"] = classification_payload
                    if kb_aware and document_id and primary_kb:
                        meta["document_id"] = document_id
                        meta["library_id"] = primary_kb.id
                    batch_metadata.append(meta)

                    if len(batch_chunks) >= self.BATCH_SIZE:
                        _, actual_dims = await self._process_embedding_batch(
                            collection_name,
                            batch_chunks, batch_metadata,
                            emb_provider, emb_model,
                            mirror_targets=mirror_targets or None,
                        )

                        if not dimensions_captured and actual_dims:
                            await self._update_embedding_dimensions(source, actual_dims)
                            dimensions_captured = True

                        batch_chunks = []
                        batch_metadata = []

                # Process remaining batch
                if batch_chunks:
                    _, actual_dims = await self._process_embedding_batch(
                        collection_name,
                        batch_chunks, batch_metadata,
                        emb_provider, emb_model,
                        mirror_targets=mirror_targets or None,
                    )

                    if not dimensions_captured and actual_dims:
                        await self._update_embedding_dimensions(source, actual_dims)
                        dimensions_captured = True

                total_chunks += file_chunk_count
                successful_files += 1

                # Persist per-source DocumentContent (raw text + classification)
                # so re-embedding and taxonomy coverage analytics work.
                await self._save_scraped_content(
                    source=source,
                    url=file_path,
                    title=title,
                    content=file_text,
                    file_path=file_path,
                    file_type=ext.lstrip("."),
                    document_type=doc_type,
                    **enrichment_fields,
                )

                # KB-aware: upsert one Document per library this source is bound to
                if kb_aware and document_id:
                    content_hash = self._compute_content_hash(file_text or "")
                    await self._upsert_kb_documents(
                        source=source,
                        kbs=kbs,
                        document_id=document_id,
                        title=title,
                        full_text=file_text or "",
                        content_hash=content_hash,
                        file_path=file_path,
                        file_type=ext.lstrip("."),
                        document_type=doc_type,
                        classification=classification_payload or None,
                        chunk_count=file_chunk_count,
                    )

                # Update log status to done
                if log:
                    log.status = "done"
                    log.chunk_count = file_chunk_count
                    log.content_length = len(file_text)
                    log.updated_at = datetime.utcnow()

            except ValueError as e:
                logger.error("Failed to process file", file=original_name, error=str(e))
                if log:
                    log.status = "failed"
                    log.error_message = str(e)
                    log.updated_at = datetime.utcnow()

            except Exception as e:
                logger.error("Unexpected error processing file", file=original_name, error=str(e))
                if log:
                    log.status = "failed"
                    log.error_message = f"Unexpected error: {str(e)}"
                    log.updated_at = datetime.utcnow()

            # Update progress and commit to release row locks
            source.progress = file_idx + 1
            source.progress_message = f"Processed {file_idx + 1}/{total_files} files"
            source.progress_updated_at = datetime.utcnow()
            await self.db.commit()

        # Finalize through the base-class path so the zero-output guards
        # (all files failed / files ok but 0 chunks) flip status to "error"
        # instead of silently reporting "indexed", and next_refresh_at is
        # recomputed for the freshness policy (#175, #129).
        await self._finalize_indexing(
            source,
            doc_count=successful_files,
            chunk_count=total_chunks,
            total_items=total_files,
            failed_count=total_files - successful_files,
            item_type="files",
        )
        await self.db.commit()

        logger.info(
            "Multi-file indexing complete",
            source_id=source.id,
            files=successful_files,
            pages=total_pages,
            chunks=total_chunks,
            embedding_provider=emb_provider,
            embedding_model=emb_model,
        )

    async def index_new_files(self, source: Source, new_files: list[dict]) -> None:
        """Index only newly added files without recreating the collection.

        Appends to the existing Qdrant collection and indexing logs.
        Commits after each file to avoid holding row locks.
        """

        if not new_files:
            return

        # Same traversal guard as the full-index path — incremental payloads
        # arrive via the job queue and must not escape the upload directory.
        new_files = self._filter_safe_files(new_files, source.id)
        if not new_files:
            return

        total_files = len(new_files)
        logger.info(
            "Starting incremental file indexing",
            source_id=source.id,
            new_file_count=total_files,
        )

        # Use source's existing embedding config, fall back to global
        emb_provider = source.embedding_provider
        emb_model = source.embedding_model
        vector_size = source.embedding_dimensions

        if not emb_provider or not emb_model or not vector_size:
            emb_provider, emb_model, vector_size = await self._get_embedding_config(source)
            await self._store_embedding_config(source, emb_provider, emb_model, vector_size)

        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")

        # Load all libraries this source belongs to (KB-aware mode)
        await self._load_kb_for_source(source)
        kbs = self._get_kbs(source)
        kb_aware = bool(kbs)
        primary_kb = kbs[0] if kbs else None

        collection_name = self._get_collection_for_source(source)
        mirror_targets: list[tuple[str, str]] = self._get_library_mirror_collections(source)

        # Ensure all collections exist (don't recreate)
        await self._setup_collection(collection_name, vector_size, recreate=False)
        for mirror_coll, _ in mirror_targets:
            await self._setup_collection(mirror_coll, vector_size, recreate=False)

        # Create indexing logs only for new files (don't delete existing)
        for file_info in new_files:
            existing_log = await self._get_log_for_file(source.id, file_info["path"])
            if not existing_log:
                log = IndexingLog(
                    source_id=source.id,
                    url=file_info["path"],
                    status="pending",
                )
                self.db.add(log)

        source.progress_total = total_files
        source.progress = 0
        source.progress_message = f"Processing {total_files} new file(s)..."
        source.progress_updated_at = datetime.utcnow()
        await self.db.commit()

        text_splitter = self._get_text_splitter()
        new_chunks = 0
        new_pages = 0
        successful_files = 0

        for file_idx, file_info in enumerate(new_files):
            file_path = file_info["path"]
            original_name = file_info.get("original_name", Path(file_path).name)

            log = await self._get_log_for_file(source.id, file_path)
            if log:
                log.status = "processing"
                await self.db.flush()

            try:
                ext = Path(file_path).suffix.lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    raise ValueError(f"Unsupported file type '{ext}': {original_name}")

                source.progress_message = f"Extracting: {original_name} ({file_idx + 1}/{total_files})"
                source.progress_updated_at = datetime.utcnow()
                await self.db.flush()

                file_text, file_title, file_pages = await self._extract_file_content(
                    file_path, original_name, ext
                )
                if file_text is None or not file_text.strip():
                    # Empty extraction must fail loudly: silently producing 0
                    # chunks lets a re-index wipe previously-good content (#129).
                    raise ValueError(f"Extracted no text from: {original_name}")

                # --- Enrichment ---
                classification_payload: dict = {}
                doc_type = "standard"
                enrichment_fields: dict = {}
                enrich_cfg = self._build_enrichment_config(source)
                if enrich_cfg.enabled or enrich_cfg.document_type_detection:
                    enrich_result = await self._enrichment_service.enrich(
                        text=file_text,
                        filename=original_name,
                        config=enrich_cfg,
                        db=self.db,
                    )
                    file_text = enrich_result["cleaned_text"]
                    doc_type = enrich_result["document_type"]
                    if enrich_result.get("classification"):
                        classification_payload = enrich_result["classification"]
                        enrichment_fields = {
                            "classification": classification_payload,
                            "classification_method": enrich_result.get("classification_method"),
                            "taxonomy_id": enrich_result.get("taxonomy_id"),
                            "classification_taxonomy_version": enrich_result.get("taxonomy_version"),
                        }

                new_pages += file_pages
                chunks = text_splitter.split_text(file_text)
                file_chunk_count = len(chunks)

                title = file_title or Path(file_path).stem
                batch_chunks = []
                batch_metadata = []

                # KB-aware: stable document_id from (source_id, file_path)
                document_id = (
                    self._generate_document_id(source.id, file_path) if kb_aware else None
                )

                for i, chunk in enumerate(chunks):
                    chunk_id = hashlib.md5(f"{file_path}:{i}".encode()).hexdigest()
                    batch_chunks.append(chunk)
                    meta: dict = {
                        "id": chunk_id,
                        "source": Path(file_path).name,
                        "source_id": source.id,
                        "chunk_index": i,
                        "title": title,
                        "original_name": original_name,
                        "document_type": doc_type,
                    }
                    if classification_payload:
                        meta["classification"] = classification_payload
                    if kb_aware and document_id and primary_kb:
                        meta["document_id"] = document_id
                        meta["library_id"] = primary_kb.id
                    batch_metadata.append(meta)

                    if len(batch_chunks) >= self.BATCH_SIZE:
                        await self._process_embedding_batch(
                            collection_name, batch_chunks, batch_metadata,
                            emb_provider, emb_model,
                            mirror_targets=mirror_targets or None,
                        )
                        batch_chunks = []
                        batch_metadata = []

                if batch_chunks:
                    await self._process_embedding_batch(
                        collection_name, batch_chunks, batch_metadata,
                        emb_provider, emb_model,
                        mirror_targets=mirror_targets or None,
                    )

                new_chunks += file_chunk_count
                successful_files += 1

                # Persist per-source DocumentContent (raw text + classification)
                # so re-embedding and taxonomy coverage analytics work.
                await self._save_scraped_content(
                    source=source,
                    url=file_path,
                    title=title,
                    content=file_text,
                    file_path=file_path,
                    file_type=ext.lstrip("."),
                    document_type=doc_type,
                    **enrichment_fields,
                )

                # KB-aware: upsert Document for every bound library
                if kb_aware and document_id:
                    content_hash = self._compute_content_hash(file_text or "")
                    await self._upsert_kb_documents(
                        source=source,
                        kbs=kbs,
                        document_id=document_id,
                        title=title,
                        full_text=file_text or "",
                        content_hash=content_hash,
                        file_path=file_path,
                        file_type=ext.lstrip("."),
                        document_type=doc_type,
                        classification=classification_payload or None,
                        chunk_count=file_chunk_count,
                    )

                if log:
                    log.status = "done"
                    log.chunk_count = file_chunk_count
                    log.content_length = len(file_text)
                    log.updated_at = datetime.utcnow()

            except ValueError as e:
                logger.error("Failed to process file", file=original_name, error=str(e))
                if log:
                    log.status = "failed"
                    log.error_message = str(e)
                    log.updated_at = datetime.utcnow()

            except Exception as e:
                logger.error("Unexpected error processing file", file=original_name, error=str(e))
                if log:
                    log.status = "failed"
                    log.error_message = f"Unexpected error: {str(e)}"
                    log.updated_at = datetime.utcnow()

            # Commit after each file to release row locks
            source.progress = file_idx + 1
            source.progress_message = f"Processed {file_idx + 1}/{total_files} new files"
            source.progress_updated_at = datetime.utcnow()
            await self.db.commit()

        # Finalize — accumulate counts rather than overwrite, but go through
        # the base-class path so counters and guards stay consistent (#175).
        await self._finalize_indexing(
            source,
            doc_count=(source.document_count or 0) + successful_files,
            chunk_count=(source.chunk_count or 0) + new_chunks,
            total_items=total_files,
            failed_count=total_files - successful_files,
            item_type="files",
        )
        await self.db.commit()

        logger.info(
            "Incremental file indexing complete",
            source_id=source.id,
            new_files=successful_files,
            new_chunks=new_chunks,
        )

    def _get_files_to_index(self, source: Source) -> list[dict]:
        """Get list of files to index from source.

        Returns list of dicts with keys: path, original_name, size_bytes

        Path traversal guard: every resolved path must sit inside the configured
        upload directory.  Paths that escape the directory (e.g. via "../../etc/passwd")
        are dropped and logged as a security warning.
        """
        files = []

        # Try selected_files first (multi-file)
        if source.selected_files:
            try:
                files = json.loads(source.selected_files)
            except json.JSONDecodeError:
                pass

        # Fall back to source_path for legacy single-file sources
        if not files and source.source_path:
            files = [{
                "path": source.source_path,
                "original_name": Path(source.source_path).name,
                "size_bytes": 0,
            }]

        return self._filter_safe_files(files, source.id)

    def _filter_safe_files(self, files: list[dict], source_id: str) -> list[dict]:
        """Path traversal guard: keep only files inside the upload directory.

        Every resolved path must sit inside the configured upload directory.
        Paths that escape it (e.g. via "../../etc/passwd") are dropped and
        logged as a security warning.
        """
        from app.core.config import get_settings
        upload_root = Path(get_settings().upload_dir).resolve()

        safe_files = []
        for file_info in files:
            try:
                resolved = Path(file_info["path"]).resolve()
                resolved.relative_to(upload_root)  # raises ValueError if outside
                safe_files.append(file_info)
            except (KeyError, ValueError, TypeError):
                logger.warning(
                    "Path traversal attempt blocked — file path escapes upload directory",
                    source_id=source_id,
                    path=file_info.get("path") if isinstance(file_info, dict) else None,
                )

        return safe_files

    async def _setup_indexing_logs(
        self,
        source: Source,
        files: list[dict]
    ) -> None:
        """Clear existing logs and create pending entries for each file."""
        # Clear existing logs
        delete_stmt = delete(IndexingLog).where(IndexingLog.source_id == source.id)
        await self.db.execute(delete_stmt)

        # Create new pending entries
        for file_info in files:
            log = IndexingLog(
                source_id=source.id,
                url=file_info["path"],  # Reuse url field for file path
                status="pending",
            )
            self.db.add(log)

        await self.db.flush()

    async def _get_log_for_file(
        self,
        source_id: str,
        file_path: str
    ) -> IndexingLog | None:
        """Get the indexing log entry for a specific file."""
        from sqlalchemy import select

        stmt = select(IndexingLog).where(
            IndexingLog.source_id == source_id,
            IndexingLog.url == file_path
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _extract_file_content(
        self,
        file_path: str,
        original_name: str,
        ext: str,
    ) -> tuple[str | None, str | None, int]:
        """
        Extract text content from a file.

        Tries Tika first for binary document formats (PDF, PPTX, DOCX).
        Falls back to pypdf for PDFs, or plain read for text files.

        Returns:
            (text, title, page_count) — text is None on failure.
        """
        from app.services.pdf_processor import extract_pdf_content, PDFProcessingError

        # Try Tika for supported binary types
        if ext in TIKA_SUPPORTED_EXTENSIONS:
            tika_text = await extract_text_with_tika(file_path)
            # Whitespace-only output counts as a failed extraction — fall
            # through to pypdf for PDFs instead of "succeeding" with a text
            # that chunks to nothing (#129).
            if tika_text and tika_text.strip():
                return tika_text, Path(file_path).stem, 1

        # PDF fallback via pypdf
        if ext == ".pdf":
            try:
                pdf_result = extract_pdf_content(file_path)
                return pdf_result.text, pdf_result.title, pdf_result.page_count
            except PDFProcessingError as exc:
                logger.warning("pypdf fallback failed", file=original_name, error=str(exc))
                return None, None, 0

        # Text / Markdown — plain read
        if ext in {".txt", ".md", ".markdown"}:
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    text = await f.read()
            except OSError as exc:
                logger.warning("Cannot read text file", file=original_name, error=str(exc))
                return None, None, 0

            title = None
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
                elif line and not line.startswith(("---", "```")):
                    title = line[:100]
                    break
            return text, title, 1

        return None, None, 0

    def _build_enrichment_config(self, source: Source) -> EnrichmentConfig:
        """Build an EnrichmentConfig from the knowledge source's enrichment settings."""
        return EnrichmentConfig(
            enabled=getattr(source, "enrichment_enabled", False) or False,
            taxonomy_id=getattr(source, "enrichment_taxonomy_id", None),
            classification_model=(
                getattr(source, "enrichment_model", None)
                or "qwen2.5:7b-instruct"
            ),
            # document_type_detection always on so we get clean text even without taxonomy
            document_type_detection=True,
        )
