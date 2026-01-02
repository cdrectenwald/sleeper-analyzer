"""Tests for the FastAPI chat endpoints and web UI."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import src.chat.llm as llm_module


class TestStaticFiles:
    """Tests for static file serving."""

    def test_static_dir_exists(self):
        """Verify the static directory exists."""
        static_dir = Path(__file__).parent.parent / "static"
        assert static_dir.exists(), "static/ directory should exist"

    def test_index_html_exists(self):
        """Verify index.html exists."""
        index_path = Path(__file__).parent.parent / "static" / "index.html"
        assert index_path.exists(), "static/index.html should exist"

    def test_styles_css_exists(self):
        """Verify styles.css exists."""
        css_path = Path(__file__).parent.parent / "static" / "styles.css"
        assert css_path.exists(), "static/styles.css should exist"

    def test_app_js_exists(self):
        """Verify app.js exists."""
        js_path = Path(__file__).parent.parent / "static" / "app.js"
        assert js_path.exists(), "static/app.js should exist"

    def test_index_html_has_required_elements(self):
        """Verify index.html has the required form elements."""
        index_path = Path(__file__).parent.parent / "static" / "index.html"
        content = index_path.read_text(encoding="utf-8")
        
        # Check for essential elements
        assert 'id="chat-form"' in content, "Should have chat form"
        assert 'id="message-input"' in content, "Should have message input"
        assert 'id="send-btn"' in content, "Should have send button"
        assert 'id="chat-container"' in content, "Should have chat container"
        assert 'id="season"' in content, "Should have season selector"

    def test_app_js_has_required_functions(self):
        """Verify app.js has the required functionality."""
        js_path = Path(__file__).parent.parent / "static" / "app.js"
        content = js_path.read_text(encoding="utf-8")
        
        # Check for essential functions
        assert "addMessage" in content, "Should have addMessage function"
        assert "sendMessage" in content, "Should have sendMessage function"
        assert "fetch('/chat'" in content, "Should call /chat endpoint"


class TestChatEndpoint:
    """Tests for the /chat API endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from app import app
        return TestClient(app)

    def test_index_returns_html(self, client):
        """GET / should return the index.html page."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Sleeper Analyzer" in response.text

    def test_static_css_served(self, client):
        """Static CSS should be accessible."""
        response = client.get("/static/styles.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_static_js_served(self, client):
        """Static JS should be accessible."""
        response = client.get("/static/app.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]

    def test_chat_endpoint_accepts_post_with_mock(self, client):
        """POST /chat should accept JSON body and return AI response."""
        with patch.object(llm_module, "answer") as mock_answer:
            mock_answer.return_value = {
                "answer": "Test response from mock",
                "confidence": "high",
                "follow_up_suggestions": ["Follow up question?"],
            }
            response = client.post(
                "/chat",
                json={"message": "Who was luckiest?", "season": "2024"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["answer"] == "Test response from mock"
            assert data["season"] == "2024"
            assert data["confidence"] == "high"
            mock_answer.assert_called_once()

    def test_chat_endpoint_requires_message(self, client):
        """POST /chat should require a message field."""
        response = client.post("/chat", json={"season": "2024"})
        assert response.status_code == 422  # Validation error

    def test_chat_endpoint_rejects_empty_message(self, client):
        """POST /chat should reject empty or whitespace-only messages."""
        response = client.post("/chat", json={"message": "   "})
        assert response.status_code == 422

    def test_chat_endpoint_optional_season(self, client):
        """Season should be optional in chat request."""
        with patch.object(llm_module, "answer") as mock_answer:
            mock_answer.return_value = {
                "answer": "Response without season",
                "confidence": "high",
                "follow_up_suggestions": None,
            }
            response = client.post("/chat", json={"message": "test"})
            assert response.status_code == 200

    def test_chat_endpoint_handles_llm_error(self, client):
        """POST /chat should return 502 when LLM fails."""
        with patch.object(llm_module, "answer") as mock_answer:
            mock_answer.side_effect = RuntimeError("OpenAI is down")
            response = client.post(
                "/chat",
                json={"message": "test", "season": "2024"}
            )
            assert response.status_code == 502
            data = response.json()
            assert data["error"] == "llm_error"

    def test_chat_endpoint_handles_rate_limit(self, client):
        """POST /chat should return 429 on rate limit errors."""
        # Create a custom exception class to simulate RateLimitError
        class RateLimitError(Exception):
            """Mock OpenAI rate limit error."""
            pass

        with patch.object(llm_module, "answer") as mock_answer:
            mock_answer.side_effect = RateLimitError("Rate limit exceeded")
            response = client.post(
                "/chat",
                json={"message": "test", "season": "2024"}
            )
            assert response.status_code == 429
            data = response.json()
            assert data["error"] == "llm_rate_limit"

    def test_chat_endpoint_all_season(self, client):
        """POST /chat with season='all' should work for cross-season queries."""
        with patch.object(llm_module, "answer") as mock_answer:
            mock_answer.return_value = {
                "answer": "All-time stats response",
                "confidence": "high",
                "follow_up_suggestions": ["Who was unluckiest?"],
            }
            response = client.post(
                "/chat",
                json={"message": "Who is the luckiest all time?", "season": "all"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["season"] == "all"
            assert data["league_id"] is None
            assert data["confidence"] == "high"

    def test_chat_endpoint_with_history(self, client):
        """POST /chat with conversation history should pass it to the LLM."""
        with patch.object(llm_module, "answer") as mock_answer:
            mock_answer.return_value = {
                "answer": "Following up on your question...",
                "confidence": "high",
                "follow_up_suggestions": None,
            }
            response = client.post(
                "/chat",
                json={
                    "message": "Tell me more",
                    "season": "2024",
                    "history": [
                        {"role": "user", "content": "Who was luckiest?"},
                        {"role": "assistant", "content": "Team X was luckiest."}
                    ]
                }
            )
            assert response.status_code == 200
            # Verify history was passed to answer()
            call_args = mock_answer.call_args
            assert call_args.kwargs.get("history") is not None
            assert len(call_args.kwargs["history"]) == 2


class TestChatRequestModel:
    """Tests for the ChatRequest Pydantic model."""

    def test_chat_req_valid(self):
        """Valid ChatRequest should be accepted."""
        from src.api.models import ChatRequest
        
        req = ChatRequest(message="Who is the luckiest?")
        assert req.message == "Who is the luckiest?"
        assert req.season is None
        assert req.league_id is None

    def test_chat_req_with_season(self):
        """ChatRequest with season should work."""
        from src.api.models import ChatRequest
        
        req = ChatRequest(message="Test", season="2024")
        assert req.season == "2024"

    def test_chat_req_with_league_id(self):
        """ChatRequest with league_id should work."""
        from src.api.models import ChatRequest
        
        req = ChatRequest(message="Test", league_id="123456")
        assert req.league_id == "123456"

    def test_chat_req_all_fields(self):
        """ChatRequest with all fields should work."""
        from src.api.models import ChatRequest
        
        req = ChatRequest(
            message="Who was unluckiest?",
            season="2023",
            league_id="867850980811821056"
        )
        assert req.message == "Who was unluckiest?"
        assert req.season == "2023"
        assert req.league_id == "867850980811821056"

    def test_chat_req_strips_whitespace(self):
        """ChatRequest should strip whitespace from message."""
        from src.api.models import ChatRequest
        
        req = ChatRequest(message="  Who is luckiest?  ")
        assert req.message == "Who is luckiest?"

    def test_chat_req_validates_season_format(self):
        """ChatRequest should reject invalid season formats."""
        from src.api.models import ChatRequest
        import pydantic
        
        with pytest.raises(pydantic.ValidationError):
            ChatRequest(message="Test", season="invalid")

    def test_chat_req_accepts_all_season(self):
        """ChatRequest should accept 'all' as a valid season."""
        from src.api.models import ChatRequest
        
        req = ChatRequest(message="Test", season="ALL")
        assert req.season == "all"  # Should be normalized to lowercase


class TestHealthEndpoint:
    """Tests for health check endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from app import app
        return TestClient(app)

    def test_health_returns_ok(self, client):
        """GET /health should return status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_ready_checks_database(self, client):
        """GET /health/ready should verify database connectivity."""
        response = client.get("/health/ready")
        # Will be 200 if DB exists, 503 if not
        assert response.status_code in [200, 503]


class TestExceptionHandlers:
    """Tests for custom exception handlers."""

    def test_sleeper_analyzer_error_to_response(self):
        """SleeperAnalyzerError should convert to proper response dict."""
        from src.api.exceptions import SeasonNotFoundError
        
        exc = SeasonNotFoundError(season="2019")
        response = exc.to_response_dict()
        
        assert response["error"] == "season_not_found"
        assert "2019" in response["detail"]
        assert response["context"]["season"] == "2019"

    def test_exception_hierarchy(self):
        """All custom exceptions should inherit from SleeperAnalyzerError."""
        from src.api.exceptions import (
            SleeperAnalyzerError,
            ValidationError,
            SeasonNotFoundError,
            LLMError,
            LLMTimeoutError,
        )
        
        assert issubclass(ValidationError, SleeperAnalyzerError)
        assert issubclass(SeasonNotFoundError, SleeperAnalyzerError)
        assert issubclass(LLMError, SleeperAnalyzerError)
        assert issubclass(LLMTimeoutError, LLMError)

    def test_llm_timeout_error_message(self):
        """LLMTimeoutError should include timeout duration."""
        from src.api.exceptions import LLMTimeoutError
        
        exc = LLMTimeoutError(timeout_seconds=45.0)
        assert "45.0" in exc.detail

