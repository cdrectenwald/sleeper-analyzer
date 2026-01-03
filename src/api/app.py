"""
FastAPI application factory.

Provides create_app() to construct and configure the FastAPI application.
The factory pattern enables different configs for testing vs production,
clean dependency injection, and easier testing with fresh app instances.
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

STATIC_DIR = Path(__file__).parent.parent.parent / "static"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware that generates correlation IDs, records latency, and tracks errors."""

    async def dispatch(self, request: Request, call_next):
        # Create request context with correlation ID
        ctx = RequestContext()
        
        request.state.request_context = ctx
        start = time.perf_counter()
        
        try:
            response = await call_next(request)
            
            # Record latency for non-static requests
            if not request.url.path.startswith("/static"):
                elapsed_ms = (time.perf_counter() - start) * 1000
                metrics.record_latency(request.url.path, elapsed_ms)
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
    """Create and configure the FastAPI application."""
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

    app.add_exception_handler(SleeperAnalyzerError, sleeper_analyzer_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_middleware(ObservabilityMiddleware)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
        log.debug("Mounted static files from %s", STATIC_DIR)
    else:
        log.warning("Static directory not found: %s", STATIC_DIR)

    app.include_router(chat_router)
    app.include_router(health_router)
    app.include_router(metrics_router)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """Serve the main chat UI."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/glossary", include_in_schema=False)
    def glossary() -> FileResponse:
        """Serve the glossary page."""
        return FileResponse(STATIC_DIR / "glossary.html")

    log.info("Application created: %s v%s", title, version)
    return app
app = create_app()
