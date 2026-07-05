"""
TaxonomySuggestionService — record, review, and action LLM-suggested terms.

Suggestions are captured during enrichment when the LLM returns a value that
isn't in the taxonomy's valid term set.  A human reviewer can approve (creates
the term), reject, or merge (adds as alias on an existing term).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import TaxonomySuggestion, TaxonomyTerm
from app.services.taxonomy.service import TaxonomyService

logger = structlog.get_logger()

_MAX_SAMPLE_IDS = 5


class TaxonomySuggestionService:
    """Service for managing taxonomy term suggestions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_suggestion(
        self,
        taxonomy_id: str,
        facet: str,
        value: str,
        document_id: Optional[str] = None,
    ) -> TaxonomySuggestion:
        """Record an LLM-suggested term.

        Upserts: increments frequency if suggestion already exists (pending/rejected).
        Rejected suggestions can accumulate frequency — reviewers can reconsider.
        Already-approved/merged suggestions are left alone.
        """
        stmt = select(TaxonomySuggestion).where(
            TaxonomySuggestion.taxonomy_id == taxonomy_id,
            TaxonomySuggestion.facet == facet,
            TaxonomySuggestion.suggested_value == value,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Don't re-record approved/merged suggestions
            if existing.status in ("approved", "merged"):
                return existing
            existing.frequency += 1
            if document_id:
                samples = list(existing.sample_document_ids or [])
                if document_id not in samples:
                    samples.append(document_id)
                    existing.sample_document_ids = samples[:_MAX_SAMPLE_IDS]
            await self.db.flush()
            return existing

        suggestion = TaxonomySuggestion(
            taxonomy_id=taxonomy_id,
            facet=facet,
            suggested_value=value,
            frequency=1,
            sample_document_ids=[document_id] if document_id else [],
            status="pending",
        )
        self.db.add(suggestion)
        await self.db.flush()
        logger.info(
            "taxonomy.suggestion.recorded",
            taxonomy_id=taxonomy_id,
            facet=facet,
            value=value,
        )
        return suggestion

    async def list_suggestions(
        self,
        taxonomy_id: str,
        status: str = "pending",
        limit: int = 50,
    ) -> list[TaxonomySuggestion]:
        """List suggestions sorted by frequency descending."""
        stmt = (
            select(TaxonomySuggestion)
            .where(
                TaxonomySuggestion.taxonomy_id == taxonomy_id,
                TaxonomySuggestion.status == status,
            )
            .order_by(TaxonomySuggestion.frequency.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_suggestion(self, suggestion_id: str) -> Optional[TaxonomySuggestion]:
        """Fetch a single suggestion by ID."""
        stmt = select(TaxonomySuggestion).where(TaxonomySuggestion.id == suggestion_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def approve_suggestion(self, suggestion_id: str) -> Optional[TaxonomyTerm]:
        """Approve a suggestion: create the term in the taxonomy, mark suggestion approved."""
        suggestion = await self.get_suggestion(suggestion_id)
        if not suggestion:
            return None
        if suggestion.status != "pending":
            raise ValueError(f"Suggestion status is '{suggestion.status}', expected 'pending'")

        taxonomy_svc = TaxonomyService()
        terms = await taxonomy_svc.add_terms(
            self.db,
            taxonomy_id=suggestion.taxonomy_id,
            terms=[{"facet": suggestion.facet, "value": suggestion.suggested_value}],
        )
        term = terms[0] if terms else None
        if not term:
            raise ValueError("Failed to create term from suggestion")

        suggestion.status = "approved"
        suggestion.reviewed_at = datetime.utcnow()
        await self.db.flush()
        logger.info(
            "taxonomy.suggestion.approved",
            suggestion_id=suggestion_id,
            term_id=term.id,
        )
        return term

    async def reject_suggestion(self, suggestion_id: str) -> Optional[TaxonomySuggestion]:
        """Mark a suggestion as rejected."""
        suggestion = await self.get_suggestion(suggestion_id)
        if not suggestion:
            return None
        if suggestion.status != "pending":
            raise ValueError(f"Suggestion status is '{suggestion.status}', expected 'pending'")
        suggestion.status = "rejected"
        suggestion.reviewed_at = datetime.utcnow()
        await self.db.flush()
        logger.info("taxonomy.suggestion.rejected", suggestion_id=suggestion_id)
        return suggestion

    async def merge_suggestion(
        self,
        suggestion_id: str,
        merge_into_value: str,
    ) -> Optional[TaxonomySuggestion]:
        """Merge: add suggested value as a keyword alias on an existing term."""
        suggestion = await self.get_suggestion(suggestion_id)
        if not suggestion:
            return None
        if suggestion.status != "pending":
            raise ValueError(f"Suggestion status is '{suggestion.status}', expected 'pending'")

        # Find the target term
        stmt = select(TaxonomyTerm).where(
            TaxonomyTerm.taxonomy_id == suggestion.taxonomy_id,
            TaxonomyTerm.facet == suggestion.facet,
            TaxonomyTerm.value == merge_into_value,
        )
        result = await self.db.execute(stmt)
        target_term = result.scalar_one_or_none()
        if not target_term:
            raise ValueError(f"Term '{merge_into_value}' not found in facet '{suggestion.facet}'")

        # Add suggested value as keyword alias
        keywords = list(target_term.keywords or [])
        if suggestion.suggested_value not in keywords:
            keywords.append(suggestion.suggested_value)
            taxonomy_svc = TaxonomyService()
            await taxonomy_svc.update_term(self.db, target_term.id, keywords=keywords)

        suggestion.status = "merged"
        suggestion.merged_into = merge_into_value
        suggestion.reviewed_at = datetime.utcnow()
        await self.db.flush()
        logger.info(
            "taxonomy.suggestion.merged",
            suggestion_id=suggestion_id,
            merged_into=merge_into_value,
        )
        return suggestion
