"""WebSocket handler for streaming agent responses."""

from __future__ import annotations

import json

from fastapi import WebSocket, WebSocketDisconnect

from src.api.app import app, state


@app.websocket("/ws/query")
async def websocket_query(websocket: WebSocket):
    """WebSocket endpoint for streaming query responses."""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            question = message.get("question", "")

            if not question:
                await websocket.send_json({"event": "error", "data": "No question provided"})
                continue

            # Send status: processing
            await websocket.send_json({"event": "status", "data": "Processing question..."})

            try:
                response = await state.agent.run(question)

                # Send SQL if generated
                if response.sql:
                    await websocket.send_json({"event": "sql", "data": response.sql})

                # Send results
                if response.results:
                    await websocket.send_json({"event": "result", "data": response.results})

                # Send explanation
                await websocket.send_json({"event": "explanation", "data": response.explanation})

                # Send complete
                await websocket.send_json({
                    "event": "complete",
                    "data": {
                        "status": response.status,
                        "latency_ms": response.latency_ms,
                        "tool_calls": len(response.tool_calls),
                        "tokens": response.total_tokens,
                    },
                })
            except Exception as e:
                await websocket.send_json({"event": "error", "data": str(e)})

    except WebSocketDisconnect:
        pass
