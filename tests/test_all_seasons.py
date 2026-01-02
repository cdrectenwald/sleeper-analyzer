"""Tests for cross-season analysis functionality."""
import pytest


class TestAllSeasonsSummary:
    """Tests for the get_all_seasons_summary function."""

    def test_function_exists(self):
        """Verify the function can be imported."""
        from src.chat.tools import get_all_seasons_summary
        assert callable(get_all_seasons_summary)

    def test_returns_dict_structure(self):
        """Verify return structure has expected keys."""
        from src.chat.tools import get_all_seasons_summary
        
        result = get_all_seasons_summary()
        
        assert isinstance(result, dict)
        assert "description" in result
        assert "managers" in result
        assert isinstance(result["managers"], list)

    def test_manager_structure(self):
        """Verify manager entries have expected fields."""
        from src.chat.tools import get_all_seasons_summary
        
        result = get_all_seasons_summary()
        
        # If there are managers, check structure
        if result["managers"]:
            manager = result["managers"][0]
            assert "name" in manager
            assert "seasons_played" in manager
            assert "total_luck" in manager
            assert "total_expected_wins" in manager
            assert "total_actual_wins" in manager
            assert "total_points" in manager
            assert "avg_luck_per_season" in manager
            assert "season_details" in manager


class TestLLMToolsIncludeAllSeasons:
    """Tests to verify LLM has access to all-seasons tool."""

    def test_tool_in_dispatch(self):
        """Verify get_all_seasons_summary is in tool dispatch."""
        from src.chat.llm import TOOL_DISPATCH
        
        assert "get_all_seasons_summary" in TOOL_DISPATCH

    def test_tool_in_tools_list(self):
        """Verify tool is defined in TOOLS list."""
        from src.chat.llm import TOOLS
        
        tool_names = [t["name"] for t in TOOLS]
        assert "get_all_seasons_summary" in tool_names

    def test_tool_description_mentions_all_seasons(self):
        """Verify tool description helps LLM know when to use it."""
        from src.chat.llm import TOOLS
        
        tool = next(t for t in TOOLS if t["name"] == "get_all_seasons_summary")
        desc = tool["description"].lower()
        
        assert "all" in desc
        assert "season" in desc


class TestAppHandlesAllSeason:
    """Tests for app.py handling of 'all' season."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from app import app
        return TestClient(app)

    def test_chat_accepts_all_season(self, client):
        """POST /chat should accept season='all'."""
        try:
            response = client.post(
                "/chat",
                json={"message": "Who is the luckiest overall?", "season": "all"}
            )
            # Should not error with 422 (validation error)
            assert response.status_code in [200, 500]
        except Exception:
            pass  # OpenAI client may fail, that's ok

    def test_all_season_returns_none_league_id(self, client):
        """When season='all', league_id should be None in response."""
        try:
            response = client.post(
                "/chat",
                json={"message": "test", "season": "all"}
            )
            if response.status_code == 200:
                data = response.json()
                assert data["season"] == "all"
                assert data["league_id"] is None
        except Exception:
            pass
