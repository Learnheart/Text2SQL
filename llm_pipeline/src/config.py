from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # Database (managed by service-controller, project: text2sql)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "text2sql_db"
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_min_pool: int = 2
    db_max_pool: int = 10
    db_statement_timeout_ms: int = 30_000

    # LLM Provider
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_fallback_model: str = "claude-opus-4-6"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.0

    # Backward compat
    anthropic_api_key: str = ""

    # Embedding (bge-m3 for multilingual)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024

    # Pipeline
    pipeline_max_retries: int = 3
    pipeline_timeout_seconds: int = 60

    # RAG / Schema Linker
    schema_top_k: int = 5
    example_top_k: int = 3

    # Redis Cache (managed by service-controller, db: 1)
    redis_url: str = "redis://localhost:6379/1"
    cache_query_ttl: int = 300       # 5 minutes
    cache_session_ttl: int = 1800    # 30 minutes
    cache_embedding_ttl: int = 3600  # 1 hour

    # Langfuse Monitoring
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def resolved_api_key(self) -> str:
        return self.llm_api_key or self.anthropic_api_key

    @property
    def resolved_base_url(self) -> str | None:
        return self.llm_base_url or None

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def asyncpg_dsn(self) -> str:
        return self.database_url

    model_config = {"env_file_encoding": "utf-8"}


settings = Settings()
