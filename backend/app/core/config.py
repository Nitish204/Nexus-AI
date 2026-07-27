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

    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"

    # LLM — Groq (OpenAI-compatible API, free-tier friendly)
    # Note: Groq's model lineup changes often — verify against
    # https://console.groq.com/docs/models before deploying. As of
    # mid-2026, llama-3.3-70b-versatile is deprecated; gpt-oss-120b is
    # the recommended general-purpose replacement.
    groq_api_key: str = ""
    agent_model: str = "openai/gpt-oss-120b"
    max_tokens_per_agent_call: int = 4096

    # Sandbox
    docker_image_python: str = "python:3.12-slim"
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit: str = "256m"

    # Deployment
    deploy_provider: str = "local"  # local | render | fly | aws
    render_api_key: str = ""

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
