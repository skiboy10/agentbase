"""Tests for library scoring — text overlap, taxonomy boost, ranking."""
import os
import pytest

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"


class TestTextOverlap:
    """Test _text_overlap_score."""

    def test_full_match(self):
        from app.services.discovery.library_scorer import _text_overlap_score
        score = _text_overlap_score(["MeshRouter", "network"], "MeshRouter Network Guide", None)
        assert score == 1.0

    def test_partial_match(self):
        from app.services.discovery.library_scorer import _text_overlap_score
        score = _text_overlap_score(["MeshRouter", "firewall"], "MeshRouter Network Guide", None)
        assert 0 < score < 1.0

    def test_no_match(self):
        from app.services.discovery.library_scorer import _text_overlap_score
        score = _text_overlap_score(["quantum", "physics"], "MeshRouter Network Guide", None)
        assert score == 0.0

    def test_description_match(self):
        from app.services.discovery.library_scorer import _text_overlap_score
        score = _text_overlap_score(
            ["firewall"],
            "Network Library",
            "Contains firewall configuration guides",
        )
        assert score > 0.0

    def test_empty_entities(self):
        from app.services.discovery.library_scorer import _text_overlap_score
        score = _text_overlap_score([], "MeshRouter Network Guide", None)
        assert score == 0.0


class TestTaxonomyBoost:
    """Test _taxonomy_boost."""

    def test_no_terms(self):
        from app.services.discovery.library_scorer import _taxonomy_boost
        boost = _taxonomy_boost(["MeshRouter"], None)
        assert boost == 0.0

    def test_single_match(self):
        from app.services.discovery.library_scorer import _taxonomy_boost
        terms = [{"value": "MeshRouter", "keywords": ["meshify", "meshrouter"]}]
        boost = _taxonomy_boost(["MeshRouter"], terms)
        assert boost == 0.2

    def test_multiple_matches_capped(self):
        from app.services.discovery.library_scorer import _taxonomy_boost
        terms = [
            {"value": "MeshRouter", "keywords": []},
            {"value": "VLAN", "keywords": []},
            {"value": "firewall", "keywords": []},
            {"value": "routing", "keywords": []},
        ]
        boost = _taxonomy_boost(["MeshRouter", "VLAN", "firewall", "routing"], terms)
        assert boost == 0.6  # Capped at 0.6

    def test_keyword_match(self):
        from app.services.discovery.library_scorer import _taxonomy_boost
        terms = [{"value": "Meshify MeshRouter", "keywords": ["meshrouter", "mrtr"]}]
        boost = _taxonomy_boost(["meshrouter"], terms)
        assert boost > 0.0


class TestSizeSignal:
    """Test _size_signal."""

    def test_large_library(self):
        from app.services.discovery.library_scorer import _size_signal
        assert _size_signal(500) == 0.05

    def test_small_library(self):
        from app.services.discovery.library_scorer import _size_signal
        assert _size_signal(50) == 0.0

    def test_boundary(self):
        from app.services.discovery.library_scorer import _size_signal
        assert _size_signal(100) == 0.0
        assert _size_signal(101) == 0.05


class TestScoreLibraries:
    """Test the full scoring pipeline."""

    def test_ranking_order(self):
        from app.services.discovery.library_scorer import score_libraries
        libraries = [
            {"id": "1", "name": "MeshRouter Network Guide", "description": "Complete MeshRouter documentation", "taxonomy_id": None, "chunk_count": 500, "source_count": 3},
            {"id": "2", "name": "AcmeCRM Admin", "description": "AcmeCRM configuration", "taxonomy_id": None, "chunk_count": 300, "source_count": 2},
            {"id": "3", "name": "General IT", "description": "Mixed IT topics", "taxonomy_id": None, "chunk_count": 50, "source_count": 1},
        ]
        scored = score_libraries(["MeshRouter", "network"], libraries)
        assert scored[0].library_id == "1"
        assert scored[0].score > scored[1].score

    def test_empty_libraries(self):
        from app.services.discovery.library_scorer import score_libraries
        scored = score_libraries(["test"], [])
        assert scored == []

    def test_scores_normalized(self):
        from app.services.discovery.library_scorer import score_libraries
        libraries = [
            {"id": "1", "name": "Test Library", "description": None, "taxonomy_id": None, "chunk_count": 200, "source_count": 1},
        ]
        scored = score_libraries(["test"], libraries)
        assert all(0 <= s.score <= 1.0 for s in scored)

    def test_taxonomy_boost_applied(self):
        from app.services.discovery.library_scorer import score_libraries
        libraries = [
            {"id": "1", "name": "Network Docs", "description": None, "taxonomy_id": "t1", "chunk_count": 200, "source_count": 1},
            {"id": "2", "name": "Network Docs 2", "description": None, "taxonomy_id": None, "chunk_count": 200, "source_count": 1},
        ]
        terms = {"1": [{"value": "MeshRouter", "keywords": ["meshrouter"]}]}
        scored = score_libraries(["MeshRouter"], libraries, taxonomy_terms_by_library=terms)
        # Library with taxonomy match should score higher
        lib1 = next(s for s in scored if s.library_id == "1")
        lib2 = next(s for s in scored if s.library_id == "2")
        assert lib1.score > lib2.score

    def test_score_breakdown_present(self):
        from app.services.discovery.library_scorer import score_libraries
        libraries = [
            {"id": "1", "name": "Test", "description": None, "taxonomy_id": None, "chunk_count": 200, "source_count": 1},
        ]
        scored = score_libraries(["test"], libraries)
        assert "text_overlap" in scored[0].score_breakdown
        assert "taxonomy_boost" in scored[0].score_breakdown
        assert "size_signal" in scored[0].score_breakdown
