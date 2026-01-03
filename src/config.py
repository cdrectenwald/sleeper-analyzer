import os
from pathlib import Path


class Settings:
    """Application configuration loaded from environment variables."""
    
    def __init__(self):
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.db_path: str = os.getenv("DB_PATH", "db/sleeper.sqlite")
        self.default_season: str = os.getenv("DEFAULT_SEASON", "2025")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

        self.default_leagues: dict[str, str] = {
            "2025": "1257104404557856768",
            "2024": "1124856081965645824",
            "2023": "916867273804288000",
            "2022": "867850980811821056",
        }

        self._load_dotenv()
    
    def _load_dotenv(self):
        """Load environment variables from .env file if present."""
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key == "OPENAI_API_KEY":
                        self.openai_api_key = value
                    elif key == "DB_PATH":
                        self.db_path = value
                    elif key == "DEFAULT_SEASON":
                        self.default_season = value
                    elif key == "LOG_LEVEL":
                        self.log_level = value


settings = Settings()
