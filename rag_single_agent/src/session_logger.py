"""Session-based logger — mỗi request tạo 1 file log riêng để tracing qua các step."""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path("logs")

# Pattern to extract timestamp from log filename: session_{id}_{YYYYMMDD_HHMMSS}.log
_LOG_FILENAME_RE = re.compile(r"^session_[0-9a-f]+_(\d{8}_\d{6})\.log$")


def cleanup_old_logs(retention_hours: int = 24) -> int:
    """Delete session log files older than *retention_hours*. Returns count of deleted files."""
    if not LOG_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(hours=retention_hours)
    deleted = 0

    for path in LOG_DIR.glob("session_*.log"):
        match = _LOG_FILENAME_RE.match(path.name)
        if not match:
            continue
        try:
            file_time = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if file_time < cutoff:
            path.unlink(missing_ok=True)
            deleted += 1

    return deleted


class SessionLogger:
    """Logger gắn với 1 session (1 request). Ghi log ra file riêng trong logs/."""

    def __init__(self, question: str | None = None) -> None:
        self.session_id = uuid.uuid4().hex[:12]
        self.created_at = datetime.now()
        self._start = time.perf_counter()
        self._step_start: float | None = None
        self._current_step = 0
        self._total_steps = 6
        self._question = question or ""

        # Ensure log directory exists
        LOG_DIR.mkdir(exist_ok=True)

        # Create file handler for this session
        timestamp = self.created_at.strftime("%Y%m%d_%H%M%S")
        self._log_file = LOG_DIR / f"session_{self.session_id}_{timestamp}.log"

        self._logger = logging.getLogger(f"session.{self.session_id}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        # Avoid duplicate handlers if logger name reused
        self._logger.handlers.clear()

        handler = logging.FileHandler(self._log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)

        # Write session header
        self._logger.info("=" * 80)
        self._logger.info(f"SESSION: {self.session_id}")
        self._logger.info(f"TIME:    {self.created_at.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        self._logger.info(f"QUESTION: {self._question}")
        self._logger.info("=" * 80)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _elapsed_since_start(self) -> int:
        """Milliseconds since session start."""
        return int((time.perf_counter() - self._start) * 1000)

    def _elapsed_since_step(self) -> int:
        """Milliseconds since current step started."""
        if self._step_start is None:
            return 0
        return int((time.perf_counter() - self._step_start) * 1000)

    def step(self, step_num: int, label: str, message: str) -> None:
        """Log a step event."""
        self._current_step = step_num
        self._step_start = time.perf_counter()
        self._logger.info(
            f"[{self._timestamp()}] [STEP {step_num}/{self._total_steps}] [{label}] {message}"
        )

    def detail(self, label: str, message: str) -> None:
        """Log a detail within the current step (with elapsed time)."""
        elapsed = self._elapsed_since_step()
        self._logger.info(
            f"[{self._timestamp()}] [STEP {self._current_step}/{self._total_steps}] "
            f"[{label}] {message} ({elapsed}ms)"
        )

    def info(self, label: str, message: str) -> None:
        """Log general info without step context."""
        self._logger.info(f"[{self._timestamp()}] [{label}] {message}")

    def error(self, label: str, message: str) -> None:
        """Log an error."""
        self._logger.error(f"[{self._timestamp()}] [ERROR] [{label}] {message}")

    def complete(self, summary: str) -> None:
        """Log session completion with total elapsed time."""
        total_ms = self._elapsed_since_start()
        self._logger.info(
            f"[{self._timestamp()}] [STEP {self._total_steps}/{self._total_steps}] "
            f"[COMPLETE] {summary} (total: {total_ms}ms)"
        )
        self._logger.info("=" * 80)

    def close(self) -> None:
        """Flush and close handlers."""
        for handler in self._logger.handlers[:]:
            handler.flush()
            handler.close()
            self._logger.removeHandler(handler)

    @property
    def log_file(self) -> Path:
        return self._log_file
