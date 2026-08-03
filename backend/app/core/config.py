"""
NEXUS — Central configuration.
All environment-dependent values live here so the rest of the app
never touches os.environ directly.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "NEXUS Autonomous Developer Workspace"
    environment: str = "development"
    debug: bool = True

    # Security
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Auth (Google / GitHub / JWT signing)
    jwt_secret: str = "change-me-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"

    # LLM — Groq (OpenAI-compatible API, free-tier friendly)
    # IMPORTANT: Groq's free tier for openai/gpt-oss-120b caps at 8,000
    # tokens PER MINUTE (input + output combined), shared across every
    # call in an orchestration run. A single agent call requesting close
    # to that ceiling can exhaust the entire per-minute budget by
    # itself, causing every subsequent agent (Backend, Frontend, QA,
    # DevOps) in the same run to fail with a 429 rate-limit error —
    # which looks exactly like "generation just stops after Product
    # Management." 3000 leaves realistic headroom for the input prompt
    # + output within one call while still fitting multiple agent calls
    # inside a single TPM window. If you upgrade to Groq's paid
    # Developer tier (much higher TPM), this can be raised significantly.
    groq_api_key: str = ""
    agent_model: str = "openai/gpt-oss-120b"
    max_tokens_per_agent_call: int = 2000

    # Sandbox
    docker_image_python: str = "python:3.12-slim"
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit: str = "256m"

    # Deployment
    deploy_provider: str = "local"  # local | render | fly | aws
    render_api_key: str = ""

    # CORS — kept as a plain string on purpose.
    # pydantic-settings tries to JSON-decode any list/dict-typed field
    # straight from the raw env var, BEFORE any validator runs, which
    # crashes on plain comma-separated strings. Keeping this as `str`
    # sidesteps that entirely; use `allowed_origins_list` below instead
    # of this field directly.
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

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
    return Settings()
