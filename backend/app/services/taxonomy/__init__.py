"""
Taxonomy service package.

Manages classification frameworks (taxonomies) and their terms.
Used by knowledge enrichment pipelines and the Taxonomy API.

Usage:
    from app.services.taxonomy import TaxonomyService
"""
from .service import TaxonomyService
from .suggestions import TaxonomySuggestionService
from .analytics import TaxonomyCoverageService

__all__ = ["TaxonomyService", "TaxonomySuggestionService", "TaxonomyCoverageService"]
