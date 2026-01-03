import json
import logging
import time

from openai import OpenAI, APIError, RateLimitError, APITimeoutError

from src.chat.tools import (
    get_luck_for_range,
    get_luck_leaderboard,
    get_all_seasons_summary,
    get_top_players_for_season,
    get_player_weekly_scores,
    get_manager_roster_history,
)
from src.common.observability import metrics
from src.common.resilience import with_retry, circuit_breaker, CircuitOpenError, RetryError

log = logging.getLogger(__name__)

_client = None

def _get_client() -> OpenAI:
    """Get or create the OpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client

SYSTEM_PROMPT = """You are the Keenasty Fantasy Football Analyst - think Bill Simmons meets your trash-talking group chat. 

PERSONALITY:
- Conversational, witty, and occasionally sarcastic
- Use sports analogies and pop culture references
- Call out bad luck sympathetically but roast good luck mercilessly  
- Reference specific stats to back up your takes
- Keep responses punchy - no one wants a dissertation
- Use phrases like "here's the thing", "and it's not even close", "this is the underrated story"

CRITICAL - ANSWER IN ONE SHOT:
- NEVER ask clarifying questions. Make reasonable assumptions and answer immediately.
- If season is "all", query ALL available seasons (2022, 2023, 2024, 2025) in parallel.
- If season is specific (e.g., "2024"), use that season only.
- When asked about "best players" or "top scorers", call get_top_players_for_season with a high limit (50+).
- When asked about luck/managers, call get_luck_leaderboard.
- Default to giving MORE data, not less. Users can skim.
- If data is missing for some seasons, just report what you have.

TOOL USAGE STRATEGY:
- Call multiple tools in PARALLEL when you need data from multiple sources.
- For "all seasons" player queries, call get_top_players_for_season for EACH season simultaneously.
- For "all seasons" luck queries, use get_all_seasons_summary (it handles aggregation).
- NEVER make the user wait for a follow-up. Give a complete answer on the first response.

RULES:
- NEVER mention league_id to the user - they only care about the SEASON YEAR
- If asking about players (NFL players like Mahomes, Kelce), use player tools
- If asking about managers/teams (fantasy team owners), use manager/luck tools
- Always explain what the stats MEAN, not just what they are

GLOSSARY (use naturally in explanations):
- Luck Score: Actual wins minus expected wins. Positive = lucky, negative = cursed.
- All-Play Record: How you'd do playing everyone every week. The truest measure of team quality.
- Expected Wins: What your record "should" be based on points scored.

RESPONSE FORMAT:
After your main response, add on its own line at the very end:
[META: confidence=high|medium|low, suggestions="question 1?|question 2?"]

Confidence: high (data found), medium (partial), low (inference/missing data)
Suggestions: 1-3 natural follow-up questions separated by |

Be entertaining. These are friends roasting each other about fantasy football."""

TOOLS = [
    {
        "type": "function",
        "name": "get_luck_for_range",
        "description": "Get luck stats for a specific WEEK RANGE within a single season. Use when user asks about specific weeks like 'playoff weeks' or 'weeks 10-14'.",
        "parameters": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Sleeper league_id (use from defaults)"},
                "season": {"type": "string", "description": "Season year, e.g. '2024'"},
                "week_start": {"type": "integer", "description": "First week inclusive"},
                "week_end": {"type": "integer", "description": "Last week inclusive"},
            },
            "required": ["league_id", "season", "week_start", "week_end"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_luck_leaderboard",
        "description": "Get the full-season luck leaderboard for ONE season. Shows who was luckiest/unluckiest for the entire year.",
        "parameters": {
            "type": "object",
            "properties": {
                "league_id": {"type": "string", "description": "Sleeper league_id (use from defaults)"},
                "season": {"type": "string", "description": "Season year"},
            },
            "required": ["league_id", "season"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_all_seasons_summary",
        "description": "Get ALL-TIME career stats across ALL seasons. Use when user selects 'All-Time', asks about 'overall', 'career', 'all seasons', or wants to compare across years.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_top_players_for_season",
        "description": "Get the highest-scoring NFL PLAYERS in the league for a season. Use when asking about player performance, top scorers, best players.",
        "parameters": {
            "type": "object",
            "properties": {
                "season": {"type": "string", "description": "Season year"},
                "limit": {"type": "integer", "description": "Number of players to return (default 20)"},
            },
            "required": ["season"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_player_weekly_scores",
        "description": "Get week-by-week scores for a specific NFL player. Use when asking about a particular player's performance.",
        "parameters": {
            "type": "object",
            "properties": {
                "season": {"type": "string", "description": "Season year"},
                "player_name": {"type": "string", "description": "Player name (partial match OK, e.g. 'Mahomes' or 'Travis Kelce')"},
            },
            "required": ["season", "player_name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_manager_roster_history",
        "description": "Get detailed stats for a specific MANAGER/TEAM for a season. Weekly breakdown and season summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "manager_name": {"type": "string", "description": "Manager's display name (partial match OK)"},
                "season": {"type": "string", "description": "Season year"},
            },
            "required": ["manager_name", "season"],
            "additionalProperties": False,
        },
    },
]

TOOL_DISPATCH = {
    "get_luck_for_range": get_luck_for_range,
    "get_luck_leaderboard": get_luck_leaderboard,
    "get_all_seasons_summary": get_all_seasons_summary,
    "get_top_players_for_season": get_top_players_for_season,
    "get_player_weekly_scores": get_player_weekly_scores,
    "get_manager_roster_history": get_manager_roster_history,
}


@with_retry(max_attempts=3, backoff_base=2.0, retryable_exceptions=(RateLimitError, APITimeoutError))
@circuit_breaker(name="openai", failure_threshold=5, recovery_timeout=60)
def _call_openai(input_list: list, tools: list) -> any:
    """
    Make a resilient OpenAI API call.
    
    - Retries up to 3 times on rate limits or timeouts
    - Circuit breaker opens after 5 consecutive failures
    - Metrics recorded for latency and errors
    """
    start = time.perf_counter()
    try:
        resp = _get_client().responses.create(
            model="gpt-5",
            tools=tools,
            input=input_list,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        metrics.record_latency("openai_api", elapsed_ms)
        return resp
    except APIError as e:
        metrics.record_error(f"openai_{type(e).__name__}")
        raise


def answer(
    question: str,
    default_league_id: str | None = None,
    default_season: str | None = None,
    history: list[dict] | None = None,
) -> dict:
    """
    Generate an AI response to a fantasy football question.

    Args:
        question: The user's question.
        default_league_id: The league_id to use if not specified.
        default_season: The season to use if not specified.
        history: Optional list of previous messages [{"role": "user"|"assistant", "content": "..."}].

    Returns:
        Dictionary with 'answer', 'confidence', and 'follow_up_suggestions' keys.
    """
    log.debug("LLM question: %s", question[:100])
    

    context_hint = ""
    if default_season:
        context_hint = f"\n\n[Internal context - do not mention league_id to user: season={default_season}"
        if default_league_id:
            context_hint += f", league_id={default_league_id}"
        context_hint += "]"
    
    input_list = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
    ]
    
    # Keeping history could be more robust, but limited to 10 messages for now
    if history:
        for msg in history[-10:]:
            input_list.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
    
    input_list.append({
        "role": "user",
        "content": question + context_hint,
    })

    tools_called = []
    
    for iteration in range(4):
        try:
            resp = _call_openai(input_list, TOOLS)
        except CircuitOpenError:
            log.error("OpenAI circuit breaker is open, failing fast")
            return {
                "answer": "The AI service is temporarily overloaded. Please try again in a minute.",
                "confidence": "low",
                "follow_up_suggestions": ["Try again shortly"],
            }
        except RetryError as e:
            log.error("OpenAI API failed after retries: %s", e)
            return {
                "answer": "Having trouble connecting to the AI service. Please try again.",
                "confidence": "low",
                "follow_up_suggestions": ["Try again shortly"],
            }

        input_list += resp.output

        tool_called = False
        for item in resp.output:
            if item.type == "function_call":
                tool_called = True
                fn = TOOL_DISPATCH.get(item.name)
                if not fn:
                    log.warning("Unknown tool called: %s", item.name)
                    input_list.append(
                        {
                            "type": "function_call_output",
                            "call_id": item.call_id,
                            "output": json.dumps({"error": f"Unknown tool: {item.name}"}),
                        }
                    )
                    continue

                args = json.loads(item.arguments) if item.arguments else {}
                
                # Log tool call and measure timing
                tool_start = time.perf_counter()
                log.info("Tool call: %s with args: %s", item.name, list(args.keys()))
                
                result = fn(**args)
                
                tool_elapsed = time.perf_counter() - tool_start
                tools_called.append({"name": item.name, "duration": tool_elapsed})
                log.info("Tool %s completed in %.3fs", item.name, tool_elapsed)
                
                # Record tool call in metrics
                metrics.record_tool_call(item.name)
                metrics.record_latency(f"tool_{item.name}", tool_elapsed * 1000)
                
                input_list.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": json.dumps(result),
                    }
                )

        # If no tool was called, the model produced a final natural language answer.
        if not tool_called:
            log.debug("LLM completed after %d iterations, tools used: %s", 
                     iteration + 1, [t["name"] for t in tools_called])
            return _parse_response(resp.output_text, tools_called)

    log.warning("Hit tool-call limit after %d iterations", 4)
    return {
        "answer": "I hit the tool-call limit while answering. Try narrowing the question (season, week range).",
        "confidence": "low",
        "follow_up_suggestions": ["Try asking about a specific season", "Ask about a specific manager"],
    }


def _parse_response(text: str, tools_called: list[dict]) -> dict:
    """
    Parse the LLM response to extract metadata.

    The LLM is instructed to append a metadata line like:
    [META: confidence=high, suggestions="Who was unluckiest?|Compare to last year"]

    Args:
        text: Raw LLM response text.
        tools_called: List of tools that were called (used to infer confidence).

    Returns:
        Dictionary with 'answer', 'confidence', and 'follow_up_suggestions'.
    """
    import re
    
    # Default values
    confidence = "high" if tools_called else "medium"
    suggestions = None
    answer_text = text
    
    # Try to parse [META: ...] line
    meta_pattern = r'\[META:\s*confidence=(high|medium|low)(?:,\s*suggestions="([^"]*)")?\]'
    match = re.search(meta_pattern, text, re.IGNORECASE)
    
    if match:
        confidence = match.group(1).lower()
        if match.group(2):
            suggestions = [s.strip() for s in match.group(2).split("|") if s.strip()]
        # Remove the metadata line from the answer
        answer_text = re.sub(r'\n?\[META:[^\]]*\]', '', text).strip()
    
    return {
        "answer": answer_text,
        "confidence": confidence,
        "follow_up_suggestions": suggestions,
    }
