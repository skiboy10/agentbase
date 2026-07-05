"""
Query decomposition for deep search.

Breaks complex multi-part queries into focused sub-queries, each with
optional metadata filters and a strategy tag. Two decomposition paths:

1. LLM decomposition (gemma4:e4b via Ollama) — understands nuance,
   extracts structured filters using taxonomy vocabulary.
2. Rule-based fallback — conjunction splitting + taxonomy term regex.
   Used when Ollama is unavailable or the query is simple.

Both paths always include the original query as a sub-query to ensure
decomposition never underperforms a single search.
"""
import json
import re
import time
from typing import Optional

import httpx
import structlog

from app.core.config import get_settings

from .types import SubQuery

logger = structlog.get_logger()

settings = get_settings()

# Default model for decomposition — gemma4:e4b balances speed and quality
DEFAULT_DECOMPOSITION_MODEL = "gemma4:e4b"

# Conjunctions that signal independent retrieval targets
_SPLIT_PATTERNS = [
    r"\band\b",
    r"\bcompared?\s+to\b",
    r"\bvs\.?\b",
    r"\bversus\b",
    r"\balso\b",
    r"\bas\s+well\s+as\b",
]
_SPLIT_RE = re.compile("|".join(_SPLIT_PATTERNS), re.IGNORECASE)

# Minimum sub-query length after splitting (skip fragments)
_MIN_SUBQUERY_LEN = 12

# Maximum bytes of LLM response to parse (guard against runaway output)
_MAX_LLM_RESPONSE_BYTES = 32_768

_DECOMPOSITION_SYSTEM_PROMPT = """\
You are a search query decomposer. Your job is to break a complex question \
into focused sub-queries that will each retrieve better results from a \
vector/keyword knowledge base.

Rules:
- Output ONLY a JSON array. No explanation, no markdown fences.
- Each element: {"query": "...", "filters": {}, "strategy": "..."}
- strategy is one of: entity, aspect, temporal, abstraction
- filters keys must come from VOCABULARY below. Values must be exact matches.
- If no filter applies, use empty dict {}.
- Return 2-5 sub-queries. Do NOT include the original query — it is added automatically.
- If the query is already focused (single intent), return a single sub-query \
  that rephrases it for better retrieval.

VOCABULARY (filter keys → allowed values):
__VOCABULARY__"""


class QueryDecomposer:
    """Decomposes complex queries into focused sub-queries.

    Uses Ollama LLM with taxonomy vocabulary injection for intelligent
    decomposition. Falls back to rule-based splitting when Ollama is
    unavailable. Follows the same health-check pattern as RerankerService.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.ollama_base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None  # None=unchecked

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def _ensure_available(self, model: str) -> bool:
        """One-time health check — cache result to avoid repeated calls."""
        if self._available is None:
            self._available = await self._check_model(model)
            if not self._available:
                logger.warning(
                    "Decomposition model not available — falling back to rule-based",
                    model=model,
                    ollama_url=self.base_url,
                )
            else:
                logger.info(
                    "Decomposition model available",
                    model=model,
                )
        return self._available

    async def _check_model(self, model: str) -> bool:
        """Check if the decomposition model is available in Ollama."""
        try:
            client = self._get_client()
            resp = await client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "options": {"num_predict": 1},
                },
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def decompose(
        self,
        query: str,
        max_sub_queries: int = 5,
        taxonomy_vocab: Optional[dict[str, list[str]]] = None,
        model: str = DEFAULT_DECOMPOSITION_MODEL,
    ) -> tuple[list[SubQuery], float]:
        """Decompose a query into sub-queries.

        Tries LLM decomposition first; falls back to rule-based.
        Always includes the original query.

        Returns:
            Tuple of (sub_queries, decomposition_time_ms)
        """
        start = time.monotonic()

        sub_queries: list[SubQuery] = []

        # Try LLM decomposition
        if await self._ensure_available(model):
            try:
                sub_queries = await self._llm_decompose(
                    query, taxonomy_vocab or {}, max_sub_queries, model
                )
            except Exception as e:
                logger.warning(
                    "LLM decomposition failed — falling back to rule-based",
                    error=str(e),
                )

        # Fall back to rule-based if LLM didn't produce results
        if not sub_queries:
            sub_queries = self._rule_based_decompose(query, taxonomy_vocab or {})

        # Always include the original query
        sub_queries.append(SubQuery(query=query, filters={}, strategy="original"))

        # Deduplicate by normalized query text
        seen: set[str] = set()
        unique: list[SubQuery] = []
        for sq in sub_queries:
            key = sq.query.strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(sq)

        elapsed_ms = (time.monotonic() - start) * 1000
        return unique[:max_sub_queries + 1], elapsed_ms  # +1 for original

    async def _llm_decompose(
        self,
        query: str,
        taxonomy_vocab: dict[str, list[str]],
        max_sub_queries: int,
        model: str,
    ) -> list[SubQuery]:
        """Decompose via Ollama chat endpoint.

        The user query is placed in a separate message (not interpolated
        into the system prompt) to prevent prompt injection.
        """
        vocab_str = self._format_vocabulary(taxonomy_vocab)
        system_prompt = _DECOMPOSITION_SYSTEM_PROMPT.replace(
            "__VOCABULARY__", vocab_str or "(no vocabulary available)"
        )

        client = self._get_client()
        resp = await client.post(
            "/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.3,
                    "num_predict": 512,
                },
            },
        )
        resp.raise_for_status()

        content = resp.json().get("message", {}).get("content", "")
        return self._parse_llm_response(content, taxonomy_vocab)

    def _parse_llm_response(
        self,
        content: str,
        taxonomy_vocab: dict[str, list[str]],
    ) -> list[SubQuery]:
        """Parse LLM JSON response into SubQuery list."""
        # Guard against oversized responses before parsing
        content = content[:_MAX_LLM_RESPONSE_BYTES].strip()
        if content.startswith("```"):
            content = re.sub(r"^```\w*\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed = json.loads(content)

        # Handle both array and {"sub_queries": [...]} formats
        if isinstance(parsed, dict):
            parsed = parsed.get("sub_queries", parsed.get("queries", []))
        if not isinstance(parsed, list):
            return []

        valid_strategies = {"entity", "aspect", "temporal", "abstraction"}
        valid_filter_keys = set(taxonomy_vocab.keys()) if taxonomy_vocab else set()

        sub_queries = []
        for item in parsed:
            if not isinstance(item, dict) or "query" not in item:
                continue

            query_text = str(item["query"]).strip()
            if len(query_text) < _MIN_SUBQUERY_LEN:
                continue

            strategy = item.get("strategy", "aspect")
            if strategy not in valid_strategies:
                strategy = "aspect"

            # Validate filters — only keep keys that match known vocabulary
            raw_filters = item.get("filters", {})
            clean_filters = {}
            if isinstance(raw_filters, dict) and valid_filter_keys:
                for k, v in raw_filters.items():
                    if k in valid_filter_keys:
                        # Ensure values are from vocabulary
                        allowed = set(taxonomy_vocab.get(k, []))
                        if isinstance(v, list):
                            validated = [x for x in v if x in allowed]
                            if validated:
                                clean_filters[k] = validated
                        elif isinstance(v, str) and v in allowed:
                            clean_filters[k] = v

            sub_queries.append(SubQuery(
                query=query_text,
                filters=clean_filters,
                strategy=strategy,
            ))

        return sub_queries

    def _rule_based_decompose(
        self,
        query: str,
        taxonomy_vocab: dict[str, list[str]],
    ) -> list[SubQuery]:
        """Split query on conjunctions and extract taxonomy terms as filters."""
        parts = _SPLIT_RE.split(query)
        parts = [p.strip() for p in parts if len(p.strip()) >= _MIN_SUBQUERY_LEN]

        if len(parts) <= 1:
            # No meaningful split — return empty (original will be added by caller)
            return []

        sub_queries = []
        for part in parts:
            filters = self._extract_taxonomy_filters(part, taxonomy_vocab)
            sub_queries.append(SubQuery(
                query=part,
                filters=filters,
                strategy="aspect",
            ))

        return sub_queries

    def _extract_taxonomy_filters(
        self,
        text: str,
        taxonomy_vocab: dict[str, list[str]],
    ) -> dict:
        """Regex-match taxonomy term values in a text fragment."""
        filters: dict[str, list[str]] = {}
        text_lower = text.lower()

        for facet, values in taxonomy_vocab.items():
            matched = []
            for val in values:
                # Case-insensitive whole-word match
                if re.search(r"\b" + re.escape(val.lower()) + r"\b", text_lower):
                    matched.append(val)
            if matched:
                filters[facet] = matched

        return filters

    @staticmethod
    def _format_vocabulary(taxonomy_vocab: dict[str, list[str]]) -> str:
        """Format taxonomy vocabulary for the LLM prompt."""
        if not taxonomy_vocab:
            return ""
        lines = []
        for facet, values in taxonomy_vocab.items():
            # Limit to 30 values per facet to keep prompt short
            display = values[:30]
            suffix = f" ... (+{len(values) - 30} more)" if len(values) > 30 else ""
            lines.append(f"  {facet}: {display}{suffix}")
        return "\n".join(lines)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
