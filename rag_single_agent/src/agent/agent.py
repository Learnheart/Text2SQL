"""Single LLM Agent — provider-agnostic tool use loop."""

from __future__ import annotations

import json
import time
from typing import Any

from src.config import settings
from src.models.schemas import AgentResponse, ToolCallRecord, RAGContext
from src.agent.prompt_builder import PromptBuilder
from src.rag.retrieval import RAGRetrieval
from src.data_access.connection import DatabasePool
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.vector_store import VectorStore
from src.rag.embedding import EmbeddingService
from src.llm.base import LLMProvider, LLMResponse
from src.session_logger import SessionLogger
from src.tools.execute_sql import execute_sql, TOOL_DEFINITION as EXEC_SQL_DEF
from src.tools.search_schema import search_schema, TOOL_DEFINITION as SEARCH_SCHEMA_DEF
from src.tools.get_metric import get_metric_definition, TOOL_DEFINITION as GET_METRIC_DEF
from src.tools.get_column_values import get_column_values, TOOL_DEFINITION as GET_COL_DEF

ALL_TOOLS = [EXEC_SQL_DEF, SEARCH_SCHEMA_DEF, GET_METRIC_DEF, GET_COL_DEF]


class Agent:
    """RAG-Enhanced Single Agent using any LLM provider with tool use."""

    def __init__(
        self,
        db_pool: DatabasePool,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        semantic_layer: SemanticLayer,
        rag_retrieval: RAGRetrieval,
        prompt_builder: PromptBuilder,
        llm_provider: LLMProvider,
    ) -> None:
        self._pool = db_pool
        self._embedder = embedding_service
        self._vector_store = vector_store
        self._semantic_layer = semantic_layer
        self._rag = rag_retrieval
        self._prompt_builder = prompt_builder
        self._llm = llm_provider

    async def run(self, question: str, session_log: SessionLogger | None = None) -> AgentResponse:
        """Run the agent: RAG → build prompt → LLM tool use loop → response."""
        start = time.perf_counter()
        tool_call_records: list[ToolCallRecord] = []
        total_tokens = 0
        log = session_log or SessionLogger(question)

        # --- Step 1: RAG retrieval ---
        log.step(1, "RAG_RETRIEVAL", f"Retrieving context for: {question[:100]}")
        rag_context: RAGContext = self._rag.retrieve(question, session_log=log)
        log.detail(
            "RAG_RETRIEVAL",
            f"Schema chunks: {len(rag_context.schema_chunks)}, "
            f"Examples: {len(rag_context.examples)}, "
            f"Metrics: {len(rag_context.metrics)}",
        )

        # --- Log retrieval output detail ---
        for i, chunk in enumerate(rag_context.schema_chunks, 1):
            log.detail("RETRIEVAL_SCHEMA", f"Chunk {i}/{len(rag_context.schema_chunks)}:\n{chunk}")
        for i, ex in enumerate(rag_context.examples, 1):
            log.detail(
                "RETRIEVAL_EXAMPLE",
                f"Example {i}/{len(rag_context.examples)}: "
                f"Q: {ex.question} | SQL: {ex.sql}",
            )
        for m in rag_context.metrics:
            log.detail(
                "RETRIEVAL_METRIC",
                f"Metric: {m.name} | SQL: {m.sql} | Filter: {m.filter} | Aliases: {m.aliases}",
            )

        # --- Step 2: Build system prompt ---
        log.step(2, "PROMPT_BUILD", "Building system prompt with RAG context")
        system_prompt = self._prompt_builder.build(rag_context)
        log.detail("PROMPT_BUILD", f"System prompt length: {len(system_prompt)} chars")
        log.detail("PROMPT_BUILD", f"System prompt detail: {system_prompt}")

        # --- Step 3: LLM tool use loop ---
        log.step(3, "LLM_LOOP", f"Starting tool use loop (provider={settings.llm_provider}, model={settings.llm_model})")
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        iteration = 0
        seen_tool_calls: set[str] = set()  # dedup guard: "tool_name:input_json"

        for _ in range(settings.agent_max_tool_calls):
            iteration += 1
            llm_start = time.perf_counter()

            llm_response: LLMResponse = self._llm.create(
                system=system_prompt,
                messages=messages,
                tools=ALL_TOOLS,
                model=settings.llm_model,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )

            llm_ms = int((time.perf_counter() - llm_start) * 1000)
            total_tokens += llm_response.total_tokens

            log.detail(
                "LLM_CALL",
                f"Iteration {iteration}: stop_reason={llm_response.stop_reason}, "
                f"tokens={llm_response.total_tokens} ({llm_ms}ms)",
            )

            # --- Log LLM reasoning output ---
            if llm_response.text:
                log.detail("REASONING", f"Iteration {iteration} LLM text:\n{llm_response.text}")

            # --- Log tool choosing ---
            if llm_response.has_tool_calls:
                tool_names = [tc.name for tc in llm_response.tool_calls]
                log.detail(
                    "TOOL_CHOOSING",
                    f"Iteration {iteration}: LLM chose {len(tool_names)} tool(s): {tool_names}",
                )
                for tc in llm_response.tool_calls:
                    log.detail(
                        "TOOL_CHOOSING",
                        f"  → {tc.name}: {json.dumps(tc.input, ensure_ascii=False)}",
                    )

            # Check if agent wants to call tools
            if llm_response.has_tool_calls:
                # Dedup guard: detect repeated identical tool calls
                dedup_keys = [
                    f"{tc.name}:{json.dumps(tc.input, sort_keys=True)}"
                    for tc in llm_response.tool_calls
                ]
                if all(k in seen_tool_calls for k in dedup_keys):
                    log.detail(
                        "DEDUP_BREAK",
                        f"Duplicate tool calls detected at iteration {iteration}, "
                        f"breaking loop: {[tc.name for tc in llm_response.tool_calls]}",
                    )
                    # Return response from results already collected (not an error)
                    elapsed = int((time.perf_counter() - start) * 1000)
                    agent_response = self._build_response(
                        llm_response, tool_call_records, total_tokens, elapsed
                    )
                    log.step(4, "RESPONSE", f"status={agent_response.status} (dedup early stop)")
                    log.complete(
                        f"status={agent_response.status}, tokens={total_tokens}, "
                        f"tool_calls={len(tool_call_records)}, iterations={iteration}"
                    )
                    if not session_log:
                        log.close()
                    return agent_response

                # Append assistant response (provider-specific format)
                messages.append(
                    self._llm.format_assistant_message(self._llm.last_raw_response)
                )

                # Process tool calls
                tool_results: list[dict] = []
                for tc in llm_response.tool_calls:
                    call_key = f"{tc.name}:{json.dumps(tc.input, sort_keys=True)}"
                    seen_tool_calls.add(call_key)

                    tool_input_summary = str(tc.input)[:200]
                    log.detail("TOOL_DISPATCH", f"{tc.name} → input: {tool_input_summary}")

                    tool_start = time.perf_counter()
                    result = await self._dispatch_tool(tc.name, tc.input)
                    tool_ms = int((time.perf_counter() - tool_start) * 1000)

                    tool_call_records.append(
                        ToolCallRecord(
                            tool_name=tc.name,
                            tool_input=tc.input,
                            tool_output=result,
                        )
                    )

                    result_summary = self._summarize_tool_result(tc.name, result)
                    log.detail("TOOL_RESULT", f"{tc.name} → {result_summary} ({tool_ms}ms)")

                    # --- Log full tool execution output ---
                    log.detail(
                        "TOOL_EXECUTING",
                        f"{tc.name} full output:\n{json.dumps(result, ensure_ascii=False, default=str)}"
                    )

                    tool_results.append(
                        self._llm.format_tool_result(
                            tool_call_id=tc.id,
                            content=str(result),
                        )
                    )

                messages.extend(self._llm.format_tool_results_message(tool_results))
            else:
                # Agent is done — extract final response
                elapsed = int((time.perf_counter() - start) * 1000)
                agent_response = self._build_response(
                    llm_response, tool_call_records, total_tokens, elapsed
                )

                # --- Step 4: Agent Explain ---
                log.step(4, "AGENT_EXPLAIN", f"status={agent_response.status}, sql={'yes' if agent_response.sql else 'no'}")
                if agent_response.explanation:
                    log.detail("AGENT_EXPLAIN", f"Explanation:\n{agent_response.explanation}")
                if agent_response.results:
                    log.detail("AGENT_EXPLAIN", f"rows={agent_response.results.get('row_count', 0)}")

                # --- Step 5: Final Output ---
                log.step(5, "FINAL_OUTPUT", "Building final output summary")
                log.detail("FINAL_OUTPUT", f"Status: {agent_response.status}")
                if agent_response.sql:
                    log.detail("FINAL_OUTPUT", f"SQL:\n{agent_response.sql}")
                if agent_response.results:
                    log.detail(
                        "FINAL_OUTPUT",
                        f"Results: {agent_response.results.get('row_count', 0)} rows, "
                        f"columns={agent_response.results.get('columns', [])}",
                    )
                log.detail(
                    "FINAL_OUTPUT",
                    f"Tokens: {total_tokens}, Latency: {elapsed}ms, "
                    f"Tool calls: {len(tool_call_records)}, Iterations: {iteration}",
                )

                # --- Step 6: Complete ---
                log.complete(
                    f"status={agent_response.status}, tokens={total_tokens}, "
                    f"tool_calls={len(tool_call_records)}, iterations={iteration}"
                )
                if not session_log:
                    log.close()
                return agent_response

        # Max tool calls reached
        elapsed = int((time.perf_counter() - start) * 1000)
        log.error("LLM_LOOP", f"Max tool calls ({settings.agent_max_tool_calls}) reached after {iteration} iterations")
        log.complete(f"status=error, tokens={total_tokens}, tool_calls={len(tool_call_records)}")
        if not session_log:
            log.close()
        return AgentResponse(
            status="error",
            explanation="Maximum tool calls reached. Please try a simpler question.",
            tool_calls=tool_call_records,
            total_tokens=total_tokens,
            latency_ms=elapsed,
        )

    async def _dispatch_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Route a tool call to the appropriate handler."""
        if tool_name == "execute_sql":
            return await execute_sql(tool_input["sql"], self._pool)
        elif tool_name == "search_schema":
            return await search_schema(
                tool_input["query"], self._embedder, self._vector_store
            )
        elif tool_name == "get_metric_definition":
            return await get_metric_definition(
                tool_input["metric_name"], self._semantic_layer
            )
        elif tool_name == "get_column_values":
            return await get_column_values(
                tool_input["table"],
                tool_input["column"],
                self._pool,
                self._semantic_layer,
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    @staticmethod
    def _summarize_tool_result(tool_name: str, result: Any) -> str:
        """Create a short summary of a tool result for logging."""
        if not isinstance(result, dict):
            return str(result)[:100]
        if "error" in result:
            return f"ERROR: {result['error'][:100]}"
        if tool_name == "execute_sql":
            return f"{result.get('row_count', 0)} rows, {result.get('execution_time_ms', 0)}ms"
        if tool_name == "search_schema":
            return f"{len(result.get('results', []))} chunks found"
        if tool_name == "get_metric_definition":
            return f"metric={result.get('name', '?')}"
        if tool_name == "get_column_values":
            return f"{result.get('count', 0)} distinct values"
        return str(result)[:100]

    @staticmethod
    def _build_response(
        llm_response: LLMResponse,
        tool_calls: list[ToolCallRecord],
        total_tokens: int,
        elapsed: int,
    ) -> AgentResponse:
        """Extract structured response from the LLM's final message."""
        full_text = llm_response.text or ""

        # Extract SQL from tool calls
        sql = None
        results = None
        for tc in tool_calls:
            if tc.tool_name == "execute_sql":
                sql = tc.tool_input.get("sql")
                if isinstance(tc.tool_output, dict) and "rows" in tc.tool_output:
                    results = tc.tool_output

        # Determine status
        status = "success" if results else "out_of_scope" if not sql else "error"

        return AgentResponse(
            status=status,
            sql=sql,
            results=results,
            explanation=full_text,
            tool_calls=tool_calls,
            total_tokens=total_tokens,
            latency_ms=elapsed,
        )
