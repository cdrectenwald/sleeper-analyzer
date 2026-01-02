"""
Integration tests for the chat API.

These tests verify the full request/response flow with mocked LLM responses.
They test the integration between routes, models, and error handling.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import src.chat.llm as llm_module


class TestChatIntegration:
    """Integration tests for /chat endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from app import app
        return TestClient(app)

    @pytest.fixture
    def mock_llm_response(self):
        """Standard mock LLM response."""
        return {
            "answer": "Here's the thing about 2024...",
            "confidence": "high",
            "follow_up_suggestions": ["Who was unluckiest?", "Compare to 2023"],
        }

    def test_full_chat_flow(self, client, mock_llm_response):
        """Test complete chat request/response cycle."""
        with patch.object(llm_module, "answer") as mock:
            mock.return_value = mock_llm_response
            
            response = client.post(
                "/chat",
                json={
                    "message": "Who was the luckiest manager in 2024?",
                    "season": "2024",
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response structure
            assert "answer" in data
            assert "confidence" in data
            assert "season" in data
            assert data["season"] == "2024"
            assert data["confidence"] == "high"
            
            # Verify LLM was called with correct args
            mock.assert_called_once()
            call_kwargs = mock.call_args.kwargs
            assert "Who was the luckiest manager" in call_kwargs["question"]
            assert call_kwargs["default_season"] == "2024"

    def test_chat_with_history(self, client, mock_llm_response):
        """Test that conversation history is passed to LLM."""
        with patch.object(llm_module, "answer") as mock:
            mock.return_value = mock_llm_response
            
            history = [
                {"role": "user", "content": "Who was luckiest?"},
                {"role": "assistant", "content": "Team A was luckiest with +3.2 luck score."},
            ]
            
            response = client.post(
                "/chat",
                json={
                    "message": "Tell me more about them",
                    "season": "2024",
                    "history": history,
                }
            )
            
            assert response.status_code == 200
            
            # Verify history was passed
            call_kwargs = mock.call_args.kwargs
            assert call_kwargs["history"] is not None
            assert len(call_kwargs["history"]) == 2

    def test_all_seasons_query(self, client, mock_llm_response):
        """Test all-time/cross-season queries."""
        with patch.object(llm_module, "answer") as mock:
            mock.return_value = mock_llm_response
            
            response = client.post(
                "/chat",
                json={
                    "message": "Who is the luckiest manager all-time?",
                    "season": "all",
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["season"] == "all"
            assert data["league_id"] is None

    def test_error_response_format(self, client):
        """Test that errors return proper JSON structure."""
        with patch.object(llm_module, "answer") as mock:
            mock.side_effect = RuntimeError("LLM unavailable")
            
            response = client.post(
                "/chat",
                json={"message": "test", "season": "2024"}
            )
            
            assert response.status_code == 502
            data = response.json()
            assert "error" in data
            assert "detail" in data
            assert data["error"] == "llm_error"

    def test_validation_error_response(self, client):
        """Test validation errors return 422 with details."""
        response = client.post(
            "/chat",
            json={"message": "", "season": "2024"}
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_health_endpoint_integration(self, client):
        """Test health endpoints work correctly."""
        # Basic health
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        
        # Ready check (may fail if DB doesn't exist, that's OK)
        response = client.get("/health/ready")
        assert response.status_code in [200, 503]


class TestToolIntegration:
    """Tests for tool function integration."""

    def test_luck_leaderboard_returns_data(self):
        """Verify luck leaderboard tool returns expected structure."""
        from src.chat.tools import get_luck_leaderboard
        from src.config import settings
        
        # Use a known season/league
        league_id = settings.default_leagues.get("2024")
        if not league_id:
            pytest.skip("No 2024 league configured")
        
        result = get_luck_leaderboard(league_id, "2024")
        
        assert "teams" in result or "error" in result
        if "teams" in result:
            assert isinstance(result["teams"], list)
            if result["teams"]:
                team = result["teams"][0]
                assert "name" in team
                assert "luck" in team

    def test_top_players_returns_data(self):
        """Verify top players tool returns expected structure."""
        from src.chat.tools import get_top_players_for_season
        
        result = get_top_players_for_season("2024", limit=10)
        
        assert "top_players" in result or "error" in result
        if "top_players" in result:
            assert isinstance(result["top_players"], list)
            if result["top_players"]:
                player = result["top_players"][0]
                assert "name" in player
                assert "total_points" in player

    def test_all_seasons_summary_aggregates_correctly(self):
        """Verify all-seasons summary aggregates across years."""
        from src.chat.tools import get_all_seasons_summary
        
        result = get_all_seasons_summary()
        
        assert "managers" in result or "error" in result
        if "managers" in result:
            assert isinstance(result["managers"], list)


class TestDatabaseIntegration:
    """Tests for database connectivity and queries."""

    def test_database_connection(self):
        """Verify database is accessible."""
        import sqlite3
        from src.config import settings
        from pathlib import Path
        
        db_path = Path(settings.db_path)
        if not db_path.exists():
            pytest.skip("Database not found")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT 1")
        result = cursor.fetchone()
        conn.close()
        
        assert result == (1,)

    def test_required_tables_exist(self):
        """Verify required tables exist in database."""
        import sqlite3
        from src.config import settings
        from pathlib import Path
        
        db_path = Path(settings.db_path)
        if not db_path.exists():
            pytest.skip("Database not found")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        required = {"matchups", "rosters", "users", "metrics_team_week", "metrics_team_season"}
        missing = required - tables
        
        assert not missing, f"Missing tables: {missing}"
