"""FastAPI application with lifespan for startup/shutdown."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.data_access.connection import DatabasePool
from src.data_access.audit import AuditLogger
from src.rag.embedding import EmbeddingService
from src.knowledge.vector_store import VectorStore
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.example_store import ExampleStore
from src.rag.retrieval import RAGRetrieval
from src.agent.prompt_builder import PromptBuilder
from src.agent.agent import Agent
from src.llm.factory import create_llm_provider


class AppState:
    """Holds shared resources initialized at startup."""

    db_pool: DatabasePool
    audit_logger: AuditLogger
    agent: Agent


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # Database
    state.db_pool = DatabasePool()
    await state.db_pool.init()

    state.audit_logger = AuditLogger()
    await state.audit_logger.init()

    # Knowledge layer
    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    semantic_layer = SemanticLayer()
    example_store = ExampleStore()

    # LLM provider
    llm_provider = create_llm_provider(
        provider=settings.llm_provider,
        api_key=settings.resolved_api_key,
        base_url=settings.resolved_base_url,
    )

    # RAG + Agent
    rag_retrieval = RAGRetrieval(embedding_service, vector_store, semantic_layer, example_store)
    prompt_builder = PromptBuilder(semantic_layer, example_store)

    state.agent = Agent(
        db_pool=state.db_pool,
        embedding_service=embedding_service,
        vector_store=vector_store,
        semantic_layer=semantic_layer,
        rag_retrieval=rag_retrieval,
        prompt_builder=prompt_builder,
        llm_provider=llm_provider,
    )

    yield

    # --- Shutdown ---
    await state.db_pool.close()
    await state.audit_logger.close()


app = FastAPI(
    title="Text-to-SQL Agent API",
    description="Banking/POS Text-to-SQL Agent — RAG-Enhanced Single Agent (Phase 1)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routes after app creation
from src.api.routes import router  # noqa: E402

app.include_router(router)
