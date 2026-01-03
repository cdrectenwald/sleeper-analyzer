"""
Health check endpoints for monitoring and load balancing.

Lightweight endpoints for Kubernetes probes, load balancers, and monitoring.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter

from src.api.models import HealthResponse
from src.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="Basic health check",
    description="Returns 200 if the service is running. Use for liveness probes.",
)
def health() -> HealthResponse:
    """Basic liveness check. Always returns 200 if the process is healthy."""
    return HealthResponse(status="ok", version="0.1.0")


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness check",
    description="""
    Returns 200 if the service is ready to accept traffic.
    Verifies database connectivity before reporting ready.
    Use for readiness probes.
    """,
)
def health_ready() -> HealthResponse:
    """Readiness check. Verifies database exists and is queryable."""
    from fastapi import HTTPException

    db_path = Path(settings.db_path)

    if not db_path.exists():
        log.warning("Readiness check failed: database not found at %s", db_path)
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "reason": "database_not_found"},
        )

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
    except sqlite3.Error as e:
        log.warning("Readiness check failed: database error: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "reason": "database_error"},
        )

    return HealthResponse(status="ok", version="0.1.0")
