"""Tests for API routes — unit tests with mocked pipeline."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_health_returns_starting_when_not_initialized(self):
        """Health check should return 'starting' before app is initialized."""
        from src.api.app import create_app

        # Create app without lifespan initialization
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        # Override to avoid actual initialization
        with patch("src.api.app.get_app_state", side_effect=RuntimeError("not ready")):
            with patch("src.api.routes.get_app_state", side_effect=RuntimeError("not ready")):
                response = client.get("/api/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "starting"


class TestQueryEndpoint:
    def test_query_requires_question(self):
        """POST /api/query should require a question field."""
        from src.api.app import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/api/query", json={})
        assert response.status_code == 422  # Validation error


class TestFeedbackEndpoint:
    def test_feedback_accepted(self):
        """POST /api/feedback should accept valid feedback."""
        from src.api.app import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        # Mock app state
        mock_state = MagicMock()
        with patch("src.api.routes.get_app_state", return_value=mock_state):
            response = client.post("/api/feedback", json={
                "question": "Tổng doanh thu?",
                "correct_sql": "SELECT SUM(total_amount) FROM sales",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "received"
