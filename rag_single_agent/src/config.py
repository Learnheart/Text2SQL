from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


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

    # LLM Provider
    llm_provider: str = "anthropic"      # "anthropic" or "openai" (for Groq/Ollama/vLLM/OpenAI)
    llm_api_key: str = ""                # API key for the provider
    llm_base_url: str = ""               # Base URL override (e.g., Groq, Ollama, vLLM)
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.0

    # Backward compat: ANTHROPIC_API_KEY still works
    anthropic_api_key: str = ""

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
    def resolved_api_key(self) -> str:
        """Return llm_api_key, falling back to anthropic_api_key for backward compat."""
        return self.llm_api_key or self.anthropic_api_key

    @property
    def resolved_base_url(self) -> str | None:
        """Return base_url if set, else None."""
        return self.llm_base_url or None

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def asyncpg_dsn(self) -> str:
        return self.database_url

    model_config = {"env_file_encoding": "utf-8"}


settings = Settings()
