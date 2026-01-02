"""Integration tests for metrics rollup using in-memory SQLite."""
import sqlite3
import json
import pytest
from pathlib import Path


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database with schema."""
    conn = sqlite3.connect(":memory:")
    schema_path = Path(__file__).parent.parent / "schema.sql"
    if schema_path.exists():
        conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


@pytest.fixture
def sample_matchups():
    """Sample matchup data for testing."""
    return [
        # Week 1: Team 1 (120) vs Team 2 (100), Team 3 (90) vs Team 4 (80)
        {"week": 1, "matchup_id": 1, "roster_id": 1, "points": 120.0},
        {"week": 1, "matchup_id": 1, "roster_id": 2, "points": 100.0},
        {"week": 1, "matchup_id": 2, "roster_id": 3, "points": 90.0},
        {"week": 1, "matchup_id": 2, "roster_id": 4, "points": 80.0},
        # Week 2: Team 1 (110) vs Team 3 (115), Team 2 (95) vs Team 4 (85)
        {"week": 2, "matchup_id": 1, "roster_id": 1, "points": 110.0},
        {"week": 2, "matchup_id": 1, "roster_id": 3, "points": 115.0},
        {"week": 2, "matchup_id": 2, "roster_id": 2, "points": 95.0},
        {"week": 2, "matchup_id": 2, "roster_id": 4, "points": 85.0},
    ]


class TestMetricsRollup:
    """Tests for metrics computation and rollup."""

    def test_insert_matchups(self, in_memory_db, sample_matchups):
        """Verify we can insert and retrieve matchups."""
        conn = in_memory_db
        league_id = "test_league"
        season = "2024"

        for m in sample_matchups:
            conn.execute(
                """
                INSERT INTO matchups 
                (league_id, season, week, roster_id, points, starters_json, players_json, data_json, fetched_at)
                VALUES (?, ?, ?, ?, ?, '[]', '[]', ?, datetime('now'))
                """,
                (league_id, season, m["week"], m["roster_id"], m["points"], 
                 json.dumps({"matchup_id": m["matchup_id"]})),
            )
        conn.commit()

        # Verify insertion
        count = conn.execute("SELECT COUNT(*) FROM matchups").fetchone()[0]
        assert count == 8

    def test_weekly_all_play_calculation(self, in_memory_db, sample_matchups):
        """Test all-play wins calculation for a single week."""
        # Week 1 scores: 120, 100, 90, 80
        # All-play wins: 
        #   Team 1 (120): beats all 3 -> 3 wins
        #   Team 2 (100): beats 90, 80 -> 2 wins  
        #   Team 3 (90): beats 80 -> 1 win
        #   Team 4 (80): beats none -> 0 wins
        from build_metrics import compute_all_play_for_week

        week1_entries = [
            (1, 120.0),
            (2, 100.0),
            (3, 90.0),
            (4, 80.0),
        ]
        exp_wins, games = compute_all_play_for_week(week1_entries)

        assert exp_wins[1] == 3.0
        assert exp_wins[2] == 2.0
        assert exp_wins[3] == 1.0
        assert exp_wins[4] == 0.0

    def test_season_totals(self, in_memory_db, sample_matchups):
        """Test season-level aggregation of all-play wins."""
        from build_metrics import compute_all_play_for_week

        # Week 1: 120, 100, 90, 80 -> wins: 3, 2, 1, 0
        week1 = [(1, 120.0), (2, 100.0), (3, 90.0), (4, 80.0)]
        exp1, _ = compute_all_play_for_week(week1)

        # Week 2: 110, 95, 115, 85 -> wins: 2, 1, 3, 0
        week2 = [(1, 110.0), (2, 95.0), (3, 115.0), (4, 85.0)]
        exp2, _ = compute_all_play_for_week(week2)

        # Season totals
        season_wins = {
            1: exp1[1] + exp2[1],  # 3 + 2 = 5
            2: exp1[2] + exp2[2],  # 2 + 1 = 3
            3: exp1[3] + exp2[3],  # 1 + 3 = 4
            4: exp1[4] + exp2[4],  # 0 + 0 = 0
        }

        assert season_wins[1] == 5.0
        assert season_wins[2] == 3.0
        assert season_wins[3] == 4.0
        assert season_wins[4] == 0.0

    def test_luck_calculation(self):
        """Test luck = actual_wins - expected_wins."""
        # Team with 8 actual wins but only 5 expected wins -> luck = +3
        actual_wins = 8.0
        expected_wins = 5.0
        luck = actual_wins - expected_wins
        assert luck == 3.0

        # Team with 3 actual wins but 6 expected wins -> luck = -3
        actual_wins = 3.0
        expected_wins = 6.0
        luck = actual_wins - expected_wins
        assert luck == -3.0

    def test_expected_win_percentage(self):
        """Test expected win percentage calculation."""
        all_play_wins = 42.0
        all_play_games = 126  # 14 weeks * 9 opponents

        exp_win_pct = all_play_wins / all_play_games
        assert abs(exp_win_pct - 0.333) < 0.01
