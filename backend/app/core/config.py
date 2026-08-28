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
    groq_api_key: str = ""
    agent_model: str = "openai/gpt-oss-120b"
    max_tokens_per_agent_call: int = 2000

    # LLM provider switch — "groq" (cloud, default) or "local" (any
    # OpenAI-compatible local server: Ollama, LM Studio, vLLM, llama.cpp
    # server). Local mode needs no API key and never leaves the machine.
    llm_provider: str = "groq"  # groq | local
    local_llm_base_url: str = "http://localhost:11434/v1"  # Ollama's default OpenAI-compatible endpoint
    local_llm_model: str = "llama3.1"

    # GitHub repo export
    github_export_token: str = ""  # a GitHub PAT with 'repo' scope, used server-side to create/push repos

    # Plugin marketplace
    plugins_registry_path: str = "app/plugins/registry.json"

    # Sandbox
    docker_image_python: str = "python:3.12-slim"
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit: str = "256m"

    # Deployment
    deploy_provider: str = "local"  # local | render | fly | aws
    render_api_key: str = ""

    # CORS — kept as a plain string on purpose.
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
