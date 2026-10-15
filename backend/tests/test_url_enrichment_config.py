"""URL/YouTube enrichment helper honors enrichment_enabled (#20)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ingestion.indexers.base import BaseIndexer


def test_build_enrichment_config_disabled_by_default():
    indexer = BaseIndexer(db=MagicMock())
    source = SimpleNamespace(
        enrichment_enabled=False,
        enrichment_taxonomy_id="tax-1",
        enrichment_model=None,
    )
    cfg = indexer._build_enrichment_config(source)
    assert cfg.enabled is False
    assert cfg.document_type_detection is False


def test_build_enrichment_config_enabled():
    indexer = BaseIndexer(db=MagicMock())
    source = SimpleNamespace(
        enrichment_enabled=True,
        enrichment_taxonomy_id="tax-1",
        enrichment_model="qwen2.5:7b-instruct",
    )
    cfg = indexer._build_enrichment_config(source)
    assert cfg.enabled is True
    assert cfg.taxonomy_id == "tax-1"
    assert cfg.document_type_detection is True


@pytest.mark.asyncio
async def test_run_enrichment_skips_when_disabled():
    indexer = BaseIndexer(db=MagicMock())
    source = SimpleNamespace(
        enrichment_enabled=False,
        enrichment_taxonomy_id=None,
        enrichment_model=None,
    )
    result = await indexer._run_enrichment(source, "hello world", "page.html")
    assert result["cleaned_text"] == "hello world"
    assert result["classification"] is None
    assert result["enrichment_fields"] == {}


@pytest.mark.asyncio
async def test_run_enrichment_calls_service_when_enabled():
    indexer = BaseIndexer(db=MagicMock())
    source = SimpleNamespace(
        enrichment_enabled=True,
        enrichment_taxonomy_id="tax-1",
        enrichment_model="qwen2.5:7b-instruct",
    )
    mock_svc = MagicMock()
    mock_svc.enrich = AsyncMock(return_value={
        "cleaned_text": "cleaned",
        "document_type": "standard",
        "classification": {"platforms": ["AcmeCRM"]},
        "classification_method": "llm",
        "taxonomy_id": "tax-1",
        "taxonomy_version": 2,
    })
    indexer._enrichment_service = mock_svc

    result = await indexer._run_enrichment(source, "raw", "doc.md")
    assert result["cleaned_text"] == "cleaned"
    assert result["classification"] == {"platforms": ["AcmeCRM"]}
    assert result["enrichment_fields"]["taxonomy_id"] == "tax-1"
    assert result["enrichment_fields"]["classification_taxonomy_version"] == 2
    mock_svc.enrich.assert_awaited_once()
