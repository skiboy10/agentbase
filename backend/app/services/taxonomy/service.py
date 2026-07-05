"""
Taxonomy Service — manage classification frameworks and their terms.

Provides CRUD for Taxonomy and TaxonomyTerm, plus bulk import from
the taxonomy.json format used by enrichment pipelines.
"""
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Taxonomy, TaxonomyTerm

logger = structlog.get_logger()


class TaxonomyService:
    """
    Manages taxonomy entities and their terms.

    A taxonomy is a named classification framework (optionally project-scoped).
    Terms are grouped into facets (e.g., "platform", "product") with optional
    hierarchy and keyword lists for auto-classification.
    """

    # ------------------------------------------------------------------ #
    # Taxonomy CRUD
    # ------------------------------------------------------------------ #

    async def create_taxonomy(
        self,
        db: AsyncSession,
        name: str,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Taxonomy:
        """Create a new taxonomy.

        Pass project_id=None to create a global taxonomy visible to all projects.
        """
        taxonomy = Taxonomy(
            name=name,
            description=description,
            project_id=project_id,
        )
        db.add(taxonomy)
        await db.flush()
        logger.info("Created taxonomy", taxonomy_id=taxonomy.id, name=name, project_id=project_id)
        return taxonomy

    async def get_taxonomy(self, db: AsyncSession, taxonomy_id: str) -> Optional[Taxonomy]:
        """Fetch a taxonomy with all its terms eagerly loaded."""
        stmt = (
            select(Taxonomy)
            .options(selectinload(Taxonomy.terms))
            .where(Taxonomy.id == taxonomy_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_taxonomies(
        self,
        db: AsyncSession,
        project_id: Optional[str] = None,
    ) -> list[tuple[Taxonomy, int]]:
        """List taxonomies with their term counts, optionally scoped to a project.

        Returns a list of (Taxonomy, term_count) tuples. Term counts are computed
        in SQL via LEFT OUTER JOIN so unloaded `Taxonomy.terms` is never accessed
        in async context.

        When project_id is provided, returns both that project's taxonomies
        and all global (project_id=NULL) taxonomies.
        When project_id is None, returns all taxonomies.
        """
        term_count = func.count(TaxonomyTerm.id).label("term_count")
        stmt = (
            select(Taxonomy, term_count)
            .outerjoin(TaxonomyTerm, TaxonomyTerm.taxonomy_id == Taxonomy.id)
            .group_by(Taxonomy.id)
            .order_by(Taxonomy.name)
        )
        if project_id:
            stmt = stmt.where(
                (Taxonomy.project_id == project_id) |
                (Taxonomy.project_id.is_(None))
            )

        result = await db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def update_taxonomy(
        self,
        db: AsyncSession,
        taxonomy_id: str,
        **kwargs,
    ) -> Optional[Taxonomy]:
        """Update taxonomy fields. Allowed kwargs: name, description, version."""
        taxonomy = await self.get_taxonomy(db, taxonomy_id)
        if not taxonomy:
            return None

        allowed = {"name", "description", "version"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(taxonomy, key, value)

        await db.flush()
        logger.info("Updated taxonomy", taxonomy_id=taxonomy_id, fields=list(kwargs.keys()))
        return taxonomy

    async def delete_taxonomy(self, db: AsyncSession, taxonomy_id: str) -> bool:
        """Delete a taxonomy and all its terms (cascade). Returns True if deleted."""
        taxonomy = await self.get_taxonomy(db, taxonomy_id)
        if taxonomy:
            await db.delete(taxonomy)
            await db.flush()
            logger.info("Deleted taxonomy", taxonomy_id=taxonomy_id)
            return True
        return False

    # ------------------------------------------------------------------ #
    # Term management
    # ------------------------------------------------------------------ #

    async def add_terms(
        self,
        db: AsyncSession,
        taxonomy_id: str,
        terms: list[dict],
    ) -> list[TaxonomyTerm]:
        """Add terms to an existing taxonomy.

        Each dict in terms may include:
            facet (required), value (required), parent_value, keywords, sort_order
        """
        created: list[TaxonomyTerm] = []
        for term_data in terms:
            term = TaxonomyTerm(
                taxonomy_id=taxonomy_id,
                facet=term_data["facet"],
                value=term_data["value"],
                parent_value=term_data.get("parent_value"),
                keywords=term_data.get("keywords"),
                sort_order=term_data.get("sort_order", 0),
            )
            db.add(term)
            created.append(term)

        await db.flush()
        logger.info("Added terms to taxonomy", taxonomy_id=taxonomy_id, count=len(created))
        return created

    async def update_term(
        self,
        db: AsyncSession,
        term_id: str,
        **kwargs,
    ) -> Optional[TaxonomyTerm]:
        """Update a taxonomy term. Allowed kwargs: value, parent_value, keywords, sort_order."""
        stmt = select(TaxonomyTerm).where(TaxonomyTerm.id == term_id)
        result = await db.execute(stmt)
        term = result.scalar_one_or_none()
        if not term:
            return None

        allowed = {"value", "parent_value", "keywords", "sort_order"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(term, key, value)

        await db.flush()
        return term

    async def delete_term(self, db: AsyncSession, term_id: str) -> bool:
        """Delete a single taxonomy term. Returns True if deleted."""
        stmt = select(TaxonomyTerm).where(TaxonomyTerm.id == term_id)
        result = await db.execute(stmt)
        term = result.scalar_one_or_none()
        if term:
            await db.delete(term)
            await db.flush()
            return True
        return False

    # ------------------------------------------------------------------ #
    # Analytics helpers
    # ------------------------------------------------------------------ #

    async def get_facets(self, db: AsyncSession, taxonomy_id: str) -> dict[str, int]:
        """Return a mapping of facet name → term count for a taxonomy.

        Example: {"platform": 4, "product": 12, "offering": 7}
        """
        stmt = (
            select(TaxonomyTerm.facet, func.count(TaxonomyTerm.id).label("count"))
            .where(TaxonomyTerm.taxonomy_id == taxonomy_id)
            .group_by(TaxonomyTerm.facet)
            .order_by(TaxonomyTerm.facet)
        )
        result = await db.execute(stmt)
        return {row.facet: row.count for row in result.all()}

    # ------------------------------------------------------------------ #
    # Bulk import
    # ------------------------------------------------------------------ #

    async def import_from_json(
        self,
        db: AsyncSession,
        taxonomy_id: str,
        json_data: dict,
    ) -> Optional[Taxonomy]:
        """Bulk-import terms from a taxonomy.json-style dict.

        Expected format:
            {
                "platforms": {
                    "ACME Cloud": ["acme cloud", "acme"],
                    "Globex Platform": ["globex"]
                },
                "products": {
                    "Analytics Suite": ["analytics suite", "analytics"]
                }
            }

        Top-level keys become facet names (lowercased, stripped of trailing 's'
        to keep consistent: "platforms" → "platform").
        Dict values are {term_value: [keyword, ...]} pairs.
        """
        # Known facet name mappings (plural JSON keys -> singular facet names)
        FACET_MAP = {
            "platforms": "platform",
            "products": "product",
            "offerings": "offering",
            "companies": "company",
            "topics": "topic",
            "doc_categories": "doc_category",
        }

        terms_to_add: list[dict] = []
        sort_counter = 0

        for raw_facet, entries in json_data.items():
            # Skip metadata keys (start with _)
            if raw_facet.startswith("_"):
                continue

            # Map facet name: use known mapping or lowercase as-is
            facet = FACET_MAP.get(raw_facet.lower(), raw_facet.lower())

            if isinstance(entries, dict):
                for value, keywords in entries.items():
                    # Skip metadata/comment entries (start with _)
                    if str(value).startswith("_"):
                        continue
                    terms_to_add.append({
                        "facet": facet,
                        "value": value,
                        "keywords": keywords if isinstance(keywords, list) else [],
                        "sort_order": sort_counter,
                    })
                    sort_counter += 1
            elif isinstance(entries, list):
                # Simple list format: ["Value1", "Value2"]
                for value in entries:
                    terms_to_add.append({
                        "facet": facet,
                        "value": str(value),
                        "keywords": [],
                        "sort_order": sort_counter,
                    })
                    sort_counter += 1

        if terms_to_add:
            await self.add_terms(db, taxonomy_id, terms_to_add)

        logger.info(
            "Imported taxonomy from JSON",
            taxonomy_id=taxonomy_id,
            term_count=len(terms_to_add),
        )
        return await self.get_taxonomy(db, taxonomy_id)
