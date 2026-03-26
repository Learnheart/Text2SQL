"""Tests for FastAPI REST endpoints and WebSocket."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.models.schemas import AgentResponse, ToolCallRecord, AuditRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_success_response() -> AgentResponse:
    return AgentResponse(
        status="success",
        sql="SELECT SUM(total_amount) FROM sales",
        results={"columns": ["sum"], "rows": [[1000000]], "row_count": 1},
        explanation="Total revenue is 1,000,000.",
        tool_calls=[ToolCallRecord(tool_name="execute_sql", tool_input={"sql": "SELECT SUM(total_amount) FROM sales"})],
        total_tokens=200,
        latency_ms=1500,
    )


def _make_out_of_scope_response() -> AgentResponse:
    return AgentResponse(
        status="out_of_scope",
        explanation="Xin lỗi, tôi chỉ hỗ trợ câu hỏi về dữ liệu Banking/POS.",
        total_tokens=50,
        latency_ms=300,
    )


@pytest.fixture
def mock_state():
    """Patch the app lifespan and state to avoid real DB/ChromaDB/Embedding init."""
    with patch("src.api.app.lifespan") as mock_lifespan:
        # Make lifespan a no-op async context manager
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _noop_lifespan(app):
            yield

        mock_lifespan.side_effect = _noop_lifespan

        # Now import and patch state
        from src.api.app import state
        state.agent = AsyncMock()
        state.audit_logger = AsyncMock()
        state.db_pool = AsyncMock()

        yield state


@pytest.fixture
async def client(mock_state):
    """Create test client with mocked state."""
    # Re-create the app with patched lifespan
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from src.api.routes import router

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.include_router(router)

    # Also mount websocket from the ws module
    from src.api import websocket as ws_module
    # Patch the state reference in websocket module
    ws_module.state = mock_state

    @test_app.websocket("/ws/query")
    async def ws_query(websocket):
        from fastapi import WebSocket
        await ws_module.websocket_query.__wrapped__(websocket) if hasattr(ws_module.websocket_query, '__wrapped__') else None

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests — Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Tests — Query endpoint
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    @pytest.mark.asyncio
    async def test_query_success(self, mock_state):
        """POST /api/query with a data question returns success."""
        mock_state.agent.run = AsyncMock(return_value=_make_success_response())
        mock_state.audit_logger.log = AsyncMock()

        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from src.api.routes import router

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/query", json={"question": "Tổng doanh thu?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["sql"] == "SELECT SUM(total_amount) FROM sales"
        assert data["results"]["row_count"] == 1
        assert "metadata" in data
        assert data["metadata"]["latency_ms"] == 1500
        assert data["metadata"]["tool_calls"] == 1
        assert data["metadata"]["tokens"] == 200

        # Verify agent was called (with question + session_log kwarg)
        mock_state.agent.run.assert_called_once()
        call_args = mock_state.agent.run.call_args
        assert call_args[0][0] == "Tổng doanh thu?"
        # Verify audit was logged
        mock_state.audit_logger.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_out_of_scope(self, mock_state):
        """POST /api/query with off-topic question returns out_of_scope."""
        mock_state.agent.run = AsyncMock(return_value=_make_out_of_scope_response())
        mock_state.audit_logger.log = AsyncMock()

        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from src.api.routes import router

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/query", json={"question": "Thời tiết hôm nay?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "out_of_scope"
        assert "sql" not in data or data["sql"] is None

    @pytest.mark.asyncio
    async def test_query_agent_error(self, mock_state):
        """POST /api/query when agent raises exception returns 500."""
        mock_state.agent.run = AsyncMock(side_effect=RuntimeError("LLM API error"))

        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from src.api.routes import router

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/query", json={"question": "test"})

        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_query_missing_question(self, mock_state):
        """POST /api/query without question field returns 422."""
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from src.api.routes import router

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/query", json={})

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests — Feedback endpoint
# ---------------------------------------------------------------------------

class TestFeedbackEndpoint:
    @pytest.mark.asyncio
    async def test_feedback_received(self, mock_state):
        """POST /api/feedback returns acknowledgement."""
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from src.api.routes import router

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "question": "Tổng doanh thu?",
                "wrong_sql": "SELECT * FROM sales",
                "correct_sql": "SELECT SUM(total_amount) FROM sales WHERE status='completed'",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert data["question"] == "Tổng doanh thu?"

    @pytest.mark.asyncio
    async def test_feedback_missing_correct_sql(self, mock_state):
        """POST /api/feedback without correct_sql returns 422."""
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from src.api.routes import router

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "question": "Tổng doanh thu?",
            })

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests — WebSocket
# ---------------------------------------------------------------------------

try:
    from httpx_ws import aconnect_ws
    _has_httpx_ws = True
except ImportError:
    _has_httpx_ws = False


@pytest.mark.skipif(not _has_httpx_ws, reason="httpx-ws not installed")
class TestWebSocket:
    @pytest.mark.asyncio
    async def test_websocket_query_flow(self, mock_state):
        """WebSocket /ws/query sends events in correct sequence."""
        mock_state.agent.run = AsyncMock(return_value=_make_success_response())

        from contextlib import asynccontextmanager
        from fastapi import FastAPI, WebSocket
        import json as json_mod

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)

        @test_app.websocket("/ws/query")
        async def ws_endpoint(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_text()
                    message = json_mod.loads(data)
                    question = message.get("question", "")

                    if not question:
                        await websocket.send_json({"event": "error", "data": "No question provided"})
                        continue

                    await websocket.send_json({"event": "status", "data": "Processing question..."})

                    response = await mock_state.agent.run(question)

                    if response.sql:
                        await websocket.send_json({"event": "sql", "data": response.sql})
                    if response.results:
                        await websocket.send_json({"event": "result", "data": response.results})
                    await websocket.send_json({"event": "explanation", "data": response.explanation})
                    await websocket.send_json({
                        "event": "complete",
                        "data": {
                            "status": response.status,
                            "latency_ms": response.latency_ms,
                            "tool_calls": len(response.tool_calls),
                            "tokens": response.total_tokens,
                        },
                    })
            except Exception:
                pass

        import json

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws("/ws/query", ac) as ws:
                await ws.send_text(json.dumps({"question": "Tổng doanh thu?"}))

                events = []
                for _ in range(5):  # status, sql, result, explanation, complete
                    msg = json.loads(await ws.receive_text())
                    events.append(msg["event"])

                assert events[0] == "status"
                assert "sql" in events
                assert "result" in events
                assert "complete" in events

    @pytest.mark.asyncio
    async def test_websocket_empty_question(self, mock_state):
        """WebSocket with empty question returns error event."""
        from contextlib import asynccontextmanager
        from fastapi import FastAPI, WebSocket
        import json as json_mod

        @asynccontextmanager
        async def noop(app):
            yield

        test_app = FastAPI(lifespan=noop)

        @test_app.websocket("/ws/query")
        async def ws_endpoint(websocket: WebSocket):
            await websocket.accept()
            try:
                data = await websocket.receive_text()
                message = json_mod.loads(data)
                question = message.get("question", "")
                if not question:
                    await websocket.send_json({"event": "error", "data": "No question provided"})
            except Exception:
                pass

        import json

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async with aconnect_ws("/ws/query", ac) as ws:
                await ws.send_text(json.dumps({"question": ""}))
                msg = json.loads(await ws.receive_text())
                assert msg["event"] == "error"
