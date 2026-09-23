"""
NEXUS — Central configuration.
"""
from __future__ import annotations  # lets `list[str]` type hints work on Python 3.8 too — see allowed_origins_list below

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "NEXUS Autonomous Developer Workspace"
    environment: str = "development"
    debug: bool = True

    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    jwt_secret: str = "change-me-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    github_mobile_client_id: str = ""
    github_mobile_client_secret: str = ""

    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"

    groq_api_key: str = ""
    agent_model: str = "openai/gpt-oss-120b"
    max_tokens_per_agent_call: int = 2000

    llm_provider: str = "groq"  # groq | local
    local_llm_base_url: str = "http://localhost:11434/v1"
    local_llm_model: str = "llama3.1"

    github_export_token: str = ""
    plugins_registry_path: str = "app/plugins/registry.json"

    docker_image_python: str = "python:3.12-slim"
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit: str = "256m"

    deploy_provider: str = "local"
    render_api_key: str = ""

    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"

    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # --- Observability -----------------------------------------------
    # Empty string = disabled. Sentry's own SDK treats dsn=None/"" as a
    # no-op client (every call becomes a cheap in-process discard), so
    # leaving this unset in dev/test never requires special-casing
    # elsewhere — see app/core/observability.py.
    sentry_dsn: str = ""
    # Fraction of requests to capture full performance traces for (0-1).
    # Kept low by default: tracing has real overhead and this is a
    # per-request cost multiplier, not a one-time toggle.
    sentry_traces_sample_rate: float = 0.1
    # Fraction of *profiled* traces (CPU profiling within a trace).
    sentry_profiles_sample_rate: float = 0.0
    # Surfaced to Sentry as the "release" so errors can be bisected to a
    # deploy. Set this from CI to a commit SHA/tag; falls back to
    # "unknown" locally, which is intentionally obvious in the Sentry UI
    # rather than silently blank.
    release_version: str = "unknown"

    # --- LLM cost tracking ---------------------------------------------
    # USD per 1,000,000 tokens, keyed by the exact model string used in
    # AgentBase (settings.agent_model / settings.local_llm_model).
    # These are looked up by app.core.llm_pricing — see that module for
    # the fallback behavior when a model isn't in this table (e.g. a
    # newly released Groq model, or a locally-hosted one, which is
    # always treated as free since nothing leaves the machine).
    llm_pricing_input_per_million: dict[str, float] = Field(
        default_factory=lambda: {
            "openai/gpt-oss-120b": 0.15,
            "openai/gpt-oss-20b": 0.05,
            "llama-3.3-70b-versatile": 0.59,
            "llama-3.1-8b-instant": 0.05,
        }
    )
    llm_pricing_output_per_million: dict[str, float] = Field(
        default_factory=lambda: {
            "openai/gpt-oss-120b": 0.60,
            "openai/gpt-oss-20b": 0.20,
            "llama-3.3-70b-versatile": 0.79,
            "llama-3.1-8b-instant": 0.08,
        }
    )

    # Only set this to True if NEXUS sits behind a proxy/load balancer
    # (nginx, Render, an ALB, etc.) that you control and that overwrites
    # X-Forwarded-For itself. If this is False (the default), the rate
    # limiter ignores that header entirely and falls back to the
    # socket's actual peer address — otherwise anyone can send a random
    # X-Forwarded-For value on every request and dodge rate limiting
    # completely, since the header is just attacker-supplied text.
    trust_proxy_headers: bool = False

    @property
    def allowed_origins_list(self) -> list[str]:
        raw = self.allowed_origins.strip()
        if not raw:
            return []
        if raw.startswith("["):
            import json
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.environment == "production":
        insecure_defaults = {
            "secret_key": "change-me-in-production",
            "jwt_secret": "change-me-in-production",
        }
        for field, default_value in insecure_defaults.items():
            if getattr(s, field) == default_value:
                raise RuntimeError(
                    f"Refusing to start: '{field}' is still set to its insecure default value "
                    f"while ENVIRONMENT=production. Set a real, random {field.upper()} in your "
                    "environment before deploying — leaving this as-is lets anyone forge valid "
                    "auth tokens for any user."
                )
    return s
