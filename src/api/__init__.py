"""
API module for Sleeper Analyzer.

This module contains the FastAPI application routes, request/response models,
exception handlers, and middleware configuration.

Modules:
    routes: HTTP endpoint definitions
    models: Pydantic request/response schemas
    exceptions: Custom exception hierarchy and handlers
    dependencies: Shared dependency injection factories
"""

from src.api.app import create_app

__all__ = ["create_app"]
