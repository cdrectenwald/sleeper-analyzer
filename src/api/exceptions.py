"""
Custom exception hierarchy for the Sleeper Analyzer API.

This module defines domain-specific exceptions that map cleanly to HTTP status codes
and provide structured error responses. All exceptions inherit from SleeperAnalyzerError
to allow broad catching at the handler level while preserving specificity.

Exception Hierarchy:
    SleeperAnalyzerError (base)
    ├── ValidationError (400)
    ├── SeasonNotFoundError (404)
    ├── LeagueNotFoundError (404)
    ├── ManagerNotFoundError (404)
    ├── PlayerNotFoundError (404)
    ├── LLMError (502)
    │   ├── LLMTimeoutError (504)
    │   └── LLMRateLimitError (429)
    └── DataError (500)

Example:
    >>> from src.api.exceptions import SeasonNotFoundError
    >>> raise SeasonNotFoundError(season="2019")
    # Results in 404 with {"error": "season_not_found", "detail": "..."}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


class SleeperAnalyzerError(Exception):
    """
    Base exception for all Sleeper Analyzer domain errors.

    Attributes:
        status_code: HTTP status code to return.
        error_code: Machine-readable error identifier (e.g., "season_not_found").
        detail: Human-readable error message.
        context: Additional structured data for debugging.

    All subclasses should set appropriate defaults for status_code and error_code.
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        detail: str = "An unexpected error occurred",
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the exception.

        Args:
            detail: Human-readable error message.
            context: Additional key-value pairs for debugging/logging.
        """
        super().__init__(detail)
        self.detail = detail
        self.context = context or {}

    def to_response_dict(self) -> dict[str, Any]:
        """
        Convert exception to a JSON-serializable response body.

        Returns:
            Dictionary with 'error', 'detail', and optionally 'context' keys.
        """
        response = {
            "error": self.error_code,
            "detail": self.detail,
        }
        # Only include context in non-production or if explicitly safe
        if self.context:
            response["context"] = self.context
        return response


# --- 4xx Client Errors ---


class ValidationError(SleeperAnalyzerError):
    """
    Request validation failed beyond Pydantic's automatic validation.

    Use for semantic validation (e.g., week_start > week_end, invalid season format).
    """

    status_code = 400
    error_code = "validation_error"


class SeasonNotFoundError(SleeperAnalyzerError):
    """Requested season does not exist in the database."""

    status_code = 404
    error_code = "season_not_found"

    def __init__(self, season: str) -> None:
        super().__init__(
            detail=f"Season '{season}' not found. Available seasons: 2022, 2023, 2024, 2025.",
            context={"season": season},
        )


class LeagueNotFoundError(SleeperAnalyzerError):
    """Requested league_id does not exist or has no data."""

    status_code = 404
    error_code = "league_not_found"

    def __init__(self, league_id: str, season: str | None = None) -> None:
        msg = f"League '{league_id}' not found"
        if season:
            msg += f" for season {season}"
        super().__init__(detail=msg, context={"league_id": league_id, "season": season})


class ManagerNotFoundError(SleeperAnalyzerError):
    """Requested manager/team name does not exist in the league."""

    status_code = 404
    error_code = "manager_not_found"

    def __init__(self, manager_name: str, season: str | None = None) -> None:
        msg = f"Manager '{manager_name}' not found"
        if season:
            msg += f" in {season} season"
        super().__init__(
            detail=msg, context={"manager_name": manager_name, "season": season}
        )


class PlayerNotFoundError(SleeperAnalyzerError):
    """Requested player does not exist in the player database."""

    status_code = 404
    error_code = "player_not_found"

    def __init__(self, player_name: str) -> None:
        super().__init__(
            detail=f"Player '{player_name}' not found in database.",
            context={"player_name": player_name},
        )


# --- 5xx Server Errors ---


class LLMError(SleeperAnalyzerError):
    """
    Error communicating with the LLM (OpenAI) service.

    Base class for LLM-specific errors. Use subclasses for specific failure modes.
    """

    status_code = 502
    error_code = "llm_error"

    def __init__(self, detail: str = "Failed to get response from AI service") -> None:
        super().__init__(detail=detail)


class LLMTimeoutError(LLMError):
    """LLM request timed out."""

    status_code = 504
    error_code = "llm_timeout"

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        super().__init__(
            detail=f"AI service timed out after {timeout_seconds:.1f}s. Try a simpler question."
        )


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded."""

    status_code = 429
    error_code = "llm_rate_limit"

    def __init__(self, retry_after: int | None = None) -> None:
        detail = "AI service rate limit exceeded. Please wait before trying again."
        super().__init__(detail=detail)
        if retry_after:
            self.context["retry_after_seconds"] = retry_after


class DataError(SleeperAnalyzerError):
    """
    Database or data processing error.

    Use when queries fail or data is in an unexpected state.
    """

    status_code = 500
    error_code = "data_error"


# --- Exception Handlers ---


async def sleeper_analyzer_exception_handler(
    request: Request, exc: SleeperAnalyzerError
) -> JSONResponse:
    """
    Global exception handler for SleeperAnalyzerError and subclasses.

    Logs the error with context and returns a structured JSON response.

    Args:
        request: The FastAPI request that triggered the exception.
        exc: The raised SleeperAnalyzerError instance.

    Returns:
        JSONResponse with appropriate status code and error body.
    """
    log.warning(
        "API error: %s [%s] path=%s context=%s",
        exc.error_code,
        exc.status_code,
        request.url.path,
        exc.context,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response_dict(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected exceptions.

    Logs the full traceback and returns a generic 500 error to avoid leaking
    internal details to clients.

    Args:
        request: The FastAPI request that triggered the exception.
        exc: The unhandled exception.

    Returns:
        JSONResponse with 500 status and generic error message.
    """
    log.exception(
        "Unhandled exception: %s path=%s",
        type(exc).__name__,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": "An unexpected error occurred. Please try again later.",
        },
    )
