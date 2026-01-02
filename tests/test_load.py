"""
Load/stress tests for the Sleeper Analyzer API.

These tests verify the system can handle concurrent requests
and measure performance characteristics.

Run with:
    pytest tests/test_load.py -v --tb=short

For actual load testing, consider using Locust:
    locust -f tests/locustfile.py --host=http://localhost:8000
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import src.chat.llm as llm_module


class TestConcurrency:
    """Tests for concurrent request handling."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from app import app
        return TestClient(app)

    @pytest.fixture
    def mock_llm_fast(self):
        """Mock LLM that responds quickly."""
        return {
            "answer": "Quick response",
            "confidence": "high",
            "follow_up_suggestions": None,
        }

    def test_concurrent_health_checks(self, client):
        """Health endpoint should handle many concurrent requests."""
        num_requests = 50
        errors = []
        
        def make_request():
            try:
                response = client.get("/health")
                if response.status_code != 200:
                    errors.append(f"Status {response.status_code}")
            except Exception as e:
                errors.append(str(e))
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            for future in as_completed(futures):
                future.result()
        
        assert len(errors) == 0, f"Errors: {errors[:5]}"

    def test_concurrent_chat_requests(self, client, mock_llm_fast):
        """Chat endpoint should handle concurrent requests."""
        num_requests = 10
        errors = []
        responses = []
        
        def make_request(i):
            try:
                with patch.object(llm_module, "answer") as mock:
                    mock.return_value = mock_llm_fast
                    response = client.post(
                        "/chat",
                        json={"message": f"Test question {i}", "season": "2024"}
                    )
                    if response.status_code == 200:
                        responses.append(response.json())
                    else:
                        errors.append(f"Request {i}: status {response.status_code}")
            except Exception as e:
                errors.append(f"Request {i}: {e}")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]
            for future in as_completed(futures):
                future.result()
        
        # Allow some failures under load, but most should succeed
        success_rate = len(responses) / num_requests
        assert success_rate >= 0.8, f"Success rate {success_rate:.1%}, errors: {errors[:3]}"

    def test_static_file_performance(self, client):
        """Static files should be served quickly."""
        endpoints = ["/", "/static/styles.css", "/static/app.js"]
        
        for endpoint in endpoints:
            start = time.perf_counter()
            response = client.get(endpoint)
            elapsed = time.perf_counter() - start
            
            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
            assert elapsed < 0.5, f"{endpoint} took {elapsed:.2f}s (should be <0.5s)"


class TestPerformance:
    """Performance benchmarks."""

    def test_tool_function_performance(self):
        """Tool functions should complete quickly."""
        from src.chat.tools import get_luck_leaderboard, get_top_players_for_season
        from src.config import settings
        
        league_id = settings.default_leagues.get("2024")
        if not league_id:
            pytest.skip("No 2024 league configured")
        
        # Luck leaderboard should be fast (precomputed)
        start = time.perf_counter()
        get_luck_leaderboard(league_id, "2024")
        luck_time = time.perf_counter() - start
        
        # Top players requires scanning matchups
        start = time.perf_counter()
        get_top_players_for_season("2024", limit=20)
        players_time = time.perf_counter() - start
        
        assert luck_time < 1.0, f"Luck leaderboard took {luck_time:.2f}s"
        assert players_time < 2.0, f"Top players took {players_time:.2f}s"

    def test_response_size_reasonable(self):
        """Tool responses should not be excessively large."""
        from src.chat.tools import get_luck_leaderboard, get_top_players_for_season, get_all_seasons_summary
        from src.config import settings
        import json
        
        league_id = settings.default_leagues.get("2024")
        if not league_id:
            pytest.skip("No 2024 league configured")
        
        responses = [
            ("luck_leaderboard", get_luck_leaderboard(league_id, "2024")),
            ("top_players", get_top_players_for_season("2024", limit=50)),
            ("all_seasons", get_all_seasons_summary()),
        ]
        
        for name, response in responses:
            size = len(json.dumps(response))
            # Responses should be under 100KB to avoid context issues
            assert size < 100_000, f"{name} response is {size/1000:.1f}KB (should be <100KB)"


class TestResiliencePatterns:
    """Tests for resilience patterns."""

    def test_retry_decorator(self):
        """Test retry with backoff works correctly."""
        from src.common.resilience import with_retry, RetryError
        
        call_count = 0
        
        @with_retry(max_attempts=3, backoff_base=0.01)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = flaky_function()
        
        assert result == "success"
        assert call_count == 3

    def test_retry_exhaustion(self):
        """Test retry raises after max attempts."""
        from src.common.resilience import with_retry, RetryError
        
        @with_retry(max_attempts=2, backoff_base=0.01)
        def always_fails():
            raise ValueError("Permanent failure")
        
        with pytest.raises(RetryError) as exc_info:
            always_fails()
        
        assert exc_info.value.attempts == 2

    def test_circuit_breaker_opens(self):
        """Test circuit breaker opens after failures."""
        from src.common.resilience import circuit_breaker, CircuitOpenError, get_circuit
        
        # Use unique circuit name for this test
        circuit_name = f"test_circuit_{time.time()}"
        
        @circuit_breaker(circuit_name, failure_threshold=3, recovery_timeout=0.1)
        def failing_function():
            raise ValueError("Service down")
        
        # Fail 3 times to open circuit
        for _ in range(3):
            try:
                failing_function()
            except ValueError:
                pass
        
        # Next call should be blocked
        with pytest.raises(CircuitOpenError):
            failing_function()

    def test_circuit_breaker_recovers(self):
        """Test circuit breaker recovers after timeout."""
        from src.common.resilience import circuit_breaker, CircuitOpenError, get_circuit
        
        circuit_name = f"test_recovery_{time.time()}"
        call_count = 0
        
        @circuit_breaker(circuit_name, failure_threshold=2, recovery_timeout=0.1)
        def recoverable_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("Temporary failure")
            return "recovered"
        
        # Fail twice to open circuit
        for _ in range(2):
            try:
                recoverable_function()
            except ValueError:
                pass
        
        # Circuit should be open
        with pytest.raises(CircuitOpenError):
            recoverable_function()
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Should be allowed through (half-open)
        result = recoverable_function()
        assert result == "recovered"


class TestObservability:
    """Tests for observability infrastructure."""

    def test_metrics_recording(self):
        """Test metrics are recorded correctly."""
        from src.common.observability import metrics
        
        metrics.reset()
        
        # Record some metrics
        metrics.record_latency("test_op", 100)
        metrics.record_latency("test_op", 200)
        metrics.record_error("test_error")
        metrics.record_tool_call("test_tool")
        
        stats = metrics.get_stats()
        
        assert "test_op" in stats["latencies"]
        assert stats["latencies"]["test_op"]["count"] == 2
        assert stats["errors"]["test_error"] == 1
        assert stats["tool_calls"]["test_tool"] == 1

    def test_request_context(self):
        """Test request context provides correlated logging."""
        from src.common.observability import get_request_context, current_context
        
        with get_request_context(test_key="test_value") as ctx:
            assert ctx.request_id is not None
            assert len(ctx.request_id) == 8
            assert ctx.metadata["test_key"] == "test_value"
            assert current_context() is ctx
            
            # Should be able to log
            ctx.log.info("Test message")
        
        # Context should be cleared outside
        assert current_context() is None

    def test_timed_operation(self):
        """Test timed operation records metrics."""
        from src.common.observability import timed_operation, metrics
        
        metrics.reset()
        
        with timed_operation("test_timed"):
            time.sleep(0.01)
        
        stats = metrics.get_stats()
        assert "test_timed" in stats["latencies"]
        assert stats["latencies"]["test_timed"]["count"] == 1
        assert stats["latencies"]["test_timed"]["avg_ms"] >= 10
