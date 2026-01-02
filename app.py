"""
Sleeper Analyzer - Fantasy Football League Analysis.

This is the application entry point. The actual application is defined
in src/api/app.py using the factory pattern.

Usage:
    # Development (with auto-reload):
    uvicorn app:app --reload

    # Production:
    uvicorn app:app --host 0.0.0.0 --port 8000

    # Using factory pattern (alternative):
    uvicorn src.api.app:create_app --factory

For testing, import create_app() to get fresh instances:
    >>> from src.api import create_app
    >>> app = create_app(debug=True)
"""

from src.common.logging import setup_logging
from src.config import settings

# Initialize logging before importing app to capture startup logs
setup_logging(settings.log_level)

# Re-export the app instance and models for backward compatibility
from src.api.app import app, create_app
from src.api.models import ChatRequest, ChatResponse

# Alias for backward compatibility with existing imports
ChatReq = ChatRequest

__all__ = ["app", "create_app", "ChatRequest", "ChatReq", "ChatResponse"]


