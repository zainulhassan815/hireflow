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

    # Embedding provider (F85.a)
    # ``local`` uses sentence-transformers with ``embedding_model`` from
    # the HuggingFace hub. Add ``openai`` / ``voyage`` adapters to switch
    # providers without code changes elsewhere.
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Layout-aware extraction (F82.d) via ``unstructured.partition``.
    # ``fast`` is rule-based (font/indent heuristics), zero GPU, ~1s/page.
    # ``hi_res`` runs a layout detector model + optional table transformer;
    # 5-30s cold start, ~100-300ms/page on GPU. Default ``hi_res`` since
    # the dev box has a GPU.
    extraction_strategy: str = "hi_res"
    # Enable table transformer in hi_res; no-op in fast mode.
    extraction_infer_tables: bool = True

    # Cross-encoder reranker (F80.5)
    # Rerank the merged RRF top-K with a (query, chunk) cross-encoder
    # that attends over both at once. Much more accurate than bi-encoder
    # cosine similarity but slower — only run on a small candidate set.
    # ``none`` falls back to NullReranker (passthrough).
    #
    # Default ``local`` now that F85.c weighted RRF lands — the
    # candidate set is filename-biased before reranking, so the reranker
    # only reshuffles within an already-correct window. Set ``none`` to
    # disable (useful for eval A/B or if bge-reranker-base fails to
    # load).
    reranker_provider: str = "local"
    reranker_model: str = "BAAI/bge-reranker-base"
    # Candidates to hand the reranker. Retrieval runs up to this many,
    # then reranker picks the top-N (N = user's ``limit``).
    reranker_top_k: int = 20

    # Chunk contextualizer (F82.c)
    # - ``llm``: generate context per chunk via the configured LlmProvider
    # - ``none``: skip contextualization entirely (fast path, no LLM cost)
    contextualizer_provider: str = "llm"
    # ``summary``: 1 summary call + N per-chunk calls with the summary.
    # ``full_doc``: every chunk call includes the full doc body (expensive
    #   without prompt caching).
    # ``auto``: pick per-doc based on size vs ``full_doc_max_chars``.
    contextualizer_mode: str = "auto"
    contextualizer_full_doc_max_chars: int = 8000
    # Optional override: if set, the contextualizer uses this model
    # instead of ``llm_model``. Lets RAG use Sonnet while
    # contextualization uses cheap Haiku.
    contextualizer_model: str | None = None

    # JWT — required, no default. Generate with: openssl rand -hex 32
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Field-level encryption (Fernet). Newest key first; older keys still
    # decrypt. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_keys: Annotated[list[SecretStr], NoDecode] = Field(default_factory=list)

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

    # Gmail resume sync (F51)
    gmail_sync_interval_minutes: int = 5
    gmail_sync_max_messages_per_run: int = 100
    gmail_sync_initial_window_days: int = 7
    gmail_sync_claim_timeout_minutes: int = 15

    # Vision OCR provider: claude | ollama | tesseract | none
    vision_provider: str = "tesseract"
    vision_model: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # Search relevance (F80 / F85.d). When ``None``, SearchService
    # asks the configured embedder for its recommended threshold
    # (per-model table in ``SentenceTransformerEmbedder``). Set an
    # explicit float to override for this deploy — rarely needed, but
    # the operator knob is there. Legacy value for bge-small was 0.35;
    # that lives in the embedder's threshold table now.
    search_max_distance: float | None = None
    search_confidence_high: float = 0.02
    search_confidence_medium: float = 0.01
    search_max_highlights_per_doc: int = 3

    # RAG context gate (F81.b / F81.c). Applied in
    # ``RagService._build_context`` after ``vector_store.query``.
    #
    # Distance cutoff: ``None`` → ask the embedder via
    # ``EmbeddingProvider.recommended_distance_threshold`` (same path as
    # search). The RAG path shipped with no distance filter at all
    # before F81.b; closing that gap is the main value here. An explicit
    # float always wins over the embedder recommendation — tighten if
    # answers still drag in off-topic chunks.
    rag_context_max_distance: float | None = None
    # Soft cap on context tokens stuffed into the prompt. Estimated via a
    # 4-chars-per-token heuristic (Anthropic's published approximation) —
    # never a hard API-limit check. Default 4000 leaves ~2.5k headroom
    # on an 8k-ctx local model after system prompt + question +
    # response; trivial for Claude's 200k. A single chunk that exceeds
    # the whole budget is still included with a WARN log (preserves
    # answer capability over config-only failures).
    rag_context_token_budget: int = 4000

    # RAG answer confidence bands (F81.e). Top-chunk distance drives
    # the user-visible badge: ``high`` ≤ high_max, ``medium`` ≤
    # medium_max, else ``low``. Defaults calibrated against bge-small
    # (recommended cutoff 0.35); operators can tighten if the UI
    # shows too many "high" badges relative to perceived quality.
    # If ``rag_context_max_distance`` is tightened below
    # ``medium_max``, the "low" band becomes unreachable — that's the
    # correct behaviour, not a miscalibration.
    rag_confidence_high_max_distance: float = 0.20
    rag_confidence_medium_max_distance: float = 0.30

    # Weighted RRF (F85.c). Multiplies each source's rank contribution
    # before scores accumulate. Boosting lexical reflects the F87
    # filename-A / skills-B index weighting so filename-intent queries
    # don't get cancelled out by vector drift. Set all to 1.0 for the
    # classical equal-weight RRF.
    rrf_weight_lexical: float = 2.0
    rrf_weight_vector: float = 1.0
    rrf_weight_sql: float = 1.0

    # LLM
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("encryption_keys", mode="before")
    @classmethod
    def _split_keys(cls, v: object) -> object:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v


settings = Settings()  # fails fast on import if required vars are missing/invalid
