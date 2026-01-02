"""
Chat endpoint for LLM-powered fantasy football analysis.

This module handles the core chat functionality, routing user questions
to the LLM service and returning AI-generated analysis.

Endpoints:
    POST /chat - Submit a question and receive AI analysis

Example:
    >>> import httpx
    >>> resp = httpx.post("/chat", json={"message": "Who was luckiest?", "season": "2024"})
    >>> print(resp.json()["answer"])
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter

from src.api.exceptions import LLMError, LLMTimeoutError, LLMRateLimitError
from src.api.models import ChatRequest, ChatResponse, ErrorResponse
from src.config import settings

if TYPE_CHECKING:
    from openai import RateLimitError, APITimeoutError

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        502: {"model": ErrorResponse, "description": "LLM service error"},
        504: {"model": ErrorResponse, "description": "LLM timeout"},
    },
    summary="Chat with the fantasy football analyst",
    description="""
    Submit a natural language question about your fantasy football league.
    
    The AI analyst (with a Bill Simmons-style personality) will query the 
    database and provide analysis on luck scores, player performance, 
    manager stats, and more.
    
    **Season options:**
    - Specific year: "2024", "2023", etc.
    - All-time: "all" for cross-season career analysis
    - Omit to use the default season
    """,
)
def chat(req: ChatRequest) -> ChatResponse:
    """
    Process a chat message and return AI-generated analysis.

    This endpoint:
    1. Resolves the season and league_id from the request or defaults
    2. Passes the question to the LLM with function-calling capabilities
    3. Returns the AI's response with confidence and suggestions

    Args:
        req: Validated chat request with message, optional season/league_id, and history.

    Returns:
        ChatResponse with the AI's answer, confidence level, and follow-up suggestions.

    Raises:
        LLMError: If the AI service fails unexpectedly.
        LLMTimeoutError: If the AI service times out.
        LLMRateLimitError: If the AI service rate limit is exceeded.
    """
    # Lazy import to avoid circular dependency and speed up module load
    from src.chat.llm import answer

    start = time.perf_counter()
    season = req.season or settings.default_season

    # Resolve league_id based on season
    if season.lower() == "all":
        league_id = None  # Cross-season queries don't use a specific league
        season_display = "all"
    else:
        league_id = req.league_id or settings.default_leagues.get(season)
        season_display = season

    # Convert history to dict format for LLM
    history = None
    if req.history:
        history = [{"role": m.role, "content": m.content} for m in req.history]

    log.info(
        "Chat request: season=%s league_id=%s message_length=%d history_length=%d",
        season_display,
        league_id,
        len(req.message),
        len(history) if history else 0,
    )

    try:
        result = answer(
            question=req.message,
            default_league_id=league_id,
            default_season=season_display,
            history=history,
        )
    except Exception as e:
        # Handle specific OpenAI exceptions
        error_type = type(e).__name__

        if "RateLimitError" in error_type:
            log.warning("LLM rate limit hit: %s", e)
            raise LLMRateLimitError() from e
        elif "Timeout" in error_type or "APITimeoutError" in error_type:
            log.warning("LLM timeout: %s", e)
            raise LLMTimeoutError() from e
        else:
            log.exception("LLM error: %s", e)
            raise LLMError(detail=f"AI service error: {error_type}") from e

    elapsed = time.perf_counter() - start
    log.info("Chat response generated in %.2fs (confidence=%s)", elapsed, result.get("confidence"))

    return ChatResponse(
        answer=result["answer"],
        confidence=result.get("confidence", "high"),
        season=season_display,
        league_id=league_id,
        follow_up_suggestions=result.get("follow_up_suggestions"),
    )
