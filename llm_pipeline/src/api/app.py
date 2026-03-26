"""FastAPI application with lifespan management.

Initializes all dependencies on startup:
- Database pool
- Knowledge base (bootstrap)
- LLM provider
- Redis cache
- Langfuse tracer
- LangGraph pipeline
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

from fastapi import FastAPI

from src.cache.redis_cache import RedisCache
from src.config import settings
from src.data_access.audit import AuditLogger
from src.data_access.connection import DatabasePool
from src.knowledge.bootstrap import KnowledgeBase, bootstrap_knowledge
from src.knowledge.vector_store import PgVectorStore
from src.llm.factory import create_llm_provider
from src.monitoring.langfuse_tracer import LangfuseTracer
from src.pipeline.graph import PipelineGraph

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Holds all initialized application dependencies."""

    db_pool: DatabasePool
    knowledge: KnowledgeBase
    pipeline: PipelineGraph
    cache: RedisCache
    audit: AuditLogger
    tracer: LangfuseTracer


_app_state: AppState | None = None


def get_app_state() -> AppState:
    if _app_state is None:
        raise RuntimeError("Application not initialized")
    return _app_state


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize and cleanup application resources."""
    global _app_state
    logger.info("Starting LLM Pipeline application...")

    # 1. Database pool
    db_pool = DatabasePool()
    await db_pool.init()

    # 2. Vector store (pgvector)
    vector_store = PgVectorStore()
    await vector_store.init()

    # 3. Knowledge base bootstrap
    knowledge = await bootstrap_knowledge(vector_store=vector_store)

    # 4. LLM provider
    llm_provider = create_llm_provider(
        provider=settings.llm_provider,
        api_key=settings.resolved_api_key,
        base_url=settings.resolved_base_url,
    )

    # 5. Pipeline graph
    pipeline = PipelineGraph(db_pool, llm_provider, knowledge)

    # 6. Redis cache
    cache = RedisCache()
    await cache.init()

    # 7. Audit logger
    audit = AuditLogger()
    await audit.init()

    # 8. Langfuse tracer
    tracer = LangfuseTracer()
    tracer.init()

    _app_state = AppState(
        db_pool=db_pool,
        knowledge=knowledge,
        pipeline=pipeline,
        cache=cache,
        audit=audit,
        tracer=tracer,
    )

    logger.info("Application initialized successfully")

    yield

    # Cleanup
    logger.info("Shutting down application...")
    tracer.shutdown()
    await cache.close()
    await audit.close()
    await vector_store.close()
    await db_pool.close()
    logger.info("Application shut down")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Text-to-SQL Pipeline",
        description="LLM-in-the-middle Pipeline for Banking/POS (Phase 2)",
        version="0.2.0",
        lifespan=lifespan,
    )

    from src.api.routes import router
    app.include_router(router)

    return app


app = create_app()
