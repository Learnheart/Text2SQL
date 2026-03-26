"""LangGraph Pipeline Orchestration — the central graph connecting all components.

Graph structure:
    START → router → [conditional: sql/reject]
                          │
                    schema_linker → sql_generator → validator → [conditional: valid/invalid]
                                        ↑                            │
                                        └── prepare_retry ←── [conditional: retry/max_retries]
                                                                     │
                                                               executor → [conditional: success/error]
                                                                     │         │
                                                                     │    prepare_retry → sql_generator
                                                                     ↓
                                                                  response → END

Uses LangGraph's StateGraph with TypedDict state and conditional edges.
"""

from __future__ import annotations

import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.config import settings
from src.data_access.connection import DatabasePool
from src.knowledge.bootstrap import KnowledgeBase
from src.llm.base import LLMProvider
from src.models.schemas import IntentType, PipelineResponse, PipelineStatus
from src.pipeline.state import PipelineState
from src.pipeline import router, schema_linker, sql_generator, validator, executor, self_correction
from src.session_logger import SessionLogger


class PipelineGraph:
    """Wraps the LangGraph graph with dependencies (DB pool, LLM provider, knowledge base).

    Usage:
        graph = PipelineGraph(db_pool, llm_provider, knowledge)
        response = await graph.run("Tổng doanh thu tháng 3?")
    """

    def __init__(
        self,
        db_pool: DatabasePool,
        llm_provider: LLMProvider,
        knowledge: KnowledgeBase,
    ) -> None:
        self._db_pool = db_pool
        self._llm_provider = llm_provider
        self._knowledge = knowledge
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Build the LangGraph StateGraph with all nodes and edges."""
        workflow = StateGraph(PipelineState)

        # --- Define nodes ---

        # Node: router
        def router_node(state: PipelineState) -> PipelineState:
            session_log = state.get("_session_log")
            return router.route(state, session_log=session_log)

        # Node: schema_linker (async)
        async def schema_linker_node(state: PipelineState) -> PipelineState:
            session_log = state.get("_session_log")
            return await schema_linker.link_schema(
                state, knowledge=self._knowledge, session_log=session_log
            )

        # Node: sql_generator
        def sql_generator_node(state: PipelineState) -> PipelineState:
            session_log = state.get("_session_log")
            return sql_generator.generate_sql(
                state, llm_provider=self._llm_provider, session_log=session_log
            )

        # Node: validator
        def validator_node(state: PipelineState) -> PipelineState:
            session_log = state.get("_session_log")
            return validator.validate(state, session_log=session_log)

        # Node: executor (async)
        async def executor_node(state: PipelineState) -> PipelineState:
            session_log = state.get("_session_log")
            return await executor.execute(
                state, db_pool=self._db_pool, session_log=session_log
            )

        # Node: prepare_retry
        def prepare_retry_node(state: PipelineState) -> PipelineState:
            session_log = state.get("_session_log")
            return self_correction.prepare_retry(state, session_log=session_log)

        # Node: max_retries_reached
        def max_retries_node(state: PipelineState) -> PipelineState:
            session_log = state.get("_session_log")
            return self_correction.finalize_max_retries(state, session_log=session_log)

        # Node: build_response (final)
        def build_response_node(state: PipelineState) -> PipelineState:
            return state  # response built in run()

        # --- Add nodes to graph ---
        workflow.add_node("router", router_node)
        workflow.add_node("schema_linker", schema_linker_node)
        workflow.add_node("sql_generator", sql_generator_node)
        workflow.add_node("validator", validator_node)
        workflow.add_node("executor", executor_node)
        workflow.add_node("prepare_retry", prepare_retry_node)
        workflow.add_node("max_retries", max_retries_node)
        workflow.add_node("build_response", build_response_node)

        # --- Define edges ---

        # START → router
        workflow.add_edge(START, "router")

        # router → conditional: if SQL → schema_linker, else → build_response (rejected)
        def route_after_router(state: PipelineState) -> str:
            router_result = state.get("router_result")
            if router_result and router_result.intent == IntentType.SQL:
                return "schema_linker"
            return "build_response"

        workflow.add_conditional_edges("router", route_after_router, {
            "schema_linker": "schema_linker",
            "build_response": "build_response",
        })

        # schema_linker → sql_generator
        workflow.add_edge("schema_linker", "sql_generator")

        # sql_generator → validator
        workflow.add_edge("sql_generator", "validator")

        # validator → conditional: if valid → executor, else → retry check
        def route_after_validator(state: PipelineState) -> str:
            validation = state.get("validation_result")
            if validation and validation.is_valid:
                return "executor"
            # Validation failed — check retry
            attempt = state.get("attempt", 1)
            if attempt < settings.pipeline_max_retries:
                return "prepare_retry"
            return "max_retries"

        workflow.add_conditional_edges("validator", route_after_validator, {
            "executor": "executor",
            "prepare_retry": "prepare_retry",
            "max_retries": "max_retries",
        })

        # executor → conditional: success → build_response, error → retry check
        def route_after_executor(state: PipelineState) -> str:
            execution_result = state.get("execution_result")
            if execution_result and not execution_result.error:
                return "build_response"
            # Execution failed — check retry
            attempt = state.get("attempt", 1)
            if attempt < settings.pipeline_max_retries:
                return "prepare_retry"
            return "max_retries"

        workflow.add_conditional_edges("executor", route_after_executor, {
            "build_response": "build_response",
            "prepare_retry": "prepare_retry",
            "max_retries": "max_retries",
        })

        # prepare_retry → sql_generator (loop back)
        workflow.add_edge("prepare_retry", "sql_generator")

        # max_retries → build_response
        workflow.add_edge("max_retries", "build_response")

        # build_response → END
        workflow.add_edge("build_response", END)

        return workflow.compile()

    async def run(self, question: str, session_id: str | None = None) -> PipelineResponse:
        """Execute the full pipeline for a question. Returns PipelineResponse."""
        start = time.perf_counter()
        session_log = SessionLogger(question=question, total_steps=7)

        initial_state: PipelineState = {
            "question": question,
            "session_id": session_id or session_log.session_id,
            "attempt": 1,
            "error_feedback": "",
            "error_history": [],
            "total_tokens": 0,
            "_session_log": session_log,
        }

        try:
            # Run the graph
            final_state = await self._graph.ainvoke(initial_state)

            latency_ms = int((time.perf_counter() - start) * 1000)

            response = self._build_response(final_state, latency_ms)

            session_log.complete(
                f"status={response.status.value}, "
                f"attempts={response.attempts}, "
                f"tokens={response.total_tokens}, "
                f"latency={latency_ms}ms"
            )

            return response
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            session_log.error("PIPELINE", f"Unhandled error: {e}")
            session_log.complete(f"status=error, latency={latency_ms}ms")
            return PipelineResponse(
                status=PipelineStatus.ERROR,
                explanation=f"Internal error: {str(e)}",
                latency_ms=latency_ms,
            )
        finally:
            session_log.close()

    @staticmethod
    def _build_response(state: PipelineState, latency_ms: int) -> PipelineResponse:
        """Build final PipelineResponse from graph state."""
        router_result = state.get("router_result")

        # Non-SQL intents
        if router_result and router_result.intent != IntentType.SQL:
            status_map = {
                IntentType.CHITCHAT: PipelineStatus.REJECTED,
                IntentType.CLARIFICATION: PipelineStatus.CLARIFICATION,
                IntentType.OUT_OF_SCOPE: PipelineStatus.REJECTED,
            }
            return PipelineResponse(
                status=status_map.get(router_result.intent, PipelineStatus.REJECTED),
                explanation=router_result.message,
                intent=router_result.intent,
                latency_ms=latency_ms,
            )

        # Max retries
        pipeline_status = state.get("status")
        if pipeline_status == PipelineStatus.MAX_RETRIES:
            return PipelineResponse(
                status=PipelineStatus.MAX_RETRIES,
                sql=state.get("generated_sql"),
                explanation=state.get("explanation", ""),
                intent=IntentType.SQL,
                attempts=state.get("attempt", 0),
                total_tokens=state.get("total_tokens", 0),
                latency_ms=latency_ms,
            )

        # Success
        execution_result = state.get("execution_result")
        return PipelineResponse(
            status=PipelineStatus.SUCCESS,
            sql=state.get("generated_sql"),
            results=execution_result,
            intent=IntentType.SQL,
            attempts=state.get("attempt", 1),
            total_tokens=state.get("total_tokens", 0),
            latency_ms=latency_ms,
        )
