from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL (async driver for the FastAPI app)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_backend"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    @property
    def sync_database_url(self) -> str:
        """Sync (psycopg2) equivalent of database_url, used by Celery workers."""
        return self.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

    # JWT
    jwt_secret_key: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Redis (caching, rate limiting, Celery broker/backend)
    # 127.0.0.1 (not "localhost") avoids slow IPv6-then-IPv4 dual-stack
    # resolution delays when Redis is unreachable.
    redis_url: str = "redis://127.0.0.1:6379/0"
    cache_ttl_seconds: int = 30

    # Celery
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = False

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    # Rate limiting (requests per period, e.g. "5/minute")
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "5/minute"
    rate_limit_ai_generate: str = "10/minute"

    # Security / environment
    environment: str = "development"
    allowed_origins: str = "http://localhost:3000"
    enable_docs: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    app_name: str = "AI-Powered Applications Backend Platform"


settings = Settings()
