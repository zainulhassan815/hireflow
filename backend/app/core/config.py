from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "HR Screening RAG API"
    debug: bool = False
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        description="CORS origins. Comma-separated in .env (e.g. https://a.com,https://b.com).",
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/hr_screening"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # JWT — required, no default. Generate with: openssl rand -hex 32
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Password reset
    password_reset_token_expire_minutes: int = 15

    # File Upload
    max_file_size_mb: int = 10

    # Object storage (MinIO / S3-compatible)
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minio"
    storage_secret_key: SecretStr = Field(default=SecretStr("minio12345"))
    storage_bucket: str = "hireflow-documents"
    storage_region: str = "us-east-1"

    # Gmail OAuth (F50 — optional until that phase)
    gmail_client_id: str | None = None
    gmail_client_secret: SecretStr | None = None
    gmail_redirect_uri: str | None = None

    # Vision OCR provider: claude | ollama | tesseract | none
    vision_provider: str = "tesseract"
    vision_model: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # LLM / Embeddings
    llm_provider: str = "anthropic"
    llm_model: str = "claude-3-haiku-20240307"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()  # fails fast on import if required vars are missing/invalid
