"""
Tests for coverage gap analysis service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.library.coverage import get_library_coverage, _rate_coverage


class TestRateCoverage:
    """Tests for the _rate_coverage helper."""

    def test_deep(self):
        assert _rate_coverage(20) == "deep"
        assert _rate_coverage(100) == "deep"

    def test_adequate(self):
        assert _rate_coverage(10) == "adequate"
        assert _rate_coverage(19) == "adequate"

    def test_thin(self):
        assert _rate_coverage(1) == "thin"
        assert _rate_coverage(9) == "thin"

    def test_none(self):
        assert _rate_coverage(0) == "none"


class TestGetLibraryCoverage:
    """Tests for get_library_coverage()."""

    @pytest.mark.asyncio
    async def test_library_not_found(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        result = await get_library_coverage(db, "nonexistent")
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_no_taxonomy_linked(self):
        db = AsyncMock()
        library = MagicMock()
        library.id = str(uuid4())
        library.name = "Test Library"
        library.taxonomy_id = None

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = library
        db.execute.return_value = result_mock

        result = await get_library_coverage(db, library.id)
        assert "error" in result
        assert "No taxonomy" in result["error"]

    @pytest.mark.asyncio
    async def test_no_terms(self):
        db = AsyncMock()
        library = MagicMock()
        library.id = str(uuid4())
        library.name = "Test Library"
        library.taxonomy_id = str(uuid4())

        # First call returns library, second returns empty terms
        lib_result = MagicMock()
        lib_result.scalar_one_or_none.return_value = library

        terms_result = MagicMock()
        terms_scalars = MagicMock()
        terms_scalars.all.return_value = []
        terms_result.scalars.return_value = terms_scalars

        db.execute.side_effect = [lib_result, terms_result]

        result = await get_library_coverage(db, library.id)
        assert "error" in result
        assert "no terms" in result["error"].lower()

    @pytest.mark.asyncio
    @patch("app.services.library.coverage.get_qdrant_client")
    async def test_coverage_report_with_terms(self, mock_get_client):
        db = AsyncMock()
        library_id = str(uuid4())
        taxonomy_id = str(uuid4())

        # Mock source with collection
        source1 = MagicMock()
        source1.collection_name = "kb_source_one_abc123"
        source1.status = "indexed"

        library = MagicMock()
        library.id = library_id
        library.name = "Meshify Networking"
        library.taxonomy_id = taxonomy_id
        library.sources = [source1]

        # Mock terms
        term1 = MagicMock()
        term1.facet = "product"
        term1.value = "MeshRouter"

        term2 = MagicMock()
        term2.facet = "product"
        term2.value = "EdgeLink"

        term3 = MagicMock()
        term3.facet = "topic"
        term3.value = "VPN"

        # DB execute calls
        lib_result = MagicMock()
        lib_result.scalar_one_or_none.return_value = library

        terms_result = MagicMock()
        terms_scalars = MagicMock()
        terms_scalars.all.return_value = [term1, term2, term3]
        terms_result.scalars.return_value = terms_scalars

        db.execute.side_effect = [lib_result, terms_result]

        # Mock Qdrant client.
        # coverage.py scrolls ALL points out of each collection and counts
        # term matches in Python (see coverage._scroll_collection_metadata),
        # rather than issuing one filtered count() per term. The facet name
        # is mapped to a metadata key via _facet_to_metadata_key: "product" ->
        # "products", "topic" -> "topics".
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        def _point(metadata):
            p = MagicMock()
            p.payload = {"metadata": metadata}
            return p

        # 25 chunks tagged MeshRouter (deep), 5 tagged EdgeLink (thin),
        # 0 tagged VPN (none). Split across two pages to exercise the
        # scroll pagination loop: a non-None next_offset continues the
        # loop, a None next_offset terminates it.
        page1 = (
            [_point({"products": ["MeshRouter"]}) for _ in range(25)]
            + [_point({"products": ["EdgeLink"]}) for _ in range(3)]
        )
        page2 = [_point({"products": ["EdgeLink"]}) for _ in range(2)]
        mock_client.scroll.side_effect = [
            (page1, "next-page-offset"),
            (page2, None),
        ]

        result = await get_library_coverage(db, library_id)

        assert result["library_id"] == library_id
        assert result["summary"]["total_terms"] == 3
        assert result["summary"]["total_chunks"] == 30
        assert result["summary"]["deep"] == 1
        assert result["summary"]["thin"] == 1
        assert result["summary"]["none"] == 1
        assert len(result["items"]) == 3

        # Exact per-term counts pin the Python-side counting and the
        # facet -> metadata-key mapping (product -> "products").
        assert result["items"][0]["term"] == "MeshRouter"
        assert result["items"][0]["chunk_count"] == 25
        assert result["items"][0]["rating"] == "deep"
        assert result["items"][1]["term"] == "EdgeLink"
        assert result["items"][1]["chunk_count"] == 5
        assert result["items"][1]["rating"] == "thin"
        assert result["items"][2]["term"] == "VPN"
        assert result["items"][2]["chunk_count"] == 0
        assert result["items"][2]["rating"] == "none"
