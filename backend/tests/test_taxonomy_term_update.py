"""Tests for taxonomy term PATCH (#21) — unset fields must not clobber NOT NULL columns."""
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Taxonomy, TaxonomyTerm
from app.services.taxonomy.service import TaxonomyService


async def _seed_term(db: AsyncSession) -> TaxonomyTerm:
    taxonomy = Taxonomy(id=str(uuid4()), name="Test Taxonomy", version=1)
    db.add(taxonomy)
    term = TaxonomyTerm(
        id=str(uuid4()),
        taxonomy_id=taxonomy.id,
        facet="platform",
        value="AcmeCRM",
        keywords=["crm"],
        sort_order=7,
    )
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return term


@pytest.mark.asyncio
async def test_update_term_omitting_sort_order_preserves_value(db_session: AsyncSession):
    term = await _seed_term(db_session)
    svc = TaxonomyService()

    updated = await svc.update_term(
        db_session,
        term.id,
        keywords=["crm", "sales"],
        sort_order=None,  # simulate a caller that still forwards None
    )
    await db_session.commit()

    assert updated is not None
    assert updated.keywords == ["crm", "sales"]
    assert updated.sort_order == 7


@pytest.mark.asyncio
async def test_update_term_can_change_sort_order(db_session: AsyncSession):
    term = await _seed_term(db_session)
    svc = TaxonomyService()

    updated = await svc.update_term(db_session, term.id, sort_order=3)
    await db_session.commit()

    assert updated is not None
    assert updated.sort_order == 3


@pytest.mark.asyncio
async def test_patch_term_via_api_omitting_sort_order(client: AsyncClient, db_session: AsyncSession):
    term = await _seed_term(db_session)

    resp = await client.patch(
        f"/api/taxonomies/{term.taxonomy_id}/terms/{term.id}",
        json={"keywords": ["alpha", "beta"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["keywords"] == ["alpha", "beta"]
    assert body["sort_order"] == 7


@pytest.mark.asyncio
async def test_patch_term_label_maps_to_value(client: AsyncClient, db_session: AsyncSession):
    term = await _seed_term(db_session)

    resp = await client.patch(
        f"/api/taxonomies/{term.taxonomy_id}/terms/{term.id}",
        json={"label": "AcmeERP"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["value"] == "AcmeERP"
    assert body["sort_order"] == 7
