"""
Enrichment service for the ingestion pipeline.

Runs text cleaning and LLM-based document classification during indexing.
Classification uses the Taxonomy entity built in Phase 1, with a keyword-match
fallback when the LLM is unavailable.
"""
import json
import re
from dataclasses import dataclass
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Taxonomy, TaxonomyTerm
from app.services.taxonomy.service import TaxonomyService
from .text_cleaner import clean_text, CleanResult

logger = structlog.get_logger()


@dataclass
class EnrichmentConfig:
    """Configuration for the enrichment pipeline."""
    enabled: bool = False
    taxonomy_id: Optional[str] = None
    classification_provider: str = "ollama"
    classification_model: str = "qwen2.5:7b-instruct"
    classification_temperature: float = 0.1
    max_classification_chars: int = 3000
    document_type_detection: bool = True


# ------------------------------------------------------------------ #
# Classification prompt template
# ------------------------------------------------------------------ #
_CLASSIFY_PROMPT = """\
You are a document classifier. Classify this document using ONLY the provided taxonomy values.

DOCUMENT (first {max_chars} chars):
{text_excerpt}

FILENAME: {filename}

TAXONOMY:
{taxonomy_block}

Return ONLY valid JSON with no explanation:
{json_template}"""


class EnrichmentService:
    """
    Enrichment service for the ingestion pipeline.

    Orchestrates:
    1. Text cleaning (artifact removal, whitespace normalization)
    2. Document type detection (presentation vs standard)
    3. LLM-based classification against a Taxonomy
    4. Keyword fallback when LLM is unavailable
    """

    def __init__(self):
        self._taxonomy_service = TaxonomyService()

    async def enrich(
        self,
        text: str,
        filename: str,
        config: EnrichmentConfig,
        db: AsyncSession,
    ) -> dict:
        """
        Run text cleaning and optional LLM classification.

        Args:
            text: Raw extracted text from the document.
            filename: Original filename (used for presentation heuristics).
            config: Enrichment configuration for this knowledge source.
            db: Database session for taxonomy lookup.

        Returns:
            dict with keys:
                - cleaned_text (str): Cleaned document text.
                - document_type (str): "presentation" or "standard".
                - presentation_score (int): Heuristic score.
                - classification (dict | None): Taxonomy classification or None
                  if enrichment is disabled or taxonomy_id is missing.
        """
        result: dict = {
            "cleaned_text": text,
            "document_type": "standard",
            "presentation_score": 0,
            "classification": None,
        }

        # --- Text cleaning (always run when enrichment is enabled) ---
        if config.document_type_detection:
            clean: CleanResult = clean_text(text, filename)
            result["cleaned_text"] = clean["text"]
            result["document_type"] = clean["document_type"]
            result["presentation_score"] = clean["presentation_score"]
        else:
            result["cleaned_text"] = text

        # --- Classification (only when taxonomy configured) ---
        if not config.enabled or not config.taxonomy_id:
            return result

        taxonomy = await self._taxonomy_service.get_taxonomy(db, config.taxonomy_id)
        if not taxonomy or not taxonomy.terms:
            logger.warning(
                "Taxonomy not found or has no terms — skipping classification",
                taxonomy_id=config.taxonomy_id,
            )
            return result

        try:
            classification = await self._classify_with_llm(
                result["cleaned_text"], filename, taxonomy, config
            )
            result["classification_method"] = "llm"
        except Exception as exc:
            logger.warning(
                "LLM classification failed — falling back to keyword matching",
                error=str(exc),
                provider=config.classification_provider,
                model=config.classification_model,
            )
            classification = await self._classify_with_keywords(
                result["cleaned_text"], filename, taxonomy
            )
            result["classification_method"] = "keyword"

        result["classification"] = classification
        return result

    # ------------------------------------------------------------------ #
    # LLM classification
    # ------------------------------------------------------------------ #

    async def _classify_with_llm(
        self,
        text: str,
        filename: str,
        taxonomy: Taxonomy,
        config: EnrichmentConfig,
    ) -> dict:
        """
        Build prompt from taxonomy terms, call LLM, parse and validate response.

        Returns validated classification dict with only known taxonomy values.
        """
        from app.providers.registry import get_registry
        from app.providers.base import ChatMessage, MessageRole

        facets = _group_terms_by_facet(taxonomy.terms)
        text_excerpt = text[: config.max_classification_chars]

        taxonomy_lines = []
        json_keys = {}
        for facet, values in sorted(facets.items()):
            taxonomy_lines.append(f"- {facet}: {', '.join(values)}")
            # Use singular "doc_category" for "doc_categories" facet to match n8n convention
            json_key = "doc_category" if facet == "doc_categories" else f"{facet}s"
            json_keys[json_key] = [] if facet != "doc_categories" else ""

        taxonomy_block = "\n".join(taxonomy_lines) if taxonomy_lines else "(no terms defined)"
        json_template = json.dumps(json_keys, indent=None)

        prompt = _CLASSIFY_PROMPT.format(
            max_chars=config.max_classification_chars,
            text_excerpt=text_excerpt,
            filename=filename,
            taxonomy_block=taxonomy_block,
            json_template=json_template,
        )

        registry = get_registry()
        messages = [ChatMessage(role=MessageRole.USER, content=prompt)]

        response = await registry.chat(
            provider_name=config.classification_provider,
            model=config.classification_model,
            messages=messages,
            temperature=config.classification_temperature,
            max_tokens=500,
        )

        raw_classification = _parse_json_response(response.content)
        if not raw_classification:
            raise ValueError(f"LLM returned non-JSON response: {response.content[:200]}")

        validated = _validate_classification(raw_classification, facets)
        logger.info(
            "LLM classification complete",
            filename=filename,
            classification=validated,
        )
        return validated

    # ------------------------------------------------------------------ #
    # Keyword fallback
    # ------------------------------------------------------------------ #

    async def _classify_with_keywords(
        self,
        text: str,
        filename: str,
        taxonomy: Taxonomy,
    ) -> dict:
        """
        Fallback classifier: match text against TaxonomyTerm.keywords arrays.

        Iterates all terms and checks whether any keyword appears in the
        lowercased document text or filename. Returns the best-matching terms
        per facet (all matches, not just the first).
        """
        facets = _group_terms_by_facet(taxonomy.terms)
        text_lower = text.lower()
        filename_lower = filename.lower()

        result: dict = {}
        for term in taxonomy.terms:
            if not term.keywords:
                continue
            matched = any(
                kw.lower() in text_lower or kw.lower() in filename_lower
                for kw in term.keywords
                if isinstance(kw, str)
            )
            if matched:
                facet = term.facet
                if facet not in result:
                    result[facet] = []
                if isinstance(result[facet], list) and term.value not in result[facet]:
                    result[facet].append(term.value)

        # Normalise to same structure used by LLM path
        normalised: dict = {}
        for facet, values in sorted(facets.items()):
            json_key = "doc_category" if facet == "doc_categories" else f"{facet}s"
            matched_values = result.get(facet, [])
            if json_key == "doc_category":
                normalised[json_key] = matched_values[0] if matched_values else ""
            else:
                normalised[json_key] = matched_values

        logger.info(
            "Keyword classification complete",
            filename=filename,
            classification=normalised,
        )
        return normalised


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _group_terms_by_facet(terms: list[TaxonomyTerm]) -> dict[str, list[str]]:
    """Group taxonomy term values by facet name."""
    facets: dict[str, list[str]] = {}
    for term in terms:
        facets.setdefault(term.facet, [])
        if term.value not in facets[term.facet]:
            facets[term.facet].append(term.value)
    return facets


def _parse_json_response(content: str) -> Optional[dict]:
    """Extract and parse JSON from LLM response text.

    Handles responses that wrap JSON in markdown code blocks.
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?", "", content).strip()
    # Try to find the first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _validate_classification(raw: dict, facets: dict[str, list[str]]) -> dict:
    """
    Filter classification results to only include known taxonomy values.

    Strips any values the LLM hallucinated that don't exist in the taxonomy.
    """
    validated: dict = {}
    for key, value in raw.items():
        # Map json key back to facet name
        if key == "doc_category":
            facet = "doc_categories"
        elif key.endswith("s"):
            facet = key[:-1]  # strip trailing 's': "platforms" → "platform"
        else:
            facet = key

        known_values = facets.get(facet, [])

        if isinstance(value, list):
            validated[key] = [v for v in value if v in known_values]
        elif isinstance(value, str):
            validated[key] = value if value in known_values else ""
        else:
            validated[key] = value

    return validated
