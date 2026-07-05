"""
URL indexer for web pages.

Handles indexing of web pages via URL scraping, including retry and selective refresh.
"""
import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from qdrant_client.models import Filter, FieldCondition, MatchAny
import structlog
from bs4 import BeautifulSoup

from app.models import Source, IndexingLog
from app.core.config import get_settings
from app.core.url_validator import validate_url_safe
from app.services.web_scraper.parser import extract_content

from .base import BaseIndexer

logger = structlog.get_logger()
settings = get_settings()


# Indexer-level safety net (see #127). The browser layer already hard-caps
# each fetch at FETCH_TIMEOUT (180s) and recycles on crash, but we wrap
# again here so a hang anywhere in scrape_page + post-processing can't
# freeze the whole job.
PER_URL_TIMEOUT = 300.0  # 5 min per page

# If the indexer goes this long without a successful page, abort the job
# with status=error instead of hanging at status=indexing forever. The
# user-visible bug in #127 was sources stuck at "indexing" with no
# completion or error. Set generously so a few slow pages don't trip it.
STALL_TIMEOUT = timedelta(minutes=15)


class _StallError(Exception):
    """Raised by the URL indexer when no successful page in STALL_TIMEOUT."""


class UrlIndexer(BaseIndexer):
    """Indexer for web pages via URL scraping."""

    def _process_page_content(
        self,
        page_content: str,
        page_html: str | None,
        page_url: str,
        text_splitter,
    ) -> tuple[list[str], list[dict]]:
        """
        Process page content, extracting code blocks if enabled.

        Args:
            page_content: Extracted text content
            page_html: Raw HTML (if available)
            page_url: Source URL
            text_splitter: Text splitter for chunking

        Returns:
            (chunks, chunk_metadata_list) - Ready for embedding
        """
        code_blocks = []
        text_content = page_content

        # Extract code blocks if preservation is enabled and HTML is available
        if settings.code_preservation_enabled and page_html:
            try:
                soup = BeautifulSoup(page_html, 'html.parser')
                result = extract_content(soup, preserve_code=True)
                if isinstance(result, tuple):
                    text_content, code_blocks = result
                else:
                    text_content = result
            except Exception as e:
                logger.warning("Code extraction failed, using raw content", url=page_url, error=str(e))
                text_content = page_content

        chunks = []
        metadata_list = []
        chunk_index = 0

        # Log code block extraction results
        if code_blocks:
            with_lang = sum(1 for cb in code_blocks if cb.get('has_language_class'))
            logger.info(
                "Code blocks extracted",
                url=page_url,
                total_blocks=len(code_blocks),
                with_language=with_lang,
                without_language=len(code_blocks) - with_lang
            )

        # Process code blocks as separate chunks (only with detected language)
        for code_block in code_blocks:
            if code_block.get('has_language_class', False):
                chunks.append(code_block['content'])
                metadata_list.append({
                    "chunk_index": chunk_index,
                    "metadata": {
                        "type": "code",
                        "language": code_block['language'],
                        "code_tag": code_block['type'],
                    },
                })
                chunk_index += 1

        # Process regular text chunks
        text_chunks = text_splitter.split_text(text_content)
        for chunk in text_chunks:
            chunks.append(chunk)
            metadata_list.append({
                "chunk_index": chunk_index,
                "metadata": {"type": "text"},
            })
            chunk_index += 1

        return chunks, metadata_list

    async def index(self, source: Source) -> None:
        """Index selected URLs from a website with embeddings and detailed logging."""
        from app.services.web_scraper import get_scraper

        if not source.selected_urls:
            raise ValueError("No URLs selected for indexing")

        try:
            urls = json.loads(source.selected_urls)
        except json.JSONDecodeError:
            raise ValueError("Invalid selected_urls format")

        if not urls:
            raise ValueError("No URLs selected for indexing")

        total_urls = len(urls)

        # Clear existing logs
        delete_logs_stmt = delete(IndexingLog).where(IndexingLog.source_id == source.id)
        await self.db.execute(delete_logs_stmt)

        # Create pending log entries
        url_logs = {}
        for url in urls:
            log = IndexingLog(
                source_id=source.id,
                url=url,
                status="pending",
            )
            self.db.add(log)
            url_logs[url] = log
        await self.db.flush()

        source.progress_total = total_urls
        source.progress = 0
        source.progress_message = f"Preparing to scrape {total_urls} pages..."
        source.progress_updated_at = datetime.utcnow()
        await self._publish_progress()

        # Load all libraries this source belongs to (KB-aware mode)
        await self._load_kb_for_source(source)
        kbs = self._get_kbs(source)
        kb_aware = bool(kbs)
        primary_kb = kbs[0] if kbs else None

        emb_provider, emb_model, vector_size = await self._get_embedding_config(source)

        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")

        logger.info(
            "Starting URL indexing with embeddings",
            source_id=source.id,
            url_count=total_urls,
            provider=emb_provider,
            model=emb_model,
            dimensions=vector_size,
            kb_aware=kb_aware,
        )

        # Store embedding config on source for retrieval validation
        await self._store_embedding_config(source, emb_provider, emb_model, vector_size)

        # Primary collection is always the source's own (what search reads);
        # bound libraries receive mirror copies.
        collection_name = self._get_collection_for_source(source)
        mirror_targets: list[tuple[str, str]] = self._get_library_mirror_collections(source)

        if kb_aware:
            await self._ensure_collection_exists(collection_name, vector_size)
            for mirror_coll, _ in mirror_targets:
                await self._ensure_collection_exists(mirror_coll, vector_size)
        else:
            await self._setup_collection(collection_name, vector_size)

        text_splitter = self._get_text_splitter()

        doc_count = 0
        chunk_count = 0
        failed_count = 0
        dimensions_captured = False

        batch_chunks = []
        batch_metadata = []
        batch_logs = []

        scraper = get_scraper()
        last_progress_at = datetime.utcnow()

        for idx, url in enumerate(urls):
            # Stall watchdog: abort the job if no successful page in
            # STALL_TIMEOUT (see #127). Browser-layer timeouts already bound
            # each fetch; this catches longer-horizon stalls (e.g. a long
            # streak of failures that should give up rather than burn hours).
            if datetime.utcnow() - last_progress_at > STALL_TIMEOUT:
                raise _StallError(
                    f"No successful page in {STALL_TIMEOUT.total_seconds() / 60:.0f} min — aborting"
                )

            log = url_logs[url]

            # SSRF re-validation (#50): URLs from the DB may be stale —
            # DNS rebinding could have moved the host to a private IP since
            # the URL was first stored, or the user added URLs that slipped
            # through earlier validation. Re-check before each fetch.
            if validate_url_safe(url) is None:
                log.status = "failed"
                log.error_message = "Blocked by SSRF policy"
                log.updated_at = datetime.utcnow()
                failed_count += 1
                await self.db.flush()
                continue

            progress_msg = f"Scraping ({idx + 1}/{total_urls}): {url}"
            source.progress = idx
            source.progress_message = progress_msg
            source.progress_updated_at = datetime.utcnow()

            log.status = "scraping"
            log.updated_at = datetime.utcnow()
            await self._publish_progress()

            scrape_start = time.time()

            try:
                try:
                    page = await asyncio.wait_for(
                        scraper.scrape_page(url), timeout=PER_URL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    page = None
                    logger.warning(
                        "Per-URL timeout hit; treating as failed page",
                        url=url,
                        timeout_sec=PER_URL_TIMEOUT,
                    )

                scrape_duration = int((time.time() - scrape_start) * 1000)
                log.scrape_duration_ms = scrape_duration

                if not page or not page.success or not page.content:
                    error_msg = page.error if page else f"Timeout (>{int(PER_URL_TIMEOUT)}s)"
                    logger.warning("Skipping failed page", url=url, error=error_msg)
                    log.status = "failed"
                    log.error_message = error_msg or "Empty content"
                    log.updated_at = datetime.utcnow()
                    failed_count += 1
                    await self.db.flush()
                    continue

                log.status = "scraped"
                log.content_length = len(page.content)
                log.updated_at = datetime.utcnow()
                await self.db.flush()

                # Save raw content to postgres for re-embedding experiments
                await self._save_scraped_content(
                    source=source,
                    url=page.url,
                    title=page.title,
                    content=page.content,
                )

                # Process content with code preservation
                logger.info(
                    "Processing page",
                    url=page.url,
                    has_html=page.html is not None,
                    html_length=len(page.html) if page.html else 0,
                    code_preservation_enabled=settings.code_preservation_enabled
                )
                chunks, chunk_metadata_list = self._process_page_content(
                    page.content, page.html, page.url, text_splitter
                )
                # Silent 0-chunk detector: page scraped successfully (we have
                # bytes in page.content) but extraction produced nothing. This
                # is a real failure — the source would otherwise show
                # status='indexed' with chunk_count=0 and be invisible at
                # search time. Mark the log as failed so it's surfaced and
                # eligible for retry-failed. See #105.
                if not chunks and page.content and len(page.content.strip()) > 50:
                    logger.warning(
                        "Page scraped successfully but produced 0 chunks — "
                        "likely a selector mismatch in extract_content",
                        url=page.url,
                        scraped_chars=len(page.content),
                        html_chars=len(page.html) if page.html else 0,
                    )
                    log.status = "failed"
                    log.error_message = (
                        f"Extraction produced 0 chunks from {len(page.content)} "
                        f"scraped chars (likely selector mismatch)"
                    )
                    log.updated_at = datetime.utcnow()
                    failed_count += 1
                    await self.db.flush()
                    continue
                log.chunk_count = len(chunks)
                chunk_scraped_at = datetime.utcnow().isoformat()

                # KB-aware: stable document_id derived from (source_id, url)
                document_id = (
                    self._generate_document_id(source.id, page.url) if kb_aware else None
                )

                for chunk, chunk_meta in zip(chunks, chunk_metadata_list):
                    chunk_id = hashlib.md5(
                        f"{page.url}:{chunk_meta['chunk_index']}".encode()
                    ).hexdigest()

                    batch_chunks.append(chunk)
                    meta = {
                        "id": chunk_id,
                        "source": page.url,
                        "source_id": source.id,
                        "chunk_index": chunk_meta['chunk_index'],
                        "title": page.title,
                        "scraped_at": chunk_scraped_at,
                        "metadata": chunk_meta['metadata'],
                    }
                    if kb_aware and document_id and primary_kb:
                        meta["document_id"] = document_id
                        meta["library_id"] = primary_kb.id
                    batch_metadata.append(meta)
                    batch_logs.append(log)

                    if len(batch_chunks) >= self.BATCH_SIZE:
                        embed_start = time.time()
                        batch_count, actual_dims = await self._process_embedding_batch(
                            collection_name,
                            batch_chunks, batch_metadata,
                            emb_provider, emb_model,
                            mirror_targets=mirror_targets or None,
                        )
                        embed_duration = int((time.time() - embed_start) * 1000)

                        # Update dimensions from actual embedding response
                        if not dimensions_captured and actual_dims:
                            await self._update_embedding_dimensions(source, actual_dims)
                            dimensions_captured = True

                        processed_logs = set(batch_logs)
                        for batch_log in processed_logs:
                            batch_log.status = "done"
                            batch_log.embed_duration_ms = embed_duration
                            batch_log.updated_at = datetime.utcnow()

                        chunk_count += len(batch_chunks)
                        logger.info("Processed batch", chunks=len(batch_chunks), total=chunk_count)
                        batch_chunks = []
                        batch_metadata = []
                        batch_logs = []
                        await self.db.flush()

                if log.status == "scraped":
                    log.status = "embedding"
                    log.updated_at = datetime.utcnow()

                # KB-aware: write/update one Document row per library this
                # source is bound to. Done per URL so partial failures still
                # leave a record of the URLs that did make it through.
                if kb_aware and document_id:
                    content_hash = self._compute_content_hash(page.content or "")
                    await self._upsert_kb_documents(
                        source=source,
                        kbs=kbs,
                        document_id=document_id,
                        title=page.title or page.url,
                        full_text=page.content or "",
                        content_hash=content_hash,
                        url=page.url,
                        file_type="url",
                        document_type="standard",
                        classification=None,
                        chunk_count=len(chunks),
                    )

                doc_count += 1
                last_progress_at = datetime.utcnow()
                logger.info("Processed URL", url=page.url, title=page.title, chunks=len(chunks))

            except Exception as e:
                logger.warning("Failed to process URL", url=url, error=str(e))
                log.status = "failed"
                log.error_message = str(e)
                log.updated_at = datetime.utcnow()
                failed_count += 1
                await self.db.flush()

        # Process remaining batch
        if batch_chunks:
            source.progress_message = f"Generating embeddings for final batch..."
            source.progress_updated_at = datetime.utcnow()
            await self.db.flush()

            embed_start = time.time()
            batch_count, actual_dims = await self._process_embedding_batch(
                collection_name,
                batch_chunks, batch_metadata,
                emb_provider, emb_model,
                mirror_targets=mirror_targets or None,
            )
            embed_duration = int((time.time() - embed_start) * 1000)

            # Update dimensions from actual embedding response
            if not dimensions_captured and actual_dims:
                await self._update_embedding_dimensions(source, actual_dims)
                dimensions_captured = True

            processed_logs = set(batch_logs)
            for batch_log in processed_logs:
                batch_log.status = "done"
                batch_log.embed_duration_ms = embed_duration
                batch_log.updated_at = datetime.utcnow()

            chunk_count += len(batch_chunks)
            await self.db.flush()

        await self._finalize_indexing(
            source, doc_count, chunk_count, total_urls, failed_count,
            item_type="pages indexed"
        )

        logger.info(
            "URL indexing complete",
            source_id=source.id,
            documents=doc_count,
            chunks=chunk_count,
            failed=failed_count,
            embedding_provider=emb_provider,
            embedding_model=emb_model,
        )

    async def execute_retry(self, source_id: str, urls: list[str]) -> None:
        """Execute retry indexing for specific URLs. Call from background task."""
        from app.services.web_scraper import get_scraper

        source = await self._get_source(source_id)
        if not source:
            logger.error("Source not found for retry task", source_id=source_id)
            return

        logs_stmt = select(IndexingLog).where(
            IndexingLog.source_id == source_id,
            IndexingLog.url.in_(urls)
        )
        logs_result = await self.db.execute(logs_stmt)
        url_logs = {log.url: log for log in logs_result.scalars().all()}

        total_urls = len(urls)

        emb_provider, emb_model, vector_size = await self._get_embedding_config(source)

        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")

        collection_name = source.collection_name
        text_splitter = self._get_text_splitter()

        doc_count = 0
        chunk_count = 0
        failed_count = 0
        dimensions_captured = False

        batch_chunks = []
        batch_metadata = []
        batch_logs = []

        scraper = get_scraper()
        last_progress_at = datetime.utcnow()

        for idx, url in enumerate(urls):
            if datetime.utcnow() - last_progress_at > STALL_TIMEOUT:
                raise _StallError(
                    f"No successful page in {STALL_TIMEOUT.total_seconds() / 60:.0f} min — aborting retry"
                )

            log = url_logs.get(url)
            if not log:
                continue

            # SSRF re-validation (#50) — see index() for rationale.
            if validate_url_safe(url) is None:
                log.status = "failed"
                log.error_message = "Blocked by SSRF policy"
                log.updated_at = datetime.utcnow()
                failed_count += 1
                await self.db.flush()
                continue

            progress_msg = f"Retrying ({idx + 1}/{total_urls}): {url}"
            source.progress = idx
            source.progress_message = progress_msg
            source.progress_updated_at = datetime.utcnow()
            await self._publish_progress()

            log.status = "scraping"
            log.updated_at = datetime.utcnow()
            await self.db.flush()

            scrape_start = time.time()

            try:
                try:
                    page = await asyncio.wait_for(
                        scraper.scrape_page(url), timeout=PER_URL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    page = None
                    logger.warning(
                        "Per-URL timeout hit; treating as failed page",
                        url=url,
                        timeout_sec=PER_URL_TIMEOUT,
                    )

                scrape_duration = int((time.time() - scrape_start) * 1000)
                log.scrape_duration_ms = scrape_duration

                if not page or not page.success or not page.content:
                    error_msg = page.error if page else f"Timeout (>{int(PER_URL_TIMEOUT)}s)"
                    log.status = "failed"
                    log.error_message = error_msg or "Empty content"
                    log.updated_at = datetime.utcnow()
                    failed_count += 1
                    await self.db.flush()
                    continue

                log.status = "scraped"
                log.content_length = len(page.content)
                log.updated_at = datetime.utcnow()
                await self.db.flush()

                # Save raw content to postgres for re-embedding experiments
                await self._save_scraped_content(
                    source=source,
                    url=page.url,
                    title=page.title,
                    content=page.content,
                )

                chunks = text_splitter.split_text(page.content)
                log.chunk_count = len(chunks)
                chunk_scraped_at = datetime.utcnow().isoformat()

                for i, chunk in enumerate(chunks):
                    chunk_id = hashlib.md5(f"{page.url}:{i}".encode()).hexdigest()
                    batch_chunks.append(chunk)
                    batch_metadata.append({
                        "id": chunk_id,
                        "source": page.url,
                        "source_id": source.id,
                        "chunk_index": i,
                        "title": page.title,
                        "scraped_at": chunk_scraped_at,
                        "metadata": {},
                    })
                    batch_logs.append(log)

                    if len(batch_chunks) >= self.BATCH_SIZE:
                        embed_start = time.time()
                        batch_count, actual_dims = await self._process_embedding_batch(
                            collection_name,
                            batch_chunks, batch_metadata,
                            emb_provider, emb_model
                        )
                        embed_duration = int((time.time() - embed_start) * 1000)

                        # Update dimensions from actual embedding response
                        if not dimensions_captured and actual_dims:
                            await self._update_embedding_dimensions(source, actual_dims)
                            dimensions_captured = True

                        for batch_log in set(batch_logs):
                            batch_log.status = "done"
                            batch_log.embed_duration_ms = embed_duration
                            batch_log.updated_at = datetime.utcnow()

                        chunk_count += len(batch_chunks)
                        batch_chunks = []
                        batch_metadata = []
                        batch_logs = []
                        await self.db.flush()

                if log.status == "scraped":
                    log.status = "embedding"
                    log.updated_at = datetime.utcnow()

                doc_count += 1
                last_progress_at = datetime.utcnow()

            except Exception as e:
                log.status = "failed"
                log.error_message = str(e)
                log.updated_at = datetime.utcnow()
                failed_count += 1
                await self.db.flush()

        # Process remaining batch
        if batch_chunks:
            embed_start = time.time()
            batch_count, actual_dims = await self._process_embedding_batch(
                collection_name,
                batch_chunks, batch_metadata,
                emb_provider, emb_model
            )
            embed_duration = int((time.time() - embed_start) * 1000)

            # Update dimensions from actual embedding response
            if not dimensions_captured and actual_dims:
                await self._update_embedding_dimensions(source, actual_dims)
                dimensions_captured = True

            for batch_log in set(batch_logs):
                batch_log.status = "done"
                batch_log.embed_duration_ms = embed_duration
                batch_log.updated_at = datetime.utcnow()

            chunk_count += len(batch_chunks)
            await self.db.flush()

        source.status = "indexed"
        source.document_count = source.document_count + doc_count
        source.chunk_count = source.chunk_count + chunk_count
        source.last_indexed = datetime.utcnow()
        source.progress = total_urls
        source.progress_message = f"Retry complete: {doc_count} pages indexed"
        if failed_count > 0:
            source.progress_message += f" ({failed_count} still failed)"
        source.progress_updated_at = datetime.utcnow()

        logger.info(
            "Retry indexing complete",
            source_id=source.id,
            documents=doc_count,
            chunks=chunk_count,
            failed=failed_count,
        )

    async def execute_selective_index(self, source_id: str, urls: list[str]) -> None:
        """Re-index only specific URLs. Deletes old vectors and re-scrapes."""
        from app.services.web_scraper import get_scraper

        source = await self._get_source(source_id)
        if not source:
            logger.error("Source not found for selective indexing", source_id=source_id)
            return

        if source.source_type != "url":
            raise ValueError("Selective indexing only available for URL sources")

        total_urls = len(urls)
        collection_name = source.collection_name

        # Delete existing vectors for these URLs
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchAny(any=urls)
                        )
                    ]
                )
            )
            logger.info("Deleted existing vectors for selective refresh", source_id=source_id, urls=urls)
        except Exception as e:
            logger.warning("Failed to delete existing vectors", error=str(e))

        # Get existing logs or create new ones
        logs_stmt = select(IndexingLog).where(
            IndexingLog.source_id == source_id,
            IndexingLog.url.in_(urls)
        )
        logs_result = await self.db.execute(logs_stmt)
        existing_logs = {log.url: log for log in logs_result.scalars().all()}

        # Create logs for any missing URLs
        url_logs = {}
        for url in urls:
            if url in existing_logs:
                log = existing_logs[url]
                log.status = "pending"
                log.error_message = None
                log.scrape_duration_ms = None
                log.embed_duration_ms = None
            else:
                log = IndexingLog(
                    source_id=source_id,
                    url=url,
                    status="pending",
                )
                self.db.add(log)
            url_logs[url] = log
        await self.db.flush()

        source.progress_total = total_urls
        source.progress = 0
        source.progress_message = f"Selectively refreshing {total_urls} pages..."
        source.progress_updated_at = datetime.utcnow()
        await self._publish_progress()

        emb_provider, emb_model, vector_size = await self._get_embedding_config(source)

        if not self.embedding_registry.get_provider(emb_provider):
            raise ValueError(f"Embedding provider '{emb_provider}' not configured")

        text_splitter = self._get_text_splitter()

        doc_count = 0
        chunk_count = 0
        failed_count = 0
        dimensions_captured = False

        batch_chunks = []
        batch_metadata = []
        batch_logs = []

        scraper = get_scraper()
        last_progress_at = datetime.utcnow()

        for idx, url in enumerate(urls):
            if datetime.utcnow() - last_progress_at > STALL_TIMEOUT:
                raise _StallError(
                    f"No successful page in {STALL_TIMEOUT.total_seconds() / 60:.0f} min — aborting refresh"
                )

            log = url_logs[url]

            # SSRF re-validation (#50) — see index() for rationale.
            if validate_url_safe(url) is None:
                log.status = "failed"
                log.error_message = "Blocked by SSRF policy"
                log.updated_at = datetime.utcnow()
                failed_count += 1
                await self.db.flush()
                continue

            progress_msg = f"Refreshing ({idx + 1}/{total_urls}): {url}"
            source.progress = idx
            source.progress_message = progress_msg
            source.progress_updated_at = datetime.utcnow()
            await self._publish_progress()

            log.status = "scraping"
            log.updated_at = datetime.utcnow()
            await self.db.flush()

            scrape_start = time.time()

            try:
                try:
                    page = await asyncio.wait_for(
                        scraper.scrape_page(url), timeout=PER_URL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    page = None
                    logger.warning(
                        "Per-URL timeout hit; treating as failed page",
                        url=url,
                        timeout_sec=PER_URL_TIMEOUT,
                    )

                scrape_duration = int((time.time() - scrape_start) * 1000)
                log.scrape_duration_ms = scrape_duration

                if not page or not page.success or not page.content:
                    error_msg = page.error if page else f"Timeout (>{int(PER_URL_TIMEOUT)}s)"
                    logger.warning("Skipping failed page", url=url, error=error_msg)
                    log.status = "failed"
                    log.error_message = error_msg or "Empty content"
                    log.updated_at = datetime.utcnow()
                    failed_count += 1
                    await self.db.flush()
                    continue

                log.status = "scraped"
                log.content_length = len(page.content)
                log.updated_at = datetime.utcnow()
                await self.db.flush()

                # Save raw content to postgres for re-embedding experiments
                await self._save_scraped_content(
                    source=source,
                    url=page.url,
                    title=page.title,
                    content=page.content,
                )

                chunks = text_splitter.split_text(page.content)
                log.chunk_count = len(chunks)
                chunk_scraped_at = datetime.utcnow().isoformat()

                for i, chunk in enumerate(chunks):
                    chunk_id = hashlib.md5(f"{page.url}:{i}".encode()).hexdigest()

                    batch_chunks.append(chunk)
                    batch_metadata.append({
                        "id": chunk_id,
                        "source": page.url,
                        "source_id": source.id,
                        "chunk_index": i,
                        "title": page.title,
                        "scraped_at": chunk_scraped_at,
                        "metadata": {},
                    })
                    batch_logs.append(log)

                    if len(batch_chunks) >= self.BATCH_SIZE:
                        embed_start = time.time()
                        batch_count, actual_dims = await self._process_embedding_batch(
                            collection_name,
                            batch_chunks, batch_metadata,
                            emb_provider, emb_model
                        )
                        embed_duration = int((time.time() - embed_start) * 1000)

                        # Update dimensions from actual embedding response
                        if not dimensions_captured and actual_dims:
                            await self._update_embedding_dimensions(source, actual_dims)
                            dimensions_captured = True

                        processed_logs = set(batch_logs)
                        for batch_log in processed_logs:
                            batch_log.status = "done"
                            batch_log.embed_duration_ms = embed_duration
                            batch_log.updated_at = datetime.utcnow()

                        chunk_count += len(batch_chunks)
                        batch_chunks = []
                        batch_metadata = []
                        batch_logs = []
                        await self.db.flush()

                if log.status == "scraped":
                    log.status = "embedding"
                    log.updated_at = datetime.utcnow()

                doc_count += 1
                last_progress_at = datetime.utcnow()

            except Exception as e:
                logger.warning("Failed to process URL", url=url, error=str(e))
                log.status = "failed"
                log.error_message = str(e)
                log.updated_at = datetime.utcnow()
                failed_count += 1
                await self.db.flush()

        # Process remaining batch
        if batch_chunks:
            source.progress_message = f"Generating embeddings for final batch..."
            source.progress_updated_at = datetime.utcnow()
            await self.db.flush()

            embed_start = time.time()
            batch_count, actual_dims = await self._process_embedding_batch(
                collection_name,
                batch_chunks, batch_metadata,
                emb_provider, emb_model
            )
            embed_duration = int((time.time() - embed_start) * 1000)

            # Update dimensions from actual embedding response
            if not dimensions_captured and actual_dims:
                await self._update_embedding_dimensions(source, actual_dims)
                dimensions_captured = True

            processed_logs = set(batch_logs)
            for batch_log in processed_logs:
                batch_log.status = "done"
                batch_log.embed_duration_ms = embed_duration
                batch_log.updated_at = datetime.utcnow()

            chunk_count += len(batch_chunks)
            await self.db.flush()

        source.status = "indexed"
        source.last_indexed = datetime.utcnow()
        source.progress = total_urls
        source.progress_message = f"Selective refresh complete: {doc_count} pages refreshed"
        if failed_count > 0:
            source.progress_message += f" ({failed_count} failed)"
        source.progress_updated_at = datetime.utcnow()
        await self.db.flush()

        logger.info(
            "Selective indexing complete",
            source_id=source_id,
            documents=doc_count,
            chunks=chunk_count,
            failed=failed_count,
        )

    async def _get_source(self, source_id: str) -> Source | None:
        """Get a knowledge source by ID."""
        from app.models import Source
        stmt = select(Source).where(Source.id == source_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
