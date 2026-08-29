"""
NEXUS — Central configuration.
All environment-dependent values live here so the rest of the app
never touches os.environ directly.
"""
from functools import lru_cache
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
