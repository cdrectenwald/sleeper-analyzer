"""
FastAPI application factory.

This module provides the create_app() factory function that constructs
and configures the FastAPI application instance. Using a factory pattern
allows for:
- Different configurations for testing vs. production
- Clean dependency injection
- Easier testing with fresh app instances

The factory pattern is preferred over a global app instance for
professional-grade applications.

Example:
    >>> from src.api import create_app
    >>> app = create_app()
    >>> # Use with uvicorn: uvicorn src.api.app:create_app --factory
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi.staticfiles import StaticFiles

from src.api.exceptions import (
    SleeperAnalyzerError,
    sleeper_analyzer_exception_handler,
    unhandled_exception_handler,
)
from src.api.routes import chat_router, health_router
from src.api.routes.metrics import router as metrics_router
from src.common.observability import RequestContext, metrics

log = logging.getLogger(__name__)

# Static files directory (relative to project root)
STATIC_DIR = Path(__file__).parent.parent.parent / "static"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Middleware for request tracking and metrics collection.
    
    For each request:
    - Generates a unique correlation ID
    - Records request latency
    - Tracks errors
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request with observability tracking."""
        # Create request context with correlation ID
        ctx = RequestContext()
        
        # Store in request state for access in route handlers
        request.state.request_context = ctx
        
        # Track timing
        start = time.perf_counter()
        
        try:
            response = await call_next(request)
            
            # Record latency for non-static requests
            if not request.url.path.startswith("/static"):
                elapsed_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(request.url.path, elapsed_ms)
                
                # Add correlation ID to response headers
                response.headers["X-Correlation-ID"] = ctx.request_id
            
            return response
            
        except Exception as e:
            # Record error
            metrics.record_error(type(e).__name__)
            raise


def create_app(
    title: str = "Sleeper Analyzer",
    version: str = "0.1.0",
    debug: bool = False,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    This factory function:
    1. Creates the FastAPI instance with metadata
    2. Registers exception handlers
    3. Mounts static file serving
    4. Includes all route modules
    5. Sets up the root redirect

    Args:
        title: Application title for OpenAPI docs.
        version: Application version for OpenAPI docs.
        debug: Enable debug mode (more verbose errors).

    Returns:
        Configured FastAPI application instance.

    Example:
        >>> app = create_app(debug=True)
        >>> # For production: app = create_app()
    """
    app = FastAPI(
        title=title,
        version=version,
        description="""
        Fantasy Football League Analyzer powered by AI.
        
        Analyze luck scores, player performance, and manager stats
        across your Sleeper fantasy football league history.
        
        Features a Bill Simmons-style personality that roasts the lucky
        and sympathizes with the cursed.
        """,
        docs_url="/docs",
        redoc_url="/redoc",
        debug=debug,
    )

    # --- Exception Handlers ---
    # Order matters: more specific handlers should be registered first,
    # but FastAPI matches by inheritance, so base class handler catches subclasses.
    app.add_exception_handler(SleeperAnalyzerError, sleeper_analyzer_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # --- Middleware ---
    # Add observability middleware for request tracking
    app.add_middleware(ObservabilityMiddleware)

    # --- Static Files ---
    # Mount static directory for CSS, JS, images
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
        log.debug("Mounted static files from %s", STATIC_DIR)
    else:
        log.warning("Static directory not found: %s", STATIC_DIR)

    # --- Routes ---
    app.include_router(chat_router)
    app.include_router(health_router)
    app.include_router(metrics_router)

    # --- Root Routes (must be after router includes to avoid shadowing) ---
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """
        Serve the main chat UI.

        Returns the index.html file from the static directory.
        This is the entry point for the web application.
        """
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/glossary", include_in_schema=False)
    def glossary() -> FileResponse:
        """
        Serve the glossary page.

        Returns the glossary.html file explaining fantasy football
        statistics and terminology used by the analyzer.
        """
        return FileResponse(STATIC_DIR / "glossary.html")

    log.info("Application created: %s v%s", title, version)
    return app


# Default app instance for uvicorn (non-factory mode)
# Usage: uvicorn src.api.app:app --reload
app = create_app()
