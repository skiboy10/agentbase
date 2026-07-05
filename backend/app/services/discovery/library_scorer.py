"""
Library scoring for discovery.

Ranks libraries by relevance to a query analysis using heuristic scoring
(no LLM dependency). Scoring factors: text overlap, taxonomy term match,
and collection size signal.
"""
from dataclasses import dataclass, field


@dataclass
class ScoredLibrary:
    """A library scored for relevance to a query."""
    library_id: str
    library_name: str
    description: str | None
    score: float
    score_breakdown: dict = field(default_factory=dict)
    taxonomy_id: str | None = None
    chunk_count: int = 0
    source_count: int = 0


def _text_overlap_score(entities: list[str], name: str, description: str | None) -> float:
    """Score based on token overlap between query entities and library text."""
    if not entities:
        return 0.0

    target_text = name.lower()
    if description:
        target_text += " " + description.lower()

    matched = 0
    for entity in entities:
        if entity.lower() in target_text:
            matched += 1

    return matched / len(entities) if entities else 0.0


def _taxonomy_boost(
    entities: list[str],
    taxonomy_terms: list[dict] | None,
) -> float:
    """Boost score for libraries whose taxonomy terms match query entities.

    Each matching taxonomy term adds 0.2 to score, capped at 0.6.

    Args:
        entities: Key entities from query analysis
        taxonomy_terms: List of dicts with 'value' and optional 'keywords' keys
    """
    if not taxonomy_terms or not entities:
        return 0.0

    boost = 0.0
    for term in taxonomy_terms:
        term_value = term.get("value", "").lower()
        term_keywords = [k.lower() for k in term.get("keywords", []) or []]
        all_term_tokens = [term_value] + term_keywords

        for entity in entities:
            entity_lower = entity.lower()
            for token in all_term_tokens:
                if entity_lower == token or entity_lower in token or token in entity_lower:
                    boost += 0.2
                    break
            if boost >= 0.6:
                return 0.6

    return min(boost, 0.6)


def _size_signal(chunk_count: int) -> float:
    """Small boost for libraries with substantial content."""
    return 0.05 if chunk_count > 100 else 0.0


def score_libraries(
    entities: list[str],
    libraries: list[dict],
    taxonomy_terms_by_library: dict[str, list[dict]] | None = None,
) -> list[ScoredLibrary]:
    """Score and rank libraries by relevance to query entities.

    Args:
        entities: Key entities extracted from the query
        libraries: List of library dicts (from _library_to_dict)
        taxonomy_terms_by_library: Optional mapping of library_id -> taxonomy terms

    Returns:
        List of ScoredLibrary sorted by score descending, normalized to 0-1
    """
    if not libraries:
        return []

    taxonomy_terms_by_library = taxonomy_terms_by_library or {}
    scored = []

    for lib in libraries:
        lib_id = lib["id"]
        name = lib.get("name", "")
        description = lib.get("description")
        chunk_count = lib.get("chunk_count", 0)

        text_score = _text_overlap_score(entities, name, description)
        tax_boost = _taxonomy_boost(
            entities,
            taxonomy_terms_by_library.get(lib_id),
        )
        size = _size_signal(chunk_count)

        raw_score = text_score + tax_boost + size

        scored.append(ScoredLibrary(
            library_id=lib_id,
            library_name=name,
            description=description,
            score=raw_score,
            score_breakdown={
                "text_overlap": round(text_score, 3),
                "taxonomy_boost": round(tax_boost, 3),
                "size_signal": round(size, 3),
            },
            taxonomy_id=lib.get("taxonomy_id"),
            chunk_count=chunk_count,
            source_count=lib.get("source_count", 0),
        ))

    # Normalize scores to 0-1
    max_score = max((s.score for s in scored), default=1.0)
    if max_score > 0:
        for s in scored:
            s.score = round(s.score / max_score, 3)

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
