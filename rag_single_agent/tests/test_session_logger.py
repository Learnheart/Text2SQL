"""Tests for session logger — per-session file logging."""

import os
import re
from pathlib import Path

import pytest

from src.session_logger import SessionLogger, LOG_DIR


@pytest.fixture(autouse=True)
def cleanup_logs():
    """Remove test log files after each test."""
    created_files: list[Path] = []
    yield created_files
    for f in created_files:
        if f.exists():
            f.unlink()


class TestSessionLogger:
    def test_creates_log_file(self, cleanup_logs):
        log = SessionLogger(question="test question")
        cleanup_logs.append(log.log_file)

        assert log.log_file.exists()
        assert log.log_file.parent == LOG_DIR
        assert "session_" in log.log_file.name
        log.close()

    def test_session_id_is_12_hex_chars(self, cleanup_logs):
        log = SessionLogger()
        cleanup_logs.append(log.log_file)

        assert len(log.session_id) == 12
        assert re.match(r"^[0-9a-f]{12}$", log.session_id)
        log.close()

    def test_header_written(self, cleanup_logs):
        log = SessionLogger(question="What is revenue?")
        cleanup_logs.append(log.log_file)
        log.close()

        content = log.log_file.read_text(encoding="utf-8")
        assert "SESSION:" in content
        assert log.session_id in content
        assert "What is revenue?" in content

    def test_step_logging(self, cleanup_logs):
        log = SessionLogger(question="test")
        cleanup_logs.append(log.log_file)

        log.step(1, "RAG_RETRIEVAL", "Starting retrieval")
        log.close()

        content = log.log_file.read_text(encoding="utf-8")
        assert "[STEP 1/5]" in content
        assert "[RAG_RETRIEVAL]" in content
        assert "Starting retrieval" in content

    def test_detail_logging_with_elapsed(self, cleanup_logs):
        log = SessionLogger(question="test")
        cleanup_logs.append(log.log_file)

        log.step(1, "RAG", "start")
        log.detail("RAG", "Schema chunks: 5")
        log.close()

        content = log.log_file.read_text(encoding="utf-8")
        # detail should contain elapsed time in ms
        assert re.search(r"Schema chunks: 5 \(\d+ms\)", content)

    def test_error_logging(self, cleanup_logs):
        log = SessionLogger(question="test")
        cleanup_logs.append(log.log_file)

        log.error("LLM_CALL", "API timeout")
        log.close()

        content = log.log_file.read_text(encoding="utf-8")
        assert "[ERROR]" in content
        assert "API timeout" in content

    def test_complete_logging(self, cleanup_logs):
        log = SessionLogger(question="test")
        cleanup_logs.append(log.log_file)

        log.complete("status=success, tokens=500")
        log.close()

        content = log.log_file.read_text(encoding="utf-8")
        assert "[COMPLETE]" in content
        assert "status=success" in content
        assert re.search(r"total: \d+ms", content)

    def test_full_session_flow(self, cleanup_logs):
        """Test a full session logging flow matching the agent pipeline."""
        log = SessionLogger(question="Doanh thu thang 3?")
        cleanup_logs.append(log.log_file)

        log.step(1, "RAG_RETRIEVAL", "Retrieving context")
        log.detail("RAG_RETRIEVAL", "Schema chunks: 5, Examples: 3, Metrics: 1")
        log.step(2, "PROMPT_BUILD", "Building system prompt")
        log.detail("PROMPT_BUILD", "System prompt length: 2000 chars")
        log.step(3, "LLM_LOOP", "Starting Claude tool use loop")
        log.detail("LLM_CALL", "Iteration 1: stop_reason=tool_use, tokens=500")
        log.detail("TOOL_DISPATCH", "execute_sql → 42 rows")
        log.detail("LLM_CALL", "Iteration 2: stop_reason=end_turn, tokens=200")
        log.step(4, "RESPONSE", "status=success, sql=yes")
        log.complete("status=success, tokens=700, tool_calls=1, iterations=2")
        log.close()

        content = log.log_file.read_text(encoding="utf-8")
        assert "[STEP 1/5]" in content
        assert "[STEP 2/5]" in content
        assert "[STEP 3/5]" in content
        assert "[STEP 4/5]" in content
        assert "[STEP 5/5]" in content
        assert "[COMPLETE]" in content
        assert "Doanh thu thang 3?" in content

    def test_info_logging(self, cleanup_logs):
        log = SessionLogger(question="test")
        cleanup_logs.append(log.log_file)

        log.info("REQUEST", "Received query")
        log.close()

        content = log.log_file.read_text(encoding="utf-8")
        assert "[REQUEST]" in content
        assert "Received query" in content

    def test_multiple_sessions_create_separate_files(self, cleanup_logs):
        log1 = SessionLogger(question="question 1")
        log2 = SessionLogger(question="question 2")
        cleanup_logs.extend([log1.log_file, log2.log_file])

        assert log1.log_file != log2.log_file
        assert log1.session_id != log2.session_id

        log1.close()
        log2.close()

    def test_close_is_idempotent(self, cleanup_logs):
        log = SessionLogger(question="test")
        cleanup_logs.append(log.log_file)

        log.close()
        log.close()  # should not raise
