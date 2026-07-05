"""
Tests for the SSRF URL validator (app.core.url_validator).

These tests do NOT require Docker or a live database — they exercise pure Python
logic and mock DNS resolution so they run in any environment.
"""
import socket
from unittest.mock import patch

import pytest

from app.core.url_validator import validate_url, validate_url_safe


# ---------------------------------------------------------------------------
# Helper — mock getaddrinfo so tests don't make real DNS queries
# ---------------------------------------------------------------------------

def _mock_getaddrinfo(resolved_ip: str):
    """Return a side_effect function that always resolves to the given IP."""
    def _inner(hostname, *args, **kwargs):
        # Mimic the shape returned by socket.getaddrinfo
        # (family, type, proto, canonname, sockaddr)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_ip, 80))]
    return _inner


# ---------------------------------------------------------------------------
# Scheme validation
# ---------------------------------------------------------------------------

class TestSchemeValidation:
    def test_http_scheme_allowed(self):
        with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
            result = validate_url("http://example.com/path")
        assert result == "http://example.com/path"

    def test_https_scheme_allowed(self):
        with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
            result = validate_url("https://example.com/")
        assert result == "https://example.com/"

    def test_ftp_scheme_rejected(self):
        with pytest.raises(ValueError, match="ftp"):
            validate_url("ftp://example.com/file")

    def test_file_scheme_rejected(self):
        with pytest.raises(ValueError, match="file"):
            validate_url("file:///etc/passwd")

    def test_gopher_scheme_rejected(self):
        with pytest.raises(ValueError, match="gopher"):
            validate_url("gopher://example.com/")

    def test_empty_scheme_rejected(self):
        with pytest.raises(ValueError):
            validate_url("//example.com/no-scheme")


# ---------------------------------------------------------------------------
# IP literal URLs
# ---------------------------------------------------------------------------

class TestIpLiterals:
    def test_loopback_ipv4_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://127.0.0.1/")

    def test_loopback_ipv4_full_range_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://127.255.255.255/admin")

    def test_private_10_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://10.0.0.1/")

    def test_private_172_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://172.16.0.1/")

    def test_private_192_168_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://192.168.1.1/")

    def test_link_local_aws_metadata_blocked(self):
        """AWS metadata endpoint 169.254.169.254 must be blocked."""
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_ipv6_loopback_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://[::1]/")

    def test_ipv6_unique_local_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://[fc00::1]/")

    def test_ipv6_link_local_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://[fe80::1]/")

    def test_zero_network_blocked(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://0.0.0.1/")

    def test_public_ipv4_allowed(self):
        result = validate_url("http://93.184.216.34/")
        assert result == "http://93.184.216.34/"

    def test_public_ipv6_allowed(self):
        result = validate_url("http://[2606:2800:220:1:248:1893:25c8:1946]/")
        assert "2606" in result


# ---------------------------------------------------------------------------
# Decimal / integer-encoded IP (http://2130706433/ == 127.0.0.1)
# ---------------------------------------------------------------------------

class TestDecimalIpEncoding:
    def test_decimal_ip_loopback_blocked(self):
        """http://2130706433/ is 127.0.0.1 in decimal — must be caught."""
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://2130706433/")

    def test_decimal_ip_private_blocked(self):
        """http://167772161/ is 10.0.0.1 in decimal."""
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://167772161/")

    def test_decimal_ip_metadata_blocked(self):
        """169.254.169.254 == 2852039166 in decimal."""
        with pytest.raises(ValueError, match="reserved"):
            validate_url("http://2852039166/")


# ---------------------------------------------------------------------------
# DNS resolution (hostname resolves to internal IP)
# ---------------------------------------------------------------------------

class TestDnsResolution:
    def test_resolves_to_private_blocked(self):
        """A hostname that resolves to 10.0.0.1 must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("10.0.0.1")):
            with pytest.raises(ValueError, match="reserved"):
                validate_url("http://evil.internal.corp/")

    def test_resolves_to_loopback_blocked(self):
        """DNS rebinding: external hostname resolves to 127.0.0.1."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("127.0.0.1")):
            with pytest.raises(ValueError, match="reserved"):
                validate_url("http://rebind.attacker.example.com/")

    def test_resolves_to_aws_metadata_blocked(self):
        with patch("socket.getaddrinfo", _mock_getaddrinfo("169.254.169.254")):
            with pytest.raises(ValueError, match="reserved"):
                validate_url("http://not-metadata.example.com/")

    def test_resolves_to_public_allowed(self):
        with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
            result = validate_url("https://example.com/page")
        assert result == "https://example.com/page"

    def test_unresolvable_hostname_raises(self):
        """If DNS fails we must block, not proceed."""
        def _fail(*args, **kwargs):
            raise socket.gaierror("Name or service not known")

        with patch("socket.getaddrinfo", _fail):
            with pytest.raises(ValueError, match="Cannot resolve"):
                validate_url("http://nonexistent.invalid/")


# ---------------------------------------------------------------------------
# validate_url_safe (non-raising variant)
# ---------------------------------------------------------------------------

class TestValidateUrlSafe:
    def test_unsafe_returns_none(self):
        assert validate_url_safe("http://127.0.0.1/") is None

    def test_safe_returns_url(self):
        with patch("socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")):
            result = validate_url_safe("https://example.com/")
        assert result == "https://example.com/"

    def test_bad_scheme_returns_none(self):
        assert validate_url_safe("file:///etc/passwd") is None


# ---------------------------------------------------------------------------
# SSRF protection bypass (dev mode)
# ---------------------------------------------------------------------------

class TestBypass:
    def test_bypass_allows_localhost(self, monkeypatch):
        """When SSRF_PROTECTION_ENABLED=False, internal URLs must pass through."""
        from app.core import url_validator
        from unittest.mock import MagicMock

        fake_settings = MagicMock()
        fake_settings.ssrf_protection_enabled = False

        monkeypatch.setattr(url_validator, "get_settings", lambda: fake_settings)

        result = validate_url("http://127.0.0.1:8002/health")
        assert result == "http://127.0.0.1:8002/health"

    def test_bypass_allows_private_ip(self, monkeypatch):
        from app.core import url_validator
        from unittest.mock import MagicMock

        fake_settings = MagicMock()
        fake_settings.ssrf_protection_enabled = False

        monkeypatch.setattr(url_validator, "get_settings", lambda: fake_settings)

        result = validate_url("http://192.168.1.50:3000/")
        assert result == "http://192.168.1.50:3000/"
