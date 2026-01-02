"""
Metrics endpoint for observability.

Provides internal metrics for monitoring and debugging.
In production, you might expose this on a separate port or behind auth.

Endpoints:
    GET /metrics - Get all metrics
    GET /metrics/circuits - Get circuit breaker states
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.common.observability import metrics
from src.common.resilience import get_all_circuit_states

log = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "",
    summary="Get application metrics",
    description="""
    Returns current application metrics including:
    - Request latencies (p50, p95, p99)
    - Error counts by type
    - Tool usage counts
    - Request counts by endpoint
    """,
)
def get_metrics() -> dict:
    """
    Get current application metrics.
    
    Returns:
        Dictionary with latency histograms, error counts, and tool usage.
    """
    return metrics.get_stats()


@router.get(
    "/circuits",
    summary="Get circuit breaker states",
    description="Returns the current state of all circuit breakers for external services.",
)
def get_circuits() -> dict:
    """
    Get circuit breaker states.
    
    Returns:
        Dictionary mapping circuit names to their current state.
    """
    return {"circuits": get_all_circuit_states()}


@router.post(
    "/reset",
    summary="Reset all metrics",
    description="Reset all metrics counters. Useful for testing.",
    include_in_schema=False,  # Hide from public docs
)
def reset_metrics() -> dict:
    """Reset all metrics (for testing/debugging)."""
    metrics.reset()
    return {"status": "reset"}
