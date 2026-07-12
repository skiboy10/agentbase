"""
Tests for taxonomy coverage analytics (TaxonomyCoverageService).

Covers the classification-key convention (facets are stored pluralized by
the enrichment pipeline), source-level taxonomy scoping, and stale
document detection.
"""
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentContent, Source, Taxonomy, TaxonomyTerm
from app.services.taxonomy.analytics import TaxonomyCoverageService
from app.services.taxonomy.facets import facet_to_classification_key


class TestFacetToClassificationKey:
    def test_pluralizes_facet(self):
        assert facet_to_classification_key("platform") == "platforms"
        assert facet_to_classification_key("System") == "Systems"

    def test_doc_categories_special_case(self):
        assert facet_to_classification_key("doc_categories") == "doc_category"


def _make_doc(source_id: str, url: str, **kwargs) -> DocumentContent:
    content = kwargs.pop("raw_content", "test content")
    return DocumentContent(
        id=str(uuid4()),
        source_id=source_id,
        url=url,
        raw_content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        content_length=len(content),
        **kwargs,
    )


async def _seed_taxonomy(db: AsyncSession, version: int = 1) -> Taxonomy:
    taxonomy = Taxonomy(id=str(uuid4()), name="Test Taxonomy", version=version)
    db.add(taxonomy)
    for facet, value in [
        ("platform", "AcmeCRM"),
        ("platform", "AcmeERP"),
        ("doc_categories", "guide"),
    ]:
        db.add(TaxonomyTerm(
            id=str(uuid4()), taxonomy_id=taxonomy.id, facet=facet, value=value,
        ))
    await db.commit()
    return taxonomy


async def _seed_source(db: AsyncSession, taxonomy_id: str | None) -> Source:
    source = Source(
        id=str(uuid4()),
        name="Test Source",
        source_type="directory",
        source_path="/tmp/acme",
        status="indexed",
        enrichment_enabled=taxonomy_id is not None,
        enrichment_taxonomy_id=taxonomy_id,
    )
    db.add(source)
    await db.commit()
    return source


class TestGetCoverage:
    @pytest.mark.asyncio
    async def test_counts_pluralized_classification_keys(self, db_session):
        """Enrichment stores {"platforms": [...]} for facet "platform" —
        coverage must count those documents as classified."""
        taxonomy = await _seed_taxonomy(db_session)
        source = await _seed_source(db_session, taxonomy.id)

        db_session.add(_make_doc(
            source.id, "/tmp/acme/a.pdf",
            taxonomy_id=taxonomy.id,
            classification={"platforms": ["AcmeCRM"], "doc_category": "guide"},
            classification_taxonomy_version=1,
        ))
        db_session.add(_make_doc(
            source.id, "/tmp/acme/b.pdf",
            taxonomy_id=taxonomy.id,
            classification={"platforms": ["AcmeCRM", "AcmeERP"], "doc_category": ""},
            classification_taxonomy_version=1,
        ))
        # Unclassified document
        db_session.add(_make_doc(source.id, "/tmp/acme/c.pdf", taxonomy_id=taxonomy.id))
        await db_session.commit()

        svc = TaxonomyCoverageService(db_session)
        report = await svc.get_coverage(taxonomy.id)

        assert report["total_documents"] == 3
        assert report["classified_documents"] == 2
        assert report["unclassified_documents"] == 1
        assert report["coverage_percent"] == 66.7
        assert report["facet_coverage"]["platform"]["covered"] == 2
        # Empty doc_category string does not count as covered
        assert report["facet_coverage"]["doc_categories"]["covered"] == 1
        usage = {t["value"]: t["count"] for t in report["term_usage"]["platform"]}
        assert usage == {"AcmeCRM": 2, "AcmeERP": 1}

    @pytest.mark.asyncio
    async def test_scopes_by_source_enrichment_taxonomy(self, db_session):
        """Documents without a per-row taxonomy_id still count when their
        source is enriched against the taxonomy (pre-fix rows)."""
        taxonomy = await _seed_taxonomy(db_session)
        source = await _seed_source(db_session, taxonomy.id)
        other_source = await _seed_source(db_session, None)

        # Legacy row: no taxonomy_id on the document itself
        db_session.add(_make_doc(
            source.id, "/tmp/acme/legacy.pdf",
            classification={"platforms": ["AcmeCRM"]},
        ))
        # Unrelated source document must not be counted
        db_session.add(_make_doc(other_source.id, "/tmp/other/x.pdf"))
        await db_session.commit()

        report = await TaxonomyCoverageService(db_session).get_coverage(taxonomy.id)
        assert report["total_documents"] == 1
        assert report["classified_documents"] == 1
        assert report["coverage_percent"] == 100.0

    @pytest.mark.asyncio
    async def test_empty_when_no_documents(self, db_session):
        taxonomy = await _seed_taxonomy(db_session)
        report = await TaxonomyCoverageService(db_session).get_coverage(taxonomy.id)
        assert report["total_documents"] == 0
        assert report["coverage_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_missing_taxonomy_returns_empty_dict(self, db_session):
        report = await TaxonomyCoverageService(db_session).get_coverage(str(uuid4()))
        assert report == {}


class TestStaleDetection:
    @pytest.mark.asyncio
    async def test_counts_outdated_and_unclassified(self, db_session):
        taxonomy = await _seed_taxonomy(db_session, version=2)
        source = await _seed_source(db_session, taxonomy.id)

        # Classified at old taxonomy version -> stale
        db_session.add(_make_doc(
            source.id, "/tmp/acme/old.pdf",
            taxonomy_id=taxonomy.id,
            classification={"platforms": ["AcmeCRM"]},
            classification_taxonomy_version=1,
        ))
        # Never classified -> stale
        db_session.add(_make_doc(source.id, "/tmp/acme/never.pdf"))
        # Current -> not stale
        db_session.add(_make_doc(
            source.id, "/tmp/acme/current.pdf",
            taxonomy_id=taxonomy.id,
            classification={"platforms": ["AcmeERP"]},
            classification_taxonomy_version=2,
        ))
        await db_session.commit()

        svc = TaxonomyCoverageService(db_session)
        assert await svc.count_stale(taxonomy.id) == 2

        stale_docs = await svc.get_stale_documents(taxonomy.id)
        stale_urls = {d.url for d in stale_docs}
        assert stale_urls == {"/tmp/acme/old.pdf", "/tmp/acme/never.pdf"}


class TestCoverageAPI:
    @pytest.mark.asyncio
    async def test_coverage_endpoint(self, client, db_session):
        taxonomy = await _seed_taxonomy(db_session)
        source = await _seed_source(db_session, taxonomy.id)
        db_session.add(_make_doc(
            source.id, "/tmp/acme/a.pdf",
            taxonomy_id=taxonomy.id,
            classification={"platforms": ["AcmeCRM"]},
            classification_taxonomy_version=1,
        ))
        await db_session.commit()

        resp = await client.get(f"/api/taxonomies/{taxonomy.id}/coverage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_documents"] == 1
        assert body["classified_documents"] == 1
        assert body["coverage_percent"] == 100.0

        resp = await client.get(f"/api/taxonomies/{taxonomy.id}/stale/count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
