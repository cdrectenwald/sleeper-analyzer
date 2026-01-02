"""
Health check endpoints for monitoring and load balancing.

Provides endpoints for:
- Basic liveness checks (is the service running?)
- Readiness checks (is the service ready to accept traffic?)
- Detailed health status with dependency checks

These endpoints are designed to be lightweight and fast for use by
Kubernetes probes, load balancers, and monitoring systems.

Endpoints:
    GET /health - Basic health check
    GET /health/ready - Readiness check with database connectivity test
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
    """
    Basic liveness check.

    This endpoint should always return 200 if the Python process is healthy.
    Does not check external dependencies.

    Returns:
        HealthResponse with status "ok" and current version.
    """
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
    """
    Readiness check with dependency verification.

    Checks:
    - Database file exists and is readable
    - Database connection can be established
    - Basic query executes successfully

    Returns:
        HealthResponse with status "ok" if all checks pass.

    Raises:
        HTTPException: 503 if any dependency check fails.
    """
    from fastapi import HTTPException

    db_path = Path(settings.db_path)

    # Check database file exists
    if not db_path.exists():
        log.warning("Readiness check failed: database not found at %s", db_path)
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "reason": "database_not_found"},
        )

    # Check database is queryable
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
