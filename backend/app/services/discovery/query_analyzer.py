"""
Query analysis for library discovery.

Extracts entities, detects complexity, and identifies domain signals
from search queries — all without LLM dependency.
"""
from dataclasses import dataclass, field


# Common English stopwords to filter out
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "through", "during", "before", "after", "about", "between",
    "under", "above", "up", "down", "out", "off", "over", "again",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than", "too",
    "very", "just", "because", "if", "when", "where", "how", "what",
    "which", "who", "whom", "this", "that", "these", "those",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his",
    "she", "her", "it", "its", "they", "them", "their",
})

# Patterns that indicate exploratory queries
_EXPLORATORY_PATTERNS = [
    "how does", "how do", "how to", "what is", "what are", "what does",
    "explain", "overview", "introduction", "guide", "tutorial",
    "tell me about", "describe", "understand",
]

# Patterns that indicate multi-faceted queries
_CONJUNCTION_PATTERNS = ["and", "or", "vs", "versus", "compared to", "difference between"]


@dataclass
class QueryAnalysis:
    """Result of analyzing a search query."""
    original_query: str
    key_entities: list[str] = field(default_factory=list)
    query_complexity: str = "simple"  # simple, multi-faceted, exploratory
    detected_domain: str | None = None
    domain_confidence: float = 0.0
    suggested_method: str = "hybrid"
    token_count: int = 0


def _extract_entities(query: str) -> list[str]:
    """Extract key entities from a query string.

    Identifies capitalized terms, multi-word phrases, and significant
    non-stopword tokens.
    """
    tokens = query.split()
    entities = []

    # First pass: find capitalized multi-word phrases (e.g., "MeshRouter Network")
    i = 0
    while i < len(tokens):
        if tokens[i] and tokens[i][0].isupper():
            # Collect consecutive capitalized words
            phrase_parts = [tokens[i]]
            j = i + 1
            while j < len(tokens) and tokens[j] and tokens[j][0].isupper():
                phrase_parts.append(tokens[j])
                j += 1
            if len(phrase_parts) > 1:
                entities.append(" ".join(phrase_parts))
            else:
                entities.append(phrase_parts[0])
            i = j
        else:
            i += 1

    # Second pass: add significant non-stopword tokens not already captured
    for token in tokens:
        cleaned = token.strip(".,;:!?\"'()[]{}").lower()
        if cleaned and cleaned not in _STOPWORDS and len(cleaned) > 2:
            # Check if already captured (case-insensitive)
            already_captured = any(
                cleaned.lower() in e.lower() for e in entities
            )
            if not already_captured:
                entities.append(cleaned)

    return entities


def _detect_complexity(query: str, token_count: int) -> str:
    """Detect query complexity: simple, multi-faceted, or exploratory."""
    query_lower = query.lower()

    # Check exploratory patterns first
    for pattern in _EXPLORATORY_PATTERNS:
        if pattern in query_lower:
            return "exploratory"

    # Check for multi-faceted indicators
    if token_count >= 15:
        return "multi-faceted"

    for pattern in _CONJUNCTION_PATTERNS:
        # Check as whole word
        if f" {pattern} " in f" {query_lower} ":
            return "multi-faceted"

    # Check for multiple clauses (commas, semicolons)
    if query.count(",") >= 2 or ";" in query:
        return "multi-faceted"

    return "simple"


def _detect_domain(
    entities: list[str],
    taxonomy_vocab: dict[str, list[str]] | None = None,
) -> tuple[str | None, float]:
    """Match query entities against known taxonomy vocabulary.

    Returns (domain_hint, confidence) where domain_hint is the best-matching
    facet name, and confidence is 0-1.
    """
    if not taxonomy_vocab or not entities:
        return None, 0.0

    best_facet = None
    best_score = 0.0

    for facet, terms in taxonomy_vocab.items():
        matches = 0
        for entity in entities:
            entity_lower = entity.lower()
            for term in terms:
                if entity_lower == term.lower() or entity_lower in term.lower() or term.lower() in entity_lower:
                    matches += 1
                    break
        if matches > 0:
            score = matches / len(entities)
            if score > best_score:
                best_score = score
                best_facet = facet

    return best_facet, round(min(best_score, 1.0), 2)


def analyze_query(
    query: str,
    taxonomy_vocab: dict[str, list[str]] | None = None,
) -> QueryAnalysis:
    """Analyze a search query for library discovery.

    Args:
        query: The raw search query string
        taxonomy_vocab: Optional dict of {facet: [term_values]} from taxonomies

    Returns:
        QueryAnalysis with extracted entities, complexity, and domain signals
    """
    tokens = query.split()
    token_count = len(tokens)

    entities = _extract_entities(query)
    complexity = _detect_complexity(query, token_count)
    domain, domain_conf = _detect_domain(entities, taxonomy_vocab)

    # Determine suggested method based on complexity
    from app.services.discovery.method_selector import select_method
    suggested, _ = select_method(QueryAnalysis(
        original_query=query,
        key_entities=entities,
        query_complexity=complexity,
        token_count=token_count,
    ))

    return QueryAnalysis(
        original_query=query,
        key_entities=entities,
        query_complexity=complexity,
        detected_domain=domain,
        domain_confidence=domain_conf,
        suggested_method=suggested,
        token_count=token_count,
    )
