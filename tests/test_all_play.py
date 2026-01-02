"""Unit tests for the all-play computation logic."""
import pytest
from build_metrics import compute_all_play_for_week


class TestComputeAllPlayForWeek:
    """Tests for compute_all_play_for_week function."""

    def test_basic_three_team_week(self):
        """Three teams: 100, 90, 80 points. Each plays 2 games."""
        entries = [
            (1, 100.0),
            (2, 90.0),
            (3, 80.0),
        ]
        exp_wins, games = compute_all_play_for_week(entries)

        # Team 1 (100 pts): beats 90 and 80 -> 2 wins
        assert exp_wins[1] == 2.0
        # Team 2 (90 pts): beats 80, loses to 100 -> 1 win
        assert exp_wins[2] == 1.0
        # Team 3 (80 pts): loses to both -> 0 wins
        assert exp_wins[3] == 0.0

        # Each team plays 2 games (N-1 where N=3)
        assert games[1] == 2
        assert games[2] == 2
        assert games[3] == 2

    def test_tie_handling(self):
        """Two teams with same score should each get 0.5 wins."""
        entries = [
            (1, 100.0),
            (2, 100.0),
            (3, 80.0),
        ]
        exp_wins, games = compute_all_play_for_week(entries)

        # Team 1 (100 pts): ties with 100, beats 80 -> 1.5 wins
        assert exp_wins[1] == 1.5
        # Team 2 (100 pts): ties with 100, beats 80 -> 1.5 wins
        assert exp_wins[2] == 1.5
        # Team 3 (80 pts): loses to both -> 0 wins
        assert exp_wins[3] == 0.0

    def test_all_tied(self):
        """All teams with same score: everyone gets 0.5 per game."""
        entries = [
            (1, 100.0),
            (2, 100.0),
            (3, 100.0),
        ]
        exp_wins, games = compute_all_play_for_week(entries)

        # Each team ties with the other 2 -> 1.0 wins each
        assert exp_wins[1] == 1.0
        assert exp_wins[2] == 1.0
        assert exp_wins[3] == 1.0

    def test_single_team(self):
        """Edge case: only one team (no games)."""
        entries = [(1, 100.0)]
        exp_wins, games = compute_all_play_for_week(entries)

        assert exp_wins[1] == 0.0
        assert games[1] == 0

    def test_empty_entries(self):
        """Edge case: no teams at all."""
        entries = []
        exp_wins, games = compute_all_play_for_week(entries)

        assert len(exp_wins) == 0
        assert len(games) == 0

    def test_larger_league(self):
        """Ten-team league: verify total wins equals N*(N-1)/2 (45 total games)."""
        entries = [
            (1, 150.0),
            (2, 140.0),
            (3, 130.0),
            (4, 120.0),
            (5, 110.0),
            (6, 100.0),
            (7, 90.0),
            (8, 80.0),
            (9, 70.0),
            (10, 60.0),
        ]
        exp_wins, games = compute_all_play_for_week(entries)

        # Total wins should equal total games (45 = 10*9/2)
        total_wins = sum(exp_wins.values())
        assert total_wins == 45.0

        # Each team plays 9 games
        for team_id in range(1, 11):
            assert games[team_id] == 9

        # Team 1 wins all 9, Team 10 wins 0
        assert exp_wins[1] == 9.0
        assert exp_wins[10] == 0.0

    def test_fractional_points(self):
        """Handle fractional point totals correctly."""
        entries = [
            (1, 100.5),
            (2, 100.4),
            (3, 100.3),
        ]
        exp_wins, games = compute_all_play_for_week(entries)

        assert exp_wins[1] == 2.0
        assert exp_wins[2] == 1.0
        assert exp_wins[3] == 0.0
