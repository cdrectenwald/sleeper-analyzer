"""
Observability infrastructure: correlation IDs, metrics, and request context.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Generator

log = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """Context object for a single request with correlation ID and timing."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    start_time: float = field(default_factory=time.perf_counter)
    metadata: dict[str, Any] = field(default_factory=dict)
    _logger: logging.Logger | None = field(default=None, repr=False)
    
    @property
    def log(self) -> logging.Logger:
        """Get a logger that includes the request_id in all messages."""
        if self._logger is None:
            self._logger = logging.LoggerAdapter(
                logging.getLogger("request"),
                {"request_id": self.request_id},
            )
        return self._logger
    
    @property
    def elapsed_ms(self) -> float:
        """Milliseconds since request started."""
        return (time.perf_counter() - self.start_time) * 1000
    
    def set(self, key: str, value: Any) -> None:
        """Add metadata to the request context."""
        self.metadata[key] = value


# Thread-local-ish storage for current request context
_current_context: RequestContext | None = None


@contextmanager
def get_request_context(**initial_metadata: Any) -> Generator[RequestContext, None, None]:
    """Create a new request context for tracing."""
    global _current_context
    
    ctx = RequestContext(metadata=initial_metadata)
    old_context = _current_context
    _current_context = ctx
    
    try:
        yield ctx
    finally:
        _current_context = old_context


def current_context() -> RequestContext | None:
    """Get the current request context, if any."""
    return _current_context


class Metrics:
    """In-memory metrics collector for latencies, errors, and tool usage."""
    
    def __init__(self) -> None:
        self._lock = Lock()
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._errors: dict[str, int] = defaultdict(int)
        self._tool_calls: dict[str, int] = defaultdict(int)
        self._requests: dict[str, int] = defaultdict(int)
    
    def record_latency(self, operation: str, latency_ms: float) -> None:
        """Record a latency measurement for an operation."""
        with self._lock:
            self._latencies[operation].append(latency_ms)
            # Keep only last 1000 measurements per operation
            if len(self._latencies[operation]) > 1000:
                self._latencies[operation] = self._latencies[operation][-1000:]
    
    def record_error(self, error_type: str) -> None:
        """Increment error counter for a specific error type."""
        with self._lock:
            self._errors[error_type] += 1
    
    def record_tool_call(self, tool_name: str) -> None:
        """Increment tool usage counter."""
        with self._lock:
            self._tool_calls[tool_name] += 1
    
    def record_request(self, endpoint: str) -> None:
        """Increment request counter for an endpoint."""
        with self._lock:
            self._requests[endpoint] += 1
    
    def get_stats(self) -> dict[str, Any]:
        """Get current metrics snapshot."""
        with self._lock:
            latency_stats = {}
            for op, values in self._latencies.items():
                if values:
                    sorted_vals = sorted(values)
                    n = len(sorted_vals)
                    latency_stats[op] = {
                        "count": n,
                        "avg_ms": round(sum(sorted_vals) / n, 2),
                        "p50_ms": round(sorted_vals[int(n * 0.5)], 2),
                        "p95_ms": round(sorted_vals[int(n * 0.95)], 2),
                        "p99_ms": round(sorted_vals[int(n * 0.99)], 2),
                    }
            
            return {
                "latencies": latency_stats,
                "errors": dict(self._errors),
                "tool_calls": dict(self._tool_calls),
                "requests": dict(self._requests),
            }
    
    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._latencies.clear()
            self._errors.clear()
            self._tool_calls.clear()
            self._requests.clear()


# Global metrics instance
metrics = Metrics()


@contextmanager
def timed_operation(operation: str) -> Generator[None, None, None]:
    """Context manager to time an operation and record metrics."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        metrics.record_latency(operation, elapsed_ms)
