"""
Locust load testing file for Sleeper Analyzer.

Run with:
    locust -f tests/locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 to configure and run tests.

For headless mode:
    locust -f tests/locustfile.py --host=http://localhost:8000 \
           --users 10 --spawn-rate 2 --run-time 1m --headless
"""

from locust import HttpUser, task, between


class SleeperAnalyzerUser(HttpUser):
    """Simulated user for load testing."""
    
    # Wait 1-3 seconds between requests
    wait_time = between(1, 3)
    
    @task(10)
    def health_check(self):
        """High-frequency health check."""
        self.client.get("/health")
    
    @task(3)
    def view_homepage(self):
        """Load the main page."""
        self.client.get("/")
    
    @task(2)
    def view_glossary(self):
        """Load the glossary page."""
        self.client.get("/glossary")
    
    @task(1)
    def load_static_assets(self):
        """Load CSS and JS."""
        self.client.get("/static/styles.css")
        self.client.get("/static/app.js")
    
    @task(5)
    def chat_luck_question(self):
        """Ask about luck (most common query type)."""
        self.client.post(
            "/chat",
            json={
                "message": "Who was the luckiest manager this season?",
                "season": "2024",
            },
        )
    
    @task(3)
    def chat_player_question(self):
        """Ask about player performance."""
        self.client.post(
            "/chat",
            json={
                "message": "Who were the top scoring players?",
                "season": "2024",
            },
        )
    
    @task(2)
    def chat_alltime_question(self):
        """Ask about all-time stats."""
        self.client.post(
            "/chat",
            json={
                "message": "Who is the luckiest manager all-time?",
                "season": "all",
            },
        )
    
    @task(2)
    def chat_with_history(self):
        """Chat with conversation history."""
        self.client.post(
            "/chat",
            json={
                "message": "Tell me more about their performance",
                "season": "2024",
                "history": [
                    {"role": "user", "content": "Who was luckiest?"},
                    {"role": "assistant", "content": "Team A was luckiest with +3.2."},
                ],
            },
        )


class HealthCheckUser(HttpUser):
    """User that only checks health (for monitoring simulation)."""
    
    wait_time = between(5, 10)
    weight = 1  # Low weight, fewer of these users
    
    @task
    def health_ready(self):
        """Readiness check (includes DB check)."""
        self.client.get("/health/ready")
