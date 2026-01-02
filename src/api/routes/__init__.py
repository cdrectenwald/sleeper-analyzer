"""
API route modules.

Each module in this package defines an APIRouter with related endpoints.
Routers are registered with the main application via include_router().

Modules:
    chat: Chat/LLM interaction endpoints
    health: Health check and status endpoints
    static: Static file serving for the web UI
"""

from src.api.routes.chat import router as chat_router
from src.api.routes.health import router as health_router

__all__ = ["chat_router", "health_router"]
