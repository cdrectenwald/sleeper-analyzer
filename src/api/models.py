"""
Pydantic models for API request validation and response serialization.

This module defines all request and response schemas used by the API endpoints.
Models use Pydantic v2 conventions with:
- Field validators for semantic validation
- Comprehensive field descriptions for OpenAPI docs
- Example values for documentation

Naming Convention:
    - Requests: <Entity><Action>Request (e.g., ChatRequest)
    - Responses: <Entity>Response (e.g., ChatResponse)
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    """A single message in the conversation history."""

    role: Annotated[
        str,
        Field(description="Message role: 'user' or 'assistant'"),
    ]
    content: Annotated[
        str,
        Field(description="Message content"),
    ]


class ChatRequest(BaseModel):
    """
    Request body for the /chat endpoint.

    Attributes:
        message: The user's question or command. Must be non-empty.
        season: Optional season year (e.g., "2024"). If omitted, uses default.
                Special value "all" triggers cross-season analysis.
        league_id: Optional Sleeper league ID. If omitted, derived from season.
        history: Optional conversation history for context.

    Example:
        >>> req = ChatRequest(message="Who was the luckiest manager?", season="2024")
    """

    message: Annotated[
        str,
        Field(
            min_length=1,
            max_length=2000,
            description="The question to ask the fantasy football analyst",
            json_schema_extra={"example": "Who was the luckiest manager this season?"},
        ),
    ]
    season: Annotated[
        str | None,
        Field(
            default=None,
            description="Season year (e.g., '2024') or 'all' for cross-season analysis",
            json_schema_extra={"example": "2024"},
        ),
    ] = None
    league_id: Annotated[
        str | None,
        Field(
            default=None,
            description="Sleeper league ID. Omit to use the default for the selected season",
            json_schema_extra={"example": "1124856081965645824"},
        ),
    ] = None
    history: Annotated[
        list[ChatMessage] | None,
        Field(
            default=None,
            description="Previous conversation messages for context. Max 10 messages.",
        ),
    ] = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        """Ensure message contains non-whitespace content."""
        if not v.strip():
            raise ValueError("Message cannot be empty or whitespace-only")
        return v.strip()

    @field_validator("season")
    @classmethod
    def validate_season(cls, v: str | None) -> str | None:
        """Validate season format if provided."""
        if v is None:
            return None
        v = v.strip().lower()
        if v == "all":
            return "all"
        # Expect a 4-digit year
        if not v.isdigit() or len(v) != 4:
            raise ValueError("Season must be a 4-digit year (e.g., '2024') or 'all'")
        year = int(v)
        if year < 2020 or year > 2030:
            raise ValueError("Season year must be between 2020 and 2030")
        return v


class ChatResponse(BaseModel):
    """
    Response body for the /chat endpoint.

    Attributes:
        answer: The AI-generated response to the user's question.
        confidence: How confident the AI is in its answer (high/medium/low).
        season: The season that was queried (for display purposes).
        league_id: The league_id used (None for cross-season queries).
        follow_up_suggestions: Optional suggested follow-up questions.

    Example:
        >>> resp = ChatResponse(answer="Here's the thing about luck...", confidence="high")
    """

    answer: Annotated[
        str,
        Field(description="The AI analyst's response"),
    ]
    confidence: Annotated[
        str,
        Field(
            description="Confidence level: 'high' (data found), 'medium' (partial data), 'low' (inference/guess)",
            json_schema_extra={"example": "high"},
        ),
    ] = "high"
    season: Annotated[
        str | None,
        Field(description="Season that was queried"),
    ] = None
    league_id: Annotated[
        str | None,
        Field(description="League ID that was queried (None for all-seasons)"),
    ] = None
    follow_up_suggestions: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="Suggested follow-up questions based on the response",
        ),
    ] = None


class ErrorResponse(BaseModel):
    """
    Standard error response body.

    Used by exception handlers to return structured errors.
    Matches the format produced by SleeperAnalyzerError.to_response_dict().

    Attributes:
        error: Machine-readable error code (e.g., "validation_error").
        detail: Human-readable error description.
        context: Optional additional error context (debugging info).
    """

    error: Annotated[str, Field(description="Machine-readable error code")]
    detail: Annotated[str, Field(description="Human-readable error message")]
    context: Annotated[
        dict | None,
        Field(default=None, description="Additional error context"),
    ] = None


class HealthResponse(BaseModel):
    """
    Response body for the /health endpoint.

    Used by load balancers and monitoring systems to verify service health.
    """

    status: Annotated[
        str,
        Field(description="Health status", json_schema_extra={"example": "ok"}),
    ]
    version: Annotated[
        str,
        Field(description="Application version", json_schema_extra={"example": "0.1.0"}),
    ]
