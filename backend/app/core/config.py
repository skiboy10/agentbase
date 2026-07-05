"""
Application configuration using Pydantic Settings.
"""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Agentbase"
    debug: bool = False
    secret_key: str = ""

    # Database
    database_url: str = "postgresql://agentbase:agentbase_password@localhost:5432/agentbase"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_prefix: str = "agentbase_"

    # Authentication
    auth_token: Optional[str] = None

    # LLM Providers
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    grok_api_key: Optional[str] = None
    grok_base_url: str = "https://api.x.ai/v1"
    google_api_key: Optional[str] = None
    cohere_api_key: Optional[str] = None
    voyage_api_key: Optional[str] = None

    # Default Model Assignments
    default_knowledge_provider: str = "anthropic"
    default_knowledge_model: str = "claude-sonnet-4-20250514"

    # RAG Configuration
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_concurrency: int = 3  # Parallel embedding requests (match OLLAMA_NUM_PARALLEL)
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 5

    # File Upload
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 200
    allowed_file_extensions: str = ".pdf,.html,.md,.txt"  # Comma-separated for multiple
    max_concurrent_indexing: int = 1  # Max concurrent indexing jobs. Worker is
                                      # sequential, but this also caps how many
                                      # the refresh_scheduler enqueues per cycle
                                      # (see refresh_scheduler._check_and_enqueue_refreshes).

    # Code Preservation
    code_preservation_enabled: bool = True  # Extract and preserve code blocks from HTML
    code_block_languages: str = "javascript,python,sql,html,css"  # Comma-separated

    # Security
    external_hostname: Optional[str] = None  # Tunnel hostname, e.g. "api.example.com"
    debug_mode: bool = False  # Controls Swagger UI visibility
    ssrf_protection_enabled: bool = True  # Block requests to private/reserved IPs. Set False in dev to allow localhost scanning.
    # Comma-separated CORS origins. Do NOT use "*" with allow_credentials=True — the CORS
    # spec (and all browsers) reject that combination. Set explicit origins instead.
    # Example for LAN access: ALLOWED_ORIGINS=http://192.168.1.100:3002
    allowed_origins: str = "http://localhost:3002,http://localhost:3000"
    # Trusted networks for internal access (no auth required).
    # Comma-separated CIDR ranges. Defaults cover loopback + LAN ranges. The
    # Docker bridge (172.16.0.0/12) was intentionally REMOVED from this default
    # in #49: trusting that range made any compromised sibling container an
    # auth-free zone, and proxy-forwarded client IPs are now handled via the
    # secret-gated proxy middleware below (which rewrites request.client.host
    # to the real public IP) rather than by trusting the bridge.
    trusted_networks: str = "127.0.0.1/32,::1/128,10.0.0.0/8,192.168.0.0/16"
    # When True, read the real client IP from the X-Forwarded-For header
    # (first entry).  Only enable this when a trusted reverse proxy sits in
    # front of the backend — never when the backend is directly internet-facing.
    trust_proxy: bool = False
    # Shared secret between nginx and backend that gates trust of the
    # X-Forwarded-For / X-Forwarded-Proto headers (see #49). When set, the
    # custom ProxyHeadersMiddleware in main.py only rewrites request.client.host
    # if the request carries a matching X-Internal-Forward-Secret header — so
    # an attacker reaching the backend port directly cannot spoof XFF.
    # When unset (default), the middleware is a no-op and request.client.host
    # is the raw TCP peer; this keeps local dev/test working out of the box
    # but is INSECURE for any deployment that exposes the backend externally.
    # Generate with: openssl rand -hex 32
    internal_forward_secret: Optional[str] = None

    # Apache Tika (document text extraction)
    tika_url: str = "http://tika:9998"
    tika_timeout: int = 300000  # milliseconds

    # Refresh scheduler
    refresh_check_interval_minutes: int = 60  # How often to check for due automatic refreshes

    # Watcher-event retention (garbage collection)
    watcher_events_gc_interval_hours: int = 24  # How often the GC loop runs
    watcher_events_retention_days: int = 30  # Delete events older than this
    watcher_events_max_per_source: int = 5000  # Hard cap on retained events per source

    # Logging
    log_level: str = "INFO"

    @property
    def providers_configured(self) -> dict[str, bool]:
        """Return which providers have API keys configured."""
        return {
            "ollama": True,  # Ollama doesn't need API key
            "openai": bool(self.openai_api_key),
            "anthropic": bool(self.anthropic_api_key),
            "grok": bool(self.grok_api_key),
            "google": bool(self.google_api_key),
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
