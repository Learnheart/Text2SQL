"""WebSocket endpoint for streaming pipeline results.

Events:
- router: Router intent classification result
- schema_linker: Context assembly status
- sql_token: SQL generation tokens (streamed)
- sql_complete: Full SQL generated
- executing: SQL execution started
- result: Query results
- complete: Pipeline finished
- error: Error occurred
- retry: Self-correction retry
"""

from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from src.api.app import get_app_state

logger = logging.getLogger(__name__)


async def websocket_query(websocket: WebSocket) -> None:
    """Handle WebSocket connection for streaming query results."""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            question = message.get("question", "")

            if not question:
                await _send_event(websocket, "error", {"message": "No question provided"})
                continue

            state = get_app_state()

            # Send status updates as the pipeline progresses
            await _send_event(websocket, "router", {"status": "classifying"})

            response = await state.pipeline.run(question=question)

            # Send results
            if response.sql:
                await _send_event(websocket, "sql_complete", {"sql": response.sql})

            if response.results:
                await _send_event(websocket, "result", {
                    "columns": response.results.columns,
                    "rows": response.results.rows,
                    "row_count": response.results.row_count,
                })

            await _send_event(websocket, "complete", {
                "status": response.status.value,
                "explanation": response.explanation,
                "latency_ms": response.latency_ms,
                "attempts": response.attempts,
            })

    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await _send_event(websocket, "error", {"message": str(e)})
        except Exception:
            pass


async def _send_event(websocket: WebSocket, event: str, data: dict) -> None:
    await websocket.send_text(json.dumps({"event": event, "data": data}))
