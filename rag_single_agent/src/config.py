from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "test_db"
    db_user: str = "test_db_user"
    db_password: str = "test_db_password"
    db_min_pool: int = 2
    db_max_pool: int = 5
    db_statement_timeout_ms: int = 30_000

    # Claude API
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6-20250514"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.0

    # Embedding
    embedding_model: str = "BAAI/bge-large-en-v1.5"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"

    # Agent
    agent_max_tool_calls: int = 10
    agent_timeout_seconds: int = 60

    # RAG
    rag_schema_top_k: int = 5
    rag_example_top_k: int = 3

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def asyncpg_dsn(self) -> str:
        return self.database_url

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
