"""
Reranking service for RAG — cross-encoder reranking via FlashRank.

Reranking is a post-processing step that re-scores a candidate set of documents
against a query using a dedicated cross-encoder model. Unlike bi-encoder embedding
models (which encode query and document independently), cross-encoders score
query-document pairs together, producing higher-quality relevance scores.

Primary backend: FlashRank (local, fast, no GPU required)
Fallback: Ollama /api/rerank endpoint (if available in future Ollama versions)

Usage:
    reranker = RerankerService()
    results = await reranker.rerank(query, documents, top_k=5)

Graceful degradation:
    If neither FlashRank nor Ollama reranker is available, documents are
    returned unchanged in their original order (no crash).
"""
from typing import Optional

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

settings = get_settings()

# FlashRank model — ms-marco-MiniLM-L-12-v2 is a 34MB cross-encoder
# with the best accuracy among lightweight models
DEFAULT_FLASHRANK_MODEL = "ms-marco-MiniLM-L-12-v2"


class RerankerService:
    """
    Cross-encoder reranking via FlashRank (local) with Ollama fallback.

    FlashRank provides fast, local cross-encoder reranking using small
    ONNX models (~34MB). No GPU required.

    Health check: On first use, attempts to load the FlashRank model.
    If unavailable (import error, model download failure), falls back
    to Ollama /api/rerank. If both fail, reranking is skipped.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.ollama_base_url
        self._ranker = None  # FlashRank Ranker instance
        self._available: Optional[bool] = None  # None=unchecked
        self._backend: Optional[str] = None  # "flashrank" or "ollama" or None

    def _ensure_flashrank(self) -> bool:
        """Try to load FlashRank ranker. Returns True if available."""
        if self._ranker is not None:
            return True
        try:
            from flashrank import Ranker
            self._ranker = Ranker(model_name=DEFAULT_FLASHRANK_MODEL)
            logger.info(
                "FlashRank reranker loaded — cross-encoder reranking is active",
                model=DEFAULT_FLASHRANK_MODEL,
            )
            return True
        except Exception as e:
            logger.warning(
                "FlashRank not available",
                error=str(e),
            )
            return False

    async def _ensure_available(self, model: str = "") -> bool:
        """One-time check: try FlashRank first, then Ollama fallback."""
        if self._available is not None:
            return self._available

        # Try FlashRank first (preferred)
        if self._ensure_flashrank():
            self._available = True
            self._backend = "flashrank"
            return True

        # Fallback: try Ollama /api/rerank
        if await self._check_ollama_rerank(model):
            self._available = True
            self._backend = "ollama"
            logger.info(
                "Ollama reranker available as fallback",
                model=model,
            )
            return True

        # Neither available
        self._available = False
        self._backend = None
        logger.warning(
            "No reranker available — reranking will be skipped. "
            "Install flashrank: pip install flashrank",
        )
        return False

    async def _check_ollama_rerank(self, model: str) -> bool:
        """Check if Ollama's /api/rerank endpoint exists."""
        try:
            import httpx
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                resp = await client.post(
                    "/api/rerank",
                    json={"model": model or "qwen-reranker-light:latest",
                          "query": "test", "documents": ["test"]},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        model: str = "",
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """
        Rerank documents by relevance to query using a cross-encoder.

        Args:
            query: The search query
            documents: List of dicts — must have a 'content' key.
            model: Ignored for FlashRank (uses DEFAULT_FLASHRANK_MODEL).
                   Used for Ollama fallback.
            top_k: Return only the top K results. None = return all.

        Returns:
            Documents sorted by rerank score (highest first), with
            '_rerank_score' added to each dict.
        """
        if not documents:
            return documents

        if not await self._ensure_available(model):
            return documents

        try:
            if self._backend == "flashrank":
                return self._rerank_flashrank(query, documents, top_k)
            elif self._backend == "ollama":
                return await self._rerank_ollama(query, documents, model, top_k)
            else:
                return documents
        except Exception as e:
            logger.warning(
                "Reranking failed — returning documents in original order",
                backend=self._backend,
                error=str(e),
            )
            return documents

    def _rerank_flashrank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int],
    ) -> list[dict]:
        """Rerank using FlashRank (synchronous — fast enough for inline use)."""
        from flashrank import RerankRequest

        # Build passages for FlashRank — requires 'text' key
        passages = []
        for i, doc in enumerate(documents):
            passages.append({
                "id": i,
                "text": doc.get("content", ""),
            })

        request = RerankRequest(query=query, passages=passages)
        ranked = self._ranker.rerank(request)

        # Map scores back to original documents
        score_by_id = {p["id"]: p.get("score", 0.0) for p in ranked}

        scored_docs = []
        for i, doc in enumerate(documents):
            enriched = dict(doc)
            enriched["_rerank_score"] = score_by_id.get(i, 0.0)
            scored_docs.append(enriched)

        scored_docs.sort(key=lambda d: d["_rerank_score"], reverse=True)

        if top_k is not None:
            scored_docs = scored_docs[:top_k]

        logger.info(
            "Reranking complete",
            backend="flashrank",
            model=DEFAULT_FLASHRANK_MODEL,
            input_count=len(documents),
            output_count=len(scored_docs),
        )

        return scored_docs

    async def _rerank_ollama(
        self,
        query: str,
        documents: list[dict],
        model: str,
        top_k: Optional[int],
    ) -> list[dict]:
        """Rerank using Ollama /api/rerank endpoint (fallback)."""
        import httpx

        contents = [doc.get("content", "") for doc in documents]
        model = model or "qwen-reranker-light:latest"

        async with httpx.AsyncClient(base_url=self.base_url, timeout=60.0) as client:
            resp = await client.post(
                "/api/rerank",
                json={"model": model, "query": query, "documents": contents},
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        scores = [0.0] * len(documents)
        for item in results:
            idx = item.get("index", 0)
            if 0 <= idx < len(scores):
                scores[idx] = item.get("relevance_score", 0.0)

        scored_docs = []
        for doc, score in zip(documents, scores):
            enriched = dict(doc)
            enriched["_rerank_score"] = score
            scored_docs.append(enriched)

        scored_docs.sort(key=lambda d: d["_rerank_score"], reverse=True)

        if top_k is not None:
            scored_docs = scored_docs[:top_k]

        logger.info(
            "Reranking complete",
            backend="ollama",
            model=model,
            input_count=len(documents),
            output_count=len(scored_docs),
        )

        return scored_docs

    async def is_available(self, model: str = "") -> bool:
        """Check whether any reranker backend is available."""
        return await self._ensure_available(model)

    async def close(self):
        """Cleanup (no persistent connections in FlashRank)."""
        self._ranker = None
