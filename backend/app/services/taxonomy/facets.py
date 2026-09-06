"""
Facet-name to classification-key mapping.

The enrichment pipeline (app/services/ingestion/enrichment.py) stores
classification results keyed by a pluralized form of the facet name:
facet "platform" -> key "platforms", facet "System" -> key "Systems".
Special case: facet "doc_categories" -> key "doc_category" (singular,
matching the original n8n convention).

Every consumer that reads classification dicts — taxonomy coverage
analytics, library coverage gap analysis — must use this mapping.
"""


def facet_to_classification_key(facet: str) -> str:
    """Map a taxonomy facet name to the key used in classification dicts."""
    if facet == "doc_categories":
        return "doc_category"
    return f"{facet}s"
