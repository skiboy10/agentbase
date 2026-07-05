"""Tests for query analysis — entity extraction, complexity detection, domain matching."""
import os
import pytest

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"


class TestEntityExtraction:
    """Test _extract_entities with various query patterns."""

    def test_capitalized_single_word(self):
        from app.services.discovery.query_analyzer import _extract_entities
        entities = _extract_entities("Configure MeshRouter network")
        # "Configure" and "MeshRouter" are consecutive capitals → grouped as phrase
        assert any("MeshRouter" in e for e in entities)

    def test_capitalized_multi_word_phrase(self):
        from app.services.discovery.query_analyzer import _extract_entities
        entities = _extract_entities("How to set up MeshRouter Prime Hub")
        # Should capture "MeshRouter Prime Hub" as a phrase
        assert any("MeshRouter" in e and "Prime" in e for e in entities)

    def test_stopwords_filtered(self):
        from app.services.discovery.query_analyzer import _extract_entities
        entities = _extract_entities("what is the best way to configure a network")
        lowered = [e.lower() for e in entities]
        assert "the" not in lowered
        assert "is" not in lowered
        assert "a" not in lowered

    def test_short_tokens_filtered(self):
        from app.services.discovery.query_analyzer import _extract_entities
        entities = _extract_entities("go to my API")
        lowered = [e.lower() for e in entities]
        assert "go" not in lowered
        assert "to" not in lowered

    def test_significant_tokens_preserved(self):
        from app.services.discovery.query_analyzer import _extract_entities
        entities = _extract_entities("VLAN isolation guest network security")
        lowered = [e.lower() for e in entities]
        assert "vlan" in lowered or "VLAN" in [e for e in entities]
        assert "isolation" in lowered
        assert "security" in lowered

    def test_empty_query(self):
        from app.services.discovery.query_analyzer import _extract_entities
        entities = _extract_entities("")
        assert entities == []

    def test_punctuation_stripped(self):
        from app.services.discovery.query_analyzer import _extract_entities
        entities = _extract_entities("What about VLANs? (network isolation)")
        lowered = [e.lower() for e in entities]
        assert "vlans" in lowered or any("vlan" in e for e in lowered)


class TestComplexityDetection:
    """Test _detect_complexity with simple, multi-faceted, and exploratory queries."""

    def test_simple_query(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        assert _detect_complexity("MeshRouter guest network setup", 4) == "simple"

    def test_exploratory_how_does(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        assert _detect_complexity("how does VLAN isolation work", 5) == "exploratory"

    def test_exploratory_what_are(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        assert _detect_complexity("what are the best practices for network security", 8) == "exploratory"

    def test_exploratory_explain(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        assert _detect_complexity("explain the difference between access and trunk ports", 8) == "exploratory"

    def test_multifaceted_conjunction(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        assert _detect_complexity("VLAN setup and firewall rules for guest isolation", 8) == "multi-faceted"

    def test_multifaceted_long_query(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        q = "I need to configure network isolation between IoT devices and the main network while allowing specific services through the firewall"
        assert _detect_complexity(q, len(q.split())) == "multi-faceted"

    def test_multifaceted_vs(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        assert _detect_complexity("MeshRouter vs pfRoute for VLAN management", 6) == "multi-faceted"

    def test_multifaceted_multiple_commas(self):
        from app.services.discovery.query_analyzer import _detect_complexity
        assert _detect_complexity("VLANs, firewall rules, DNS, and DHCP", 6) == "multi-faceted"


class TestDomainDetection:
    """Test _detect_domain against taxonomy vocabulary."""

    def test_no_vocab_returns_none(self):
        from app.services.discovery.query_analyzer import _detect_domain
        domain, conf = _detect_domain(["MeshRouter", "network"], None)
        assert domain is None
        assert conf == 0.0

    def test_matching_term(self):
        from app.services.discovery.query_analyzer import _detect_domain
        vocab = {"platforms": ["MeshRouter", "AcmeCRM"], "topics": ["networking", "security"]}
        domain, conf = _detect_domain(["MeshRouter", "network"], vocab)
        assert domain is not None
        assert conf > 0.0

    def test_no_match(self):
        from app.services.discovery.query_analyzer import _detect_domain
        vocab = {"platforms": ["AcmeCRM", "WidgetHub"]}
        domain, conf = _detect_domain(["quantum", "physics"], vocab)
        assert conf == 0.0

    def test_partial_match(self):
        from app.services.discovery.query_analyzer import _detect_domain
        vocab = {"topics": ["networking", "security", "automation"]}
        domain, conf = _detect_domain(["networking", "something"], vocab)
        assert domain == "topics"
        assert 0 < conf <= 1.0


class TestAnalyzeQuery:
    """Test the full analyze_query pipeline."""

    def test_simple_query_analysis(self):
        from app.services.discovery.query_analyzer import analyze_query
        result = analyze_query("MeshRouter guest network")
        assert result.original_query == "MeshRouter guest network"
        assert result.query_complexity == "simple"
        assert len(result.key_entities) > 0
        assert result.token_count == 3

    def test_exploratory_query_analysis(self):
        from app.services.discovery.query_analyzer import analyze_query
        result = analyze_query("how does VLAN isolation protect IoT devices")
        assert result.query_complexity == "exploratory"
        assert result.suggested_method == "hybrid"

    def test_comparison_query_analysis(self):
        from app.services.discovery.query_analyzer import analyze_query
        result = analyze_query("compare MeshRouter and pfRoute VLAN handling")
        assert result.suggested_method == "deep_search"

    def test_with_taxonomy_vocab(self):
        from app.services.discovery.query_analyzer import analyze_query
        vocab = {"platforms": ["MeshRouter", "pfRoute"], "topics": ["VLAN", "firewall"]}
        result = analyze_query("MeshRouter VLAN configuration", taxonomy_vocab=vocab)
        assert result.detected_domain is not None
        assert result.domain_confidence > 0
