"""
Reciprocal Rank Fusion (RRF) utilities for merging search results.
"""
from .types import SearchResult


def reciprocal_rank_fusion(
    result_lists: list[list[SearchResult]],
    k: int = 60
) -> list[SearchResult]:
    """
    Merge multiple ranked lists using Reciprocal Rank Fusion (RRF).

    RRF is a simple and effective method for combining ranked results from
    different retrieval systems. It's particularly useful when the scores
    from different systems are not directly comparable (e.g., different
    embedding models).

    Formula: RRF_score(d) = sum(1 / (k + rank(d))) for each list where d appears

    The constant k (default 60) controls how much to diminish the contribution
    of lower-ranked documents. Higher k values make the ranking more uniform.

    Args:
        result_lists: List of ranked result lists, each from a different source/model
        k: RRF constant (typically 60, as per original paper)

    Returns:
        List of SearchResults sorted by combined RRF score (highest first)
    """
    if not result_lists:
        return []

    if len(result_lists) == 1:
        return result_lists[0]

    # Track scores and results by a unique identifier
    # Using (source, content_hash or content[:100]) as identifier
    scores: dict[str, float] = {}
    results_by_id: dict[str, SearchResult] = {}

    for result_list in result_lists:
        for rank, result in enumerate(result_list):
            # Create unique identifier for this result
            content_hash = result.metadata.get("content_hash", "")
            if content_hash:
                doc_id = f"{result.source}:{content_hash}"
            else:
                # Fallback to source + content prefix
                doc_id = f"{result.source}:{hash(result.content[:200])}"

            # Calculate RRF contribution: 1 / (k + rank + 1)
            # rank is 0-indexed, so we add 1 to make it 1-indexed
            rrf_contribution = 1.0 / (k + rank + 1)

            if doc_id in scores:
                scores[doc_id] += rrf_contribution
            else:
                scores[doc_id] = rrf_contribution
                results_by_id[doc_id] = result

    # Sort by combined score (highest first) and create new results with RRF scores
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    merged_results = []
    for doc_id in sorted_ids:
        result = results_by_id[doc_id]
        # Create a new SearchResult with the RRF score
        merged_results.append(SearchResult(
            content=result.content,
            source=result.source,
            score=scores[doc_id],  # RRF score
            metadata={
                **result.metadata,
                "original_score": result.score,  # Preserve original score
                "fusion_method": "rrf",
            }
        ))

    return merged_results


def weighted_rrf(
    vector_results: dict,
    text_results: dict,
    vector_weight: float = 0.7,
    k: int = 60,
) -> list[SearchResult]:
    """
    Combine rankings using weighted Reciprocal Rank Fusion.

    Used for hybrid search to combine vector and text search results.

    Args:
        vector_results: Dict of id -> (SearchResult, rank) from vector search
        text_results: Dict of id -> (SearchResult, rank) from text search
        vector_weight: Weight for vector search contribution (0-1)
        k: RRF constant (typically 60)

    Returns:
        List of SearchResults sorted by combined RRF score
    """
    scores = {}
    results_by_id = {}

    # Score from vector search
    for doc_id, (result, rank) in vector_results.items():
        scores[doc_id] = vector_weight / (k + rank + 1)
        results_by_id[doc_id] = result

    # Score from text search
    text_weight = 1 - vector_weight
    for doc_id, (result, rank) in text_results.items():
        if doc_id in scores:
            scores[doc_id] += text_weight / (k + rank + 1)
        else:
            scores[doc_id] = text_weight / (k + rank + 1)
            results_by_id[doc_id] = result

    # Sort by combined score and return
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    # Normalize scores to 0-1 range so the top result is ~1.0
    if sorted_ids:
        max_score = scores[sorted_ids[0]]
        if max_score > 0:
            for doc_id in sorted_ids:
                scores[doc_id] = scores[doc_id] / max_score

    # Update scores in results
    final_results = []
    for doc_id in sorted_ids:
        result = results_by_id[doc_id]
        # Update score to RRF score
        result.score = scores[doc_id]
        final_results.append(result)

    return final_results
