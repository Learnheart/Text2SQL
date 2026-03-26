"""Langfuse integration for LLM tracing, cost tracking, and prompt versioning.

Wraps Langfuse SDK to trace:
- Each pipeline execution (trace)
- Individual LLM calls (generation spans)
- Pipeline step timings (spans)
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)


class LangfuseTracer:
    """Langfuse tracing wrapper. Gracefully degrades if Langfuse is not configured."""

    def __init__(self) -> None:
        self._langfuse: Any = None
        self._enabled = False

    def init(self) -> None:
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.info("Langfuse not configured — tracing disabled")
            return

        try:
            from langfuse import Langfuse
            self._langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            self._enabled = True
            logger.info("Langfuse tracing enabled: %s", settings.langfuse_host)
        except Exception as e:
            logger.warning("Langfuse init failed — tracing disabled: %s", e)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def trace(
        self,
        name: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Create a new trace for a pipeline execution."""
        if not self._enabled:
            return _NoOpTrace()

        try:
            return self._langfuse.trace(
                name=name,
                session_id=session_id,
                metadata=metadata or {},
            )
        except Exception:
            return _NoOpTrace()

    def generation(
        self,
        trace: Any,
        name: str,
        model: str,
        input_text: str,
        output_text: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log an LLM generation span within a trace."""
        if not self._enabled or isinstance(trace, _NoOpTrace):
            return

        try:
            trace.generation(
                name=name,
                model=model,
                input=input_text[:1000],  # Truncate for storage
                output=output_text[:2000],
                usage={
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": input_tokens + output_tokens,
                },
                metadata=metadata or {},
            )
        except Exception:
            pass

    def span(
        self,
        trace: Any,
        name: str,
        input_data: Any = None,
        output_data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a pipeline step span within a trace."""
        if not self._enabled or isinstance(trace, _NoOpTrace):
            return

        try:
            trace.span(
                name=name,
                input=input_data,
                output=output_data,
                metadata=metadata or {},
            )
        except Exception:
            pass

    def flush(self) -> None:
        if self._enabled and self._langfuse:
            try:
                self._langfuse.flush()
            except Exception:
                pass

    def shutdown(self) -> None:
        self.flush()
        if self._langfuse:
            try:
                self._langfuse.shutdown()
            except Exception:
                pass


class _NoOpTrace:
    """No-op trace when Langfuse is disabled."""

    def generation(self, **kwargs: Any) -> None:
        pass

    def span(self, **kwargs: Any) -> None:
        pass
