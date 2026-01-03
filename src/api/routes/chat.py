"""
Chat endpoint for LLM-powered fantasy football analysis.

Routes user questions to the LLM service and returns AI-generated analysis.
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
    """Process a chat message and return AI-generated analysis."""
    from src.chat.llm import answer

    start = time.perf_counter()
    season = req.season or settings.default_season

    # Resolve league_id based on season
    if season.lower() == "all":
        league_id = None  
        season_display = "all"
    else:
        league_id = req.league_id or settings.default_leagues.get(season)
        season_display = season

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
