"""
TaxonomyCoverageService — coverage analytics and stale classification detection.

Coverage: per-facet coverage percentages and per-term usage counts, computed
from DocumentContent records stored in Postgres.

Stale detection: documents whose classification_taxonomy_version is behind
the current taxonomy.version.
"""
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Taxonomy, TaxonomyTerm, DocumentContent

logger = structlog.get_logger()


class TaxonomyCoverageService:
    """Analytics service for taxonomy coverage and stale document detection."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ #
    # Coverage analytics                                                   #
    # ------------------------------------------------------------------ #

    async def get_coverage(
        self,
        taxonomy_id: str,
        source_id: Optional[str] = None,
    ) -> dict:
        """Calculate classification coverage metrics.

        Returns aggregated stats across all DocumentContent records that
        belong to this taxonomy (optionally scoped to a knowledge source).

        Shape:
            {
                "total_documents": 150,
                "classified_documents": 120,
                "unclassified_documents": 30,
                "coverage_percent": 80.0,
                "facet_coverage": {
                    "platform": {"covered": 110, "total": 150, "percent": 73.3},
                    ...
                },
                "term_usage": {
                    "platform": [
                        {"value": "AcmeCRM", "count": 95},
                        ...
                    ],
                    ...
                },
            }
        """
        taxonomy = await self._get_taxonomy(taxonomy_id)
        if not taxonomy:
            return {}

        docs = await self._fetch_documents(taxonomy_id, source_id)
        total = len(docs)
        if total == 0:
            return self._empty_coverage(total)

        # Determine active facets from terms in the taxonomy
        facets = await self._infer_facets(taxonomy_id)

        classified = 0
        facet_counts: dict[str, int] = {f: 0 for f in facets}
        term_counts: dict[str, dict[str, int]] = {f: {} for f in facets}

        for doc in docs:
            classification = doc.classification or {}
            has_any = False

            for facet in facets:
                values = classification.get(facet) or []
                if values:
                    has_any = True
                    facet_counts[facet] += 1
                    for v in values:
                        term_counts[facet][v] = term_counts[facet].get(v, 0) + 1

            if has_any:
                classified += 1

        unclassified = total - classified
        coverage_percent = round(classified / total * 100, 1) if total else 0.0

        facet_coverage = {}
        for facet in facets:
            covered = facet_counts[facet]
            facet_coverage[facet] = {
                "covered": covered,
                "total": total,
                "percent": round(covered / total * 100, 1) if total else 0.0,
            }

        # Sort term usage by count desc
        term_usage = {}
        for facet in facets:
            sorted_terms = sorted(
                term_counts[facet].items(), key=lambda x: x[1], reverse=True
            )
            term_usage[facet] = [{"value": v, "count": c} for v, c in sorted_terms]

        return {
            "total_documents": total,
            "classified_documents": classified,
            "unclassified_documents": unclassified,
            "coverage_percent": coverage_percent,
            "facet_coverage": facet_coverage,
            "term_usage": term_usage,
        }

    # ------------------------------------------------------------------ #
    # Stale detection                                                      #
    # ------------------------------------------------------------------ #

    async def get_stale_documents(
        self,
        taxonomy_id: str,
        source_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[DocumentContent]:
        """Return documents classified at an older taxonomy version.

        A document is stale when:
          - classification_taxonomy_version < current taxonomy.version, OR
          - classification is null/empty (never classified)
        """
        taxonomy = await self._get_taxonomy(taxonomy_id)
        if not taxonomy:
            return []

        stmt = (
            select(DocumentContent)
            .where(DocumentContent.taxonomy_id == taxonomy_id)
            .where(
                (DocumentContent.classification_taxonomy_version < taxonomy.version)
                | (DocumentContent.classification_taxonomy_version == None)
                | (DocumentContent.classification == None)
            )
        )
        if source_id:
            stmt = stmt.where(DocumentContent.source_id == source_id)
        stmt = stmt.order_by(DocumentContent.updated_at.asc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_stale(
        self,
        taxonomy_id: str,
        source_id: Optional[str] = None,
    ) -> int:
        """Count stale documents for a taxonomy."""
        taxonomy = await self._get_taxonomy(taxonomy_id)
        if not taxonomy:
            return 0

        stmt = (
            select(func.count())
            .select_from(DocumentContent)
            .where(DocumentContent.taxonomy_id == taxonomy_id)
            .where(
                (DocumentContent.classification_taxonomy_version < taxonomy.version)
                | (DocumentContent.classification_taxonomy_version == None)
                | (DocumentContent.classification == None)
            )
        )
        if source_id:
            stmt = stmt.where(DocumentContent.source_id == source_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _get_taxonomy(self, taxonomy_id: str) -> Optional[Taxonomy]:
        result = await self.db.execute(
            select(Taxonomy).where(Taxonomy.id == taxonomy_id)
        )
        return result.scalar_one_or_none()

    async def _fetch_documents(
        self,
        taxonomy_id: str,
        source_id: Optional[str],
    ) -> list[DocumentContent]:
        stmt = select(DocumentContent).where(DocumentContent.taxonomy_id == taxonomy_id)
        if source_id:
            stmt = stmt.where(DocumentContent.source_id == source_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _infer_facets(self, taxonomy_id: str) -> list[str]:
        """Derive distinct facets from the terms table when taxonomy.facets is empty."""
        stmt = (
            select(TaxonomyTerm.facet)
            .where(TaxonomyTerm.taxonomy_id == taxonomy_id)
            .distinct()
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    @staticmethod
    def _empty_coverage(total: int) -> dict:
        return {
            "total_documents": total,
            "classified_documents": 0,
            "unclassified_documents": total,
            "coverage_percent": 0.0,
            "facet_coverage": {},
            "term_usage": {},
        }
