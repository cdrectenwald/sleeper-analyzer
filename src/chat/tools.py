import json
import logging
import sqlite3
import time
from pathlib import Path
from collections import defaultdict

from src.config import settings

log = logging.getLogger(__name__)

DB_PATH = Path(settings.db_path)


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def get_luck_for_range(league_id: str, season: str, week_start: int, week_end: int) -> dict:
    """
    Slice-based luck:
      expected = all-play wins in range
      actual   = head-to-head wins in range (derived from matchups)
      luck     = actual - expected
    """
    start = time.perf_counter()
    log.info(
        "get_luck_for_range: league_id=%s season=%s weeks=%d-%d",
        league_id, season, week_start, week_end
    )
    conn = _conn()

    # Expected (all-play) from metrics_team_week
    exp_rows = conn.execute(
        """
        SELECT roster_id,
               SUM(all_play_wins) AS exp_wins,
               SUM(all_play_games) AS ap_games,
               SUM(points_for) AS points_for,
               SUM(COALESCE(bench_points,0)) AS bench_points
        FROM metrics_team_week
        WHERE league_id = ?
          AND season = ?
          AND week BETWEEN ? AND ?
        GROUP BY roster_id
        """,
        (league_id, season, week_start, week_end),
    ).fetchall()

    expected = {}
    for roster_id, exp_wins, ap_games, pf, bp in exp_rows:
        roster_id = int(roster_id)
        ap_games = int(ap_games or 0)
        exp_wins = float(exp_wins or 0.0)
        expected[roster_id] = {
            "expected_wins": exp_wins,
            "all_play_games": ap_games,
            "expected_win_pct": (exp_wins / ap_games) if ap_games else 0.0,
            "points_for": float(pf or 0.0),
            "bench_points": float(bp or 0.0),
        }

    # Actual (head-to-head) computed from raw matchups table
    # Note: matchup_id is stored in data_json, not as a column
    mrows = conn.execute(
        """
        SELECT week, roster_id, points, data_json
        FROM matchups
        WHERE league_id = ?
          AND season = ?
          AND week BETWEEN ? AND ?
        ORDER BY week, roster_id
        """,
        (league_id, season, week_start, week_end),
    ).fetchall()

    by_game = defaultdict(list)  # (week, matchup_id) -> [(roster_id, points)]
    for week, roster_id, points, data_json in mrows:
        # Extract matchup_id from data_json
        matchup_id = None
        if data_json:
            try:
                data = json.loads(data_json)
                matchup_id = data.get("matchup_id")
            except (json.JSONDecodeError, TypeError):
                pass
        if matchup_id is None:
            continue
        by_game[(int(week), int(matchup_id))].append((int(roster_id), float(points or 0.0)))

    actual_wins = defaultdict(float)
    actual_games = defaultdict(int)

    for (_week, _mid), teams in by_game.items():
        # Typical is 2 teams; handle oddities defensively.
        if len(teams) < 2:
            continue
        teams_sorted = sorted(teams, key=lambda x: x[1], reverse=True)
        top_score = teams_sorted[0][1]
        winners = [rid for rid, pts in teams_sorted if pts == top_score]

        for rid, _pts in teams:
            actual_games[rid] += 1

        if len(winners) == 1:
            actual_wins[winners[0]] += 1.0
        else:
            # tie among top
            for rid in winners:
                actual_wins[rid] += 0.5

    # Attach names (optional but nice)
    name_rows = conn.execute(
        """
        SELECT r.roster_id, COALESCE(u.display_name, u.username, 'Team ' || r.roster_id)
        FROM rosters r
        LEFT JOIN users u ON r.owner_id = u.user_id
        WHERE r.league_id = ? AND r.season = ?
        """,
        (league_id, season),
    ).fetchall()
    names = {int(rid): name for rid, name in name_rows}

    # Merge
    roster_ids = sorted(set(expected.keys()) | set(actual_games.keys()))
    out = []
    for rid in roster_ids:
        exp = expected.get(rid, {})
        act_w = float(actual_wins.get(rid, 0.0))
        act_g = int(actual_games.get(rid, 0))
        exp_w = float(exp.get("expected_wins", 0.0))
        out.append(
            {
                "roster_id": rid,
                "name": names.get(rid, f"Team {rid}"),
                "actual_wins": act_w,
                "actual_games": act_g,
                "expected_wins": exp_w,
                "luck": act_w - exp_w,
                "expected_win_pct": float(exp.get("expected_win_pct", 0.0)),
                "points_for": float(exp.get("points_for", 0.0)),
                "bench_points": float(exp.get("bench_points", 0.0)),
            }
        )

    conn.close()
    out.sort(key=lambda r: r["luck"], reverse=True)

    elapsed = time.perf_counter() - start
    log.info("get_luck_for_range completed in %.3fs, returned %d teams", elapsed, len(out))

    return {
        "league_id": league_id,
        "season": season,
        "week_start": week_start,
        "week_end": week_end,
        "teams": out,
    }


def get_luck_leaderboard(league_id: str, season: str) -> dict:
    start = time.perf_counter()
    log.info("get_luck_leaderboard: league_id=%s season=%s", league_id, season)
    conn = _conn()

    rows = conn.execute(
        """
        SELECT roster_id, exp_wins, actual_wins, luck, exp_win_pct, points_for, bench_points
        FROM metrics_team_season
        WHERE league_id = ? AND season = ?
        ORDER BY luck DESC
        """,
        (league_id, season),
    ).fetchall()

    name_rows = conn.execute(
        """
        SELECT r.roster_id, COALESCE(u.display_name, u.username, 'Team ' || r.roster_id)
        FROM rosters r
        LEFT JOIN users u ON r.owner_id = u.user_id
        WHERE r.league_id = ? AND r.season = ?
        """,
        (league_id, season),
    ).fetchall()
    names = {int(rid): name for rid, name in name_rows}

    conn.close()

    teams = []
    for rid, exp_w, act_w, luck, exp_pct, pf, bp in rows:
        rid = int(rid)
        teams.append(
            {
                "roster_id": rid,
                "name": names.get(rid, f"Team {rid}"),
                "expected_wins": float(exp_w or 0.0),
                "actual_wins": float(act_w or 0.0),
                "luck": float(luck or 0.0),
                "expected_win_pct": float(exp_pct or 0.0),
                "points_for": float(pf or 0.0),
                "bench_points": float(bp or 0.0),
            }
        )

    elapsed = time.perf_counter() - start
    log.info("get_luck_leaderboard completed in %.3fs, returned %d teams", elapsed, len(teams))

    return {"league_id": league_id, "season": season, "teams": teams}


def get_all_seasons_summary() -> dict:
    """
    Get luck and performance summary across ALL seasons for the same manager names.
    Aggregates stats by display_name across all leagues/seasons.
    """
    start = time.perf_counter()
    log.info("get_all_seasons_summary: fetching cross-season data")
    conn = _conn()

    # Get all season metrics with manager names
    rows = conn.execute(
        """
        SELECT 
            m.league_id,
            m.season,
            m.roster_id,
            COALESCE(u.display_name, u.username, 'Team ' || m.roster_id) as manager_name,
            m.exp_wins,
            m.actual_wins,
            m.luck,
            m.points_for,
            m.weeks_played
        FROM metrics_team_season m
        JOIN rosters r ON m.league_id = r.league_id 
            AND m.season = r.season 
            AND m.roster_id = r.roster_id
        LEFT JOIN users u ON r.owner_id = u.user_id
        ORDER BY m.season DESC, m.luck DESC
        """
    ).fetchall()

    # Aggregate by manager name
    manager_stats = defaultdict(lambda: {
        "seasons": [],
        "total_exp_wins": 0.0,
        "total_actual_wins": 0.0,
        "total_luck": 0.0,
        "total_points": 0.0,
        "total_weeks": 0,
    })

    for league_id, season, roster_id, name, exp_w, act_w, luck, pf, weeks in rows:
        stats = manager_stats[name]
        stats["seasons"].append({
            "season": season,
            "league_id": league_id,
            "exp_wins": float(exp_w or 0),
            "actual_wins": float(act_w or 0),
            "luck": float(luck or 0),
            "points_for": float(pf or 0),
        })
        stats["total_exp_wins"] += float(exp_w or 0)
        stats["total_actual_wins"] += float(act_w or 0)
        stats["total_luck"] += float(luck or 0)
        stats["total_points"] += float(pf or 0)
        stats["total_weeks"] += int(weeks or 0)

    conn.close()

    # Convert to list sorted by total luck
    managers = []
    for name, stats in manager_stats.items():
        managers.append({
            "name": name,
            "seasons_played": len(stats["seasons"]),
            "season_details": stats["seasons"],
            "total_expected_wins": round(stats["total_exp_wins"], 2),
            "total_actual_wins": round(stats["total_actual_wins"], 2),
            "total_luck": round(stats["total_luck"], 2),
            "total_points": round(stats["total_points"], 1),
            "avg_luck_per_season": round(stats["total_luck"] / len(stats["seasons"]), 2) if stats["seasons"] else 0,
        })

    managers.sort(key=lambda x: x["total_luck"], reverse=True)

    elapsed = time.perf_counter() - start
    log.info("get_all_seasons_summary completed in %.3fs, returned %d managers", elapsed, len(managers))

    return {
        "description": "All-time stats aggregated by manager across all seasons",
        "managers": managers,
    }


def _get_player_names() -> dict[str, str]:
    """Load player ID -> name mapping from players_dump if available."""
    conn = _conn()
    row = conn.execute(
        "SELECT data_json FROM players_dump WHERE sport = 'nfl'"
    ).fetchone()
    conn.close()
    
    if not row:
        return {}
    
    try:
        players = json.loads(row[0])
        return {
            pid: p.get("full_name") or p.get("first_name", "") + " " + p.get("last_name", "")
            for pid, p in players.items()
            if isinstance(p, dict)
        }
    except (json.JSONDecodeError, TypeError):
        return {}


def get_top_players_for_season(season: str, limit: int = 20) -> dict:
    """
    Get the top scoring players across all rosters for a given season.
    Aggregates player points from all matchups.
    """
    start = time.perf_counter()
    log.info("get_top_players_for_season: season=%s limit=%d", season, limit)
    
    conn = _conn()
    
    # Get the league_id for this season
    league_id = settings.default_leagues.get(season)
    if not league_id:
        conn.close()
        return {"error": f"No league configured for season {season}"}
    
    # Get all matchups with player points
    rows = conn.execute(
        """
        SELECT data_json
        FROM matchups
        WHERE league_id = ? AND season = ?
        """,
        (league_id, season),
    ).fetchall()
    
    conn.close()
    
    # Aggregate player points
    player_totals = defaultdict(lambda: {"points": 0.0, "games": 0})
    
    for (data_json,) in rows:
        if not data_json:
            continue
        try:
            data = json.loads(data_json)
            players_points = data.get("players_points", {})
            for player_id, points in players_points.items():
                if points and isinstance(points, (int, float)):
                    player_totals[player_id]["points"] += float(points)
                    player_totals[player_id]["games"] += 1
        except (json.JSONDecodeError, TypeError):
            continue
    
    # Get player names
    player_names = _get_player_names()
    
    # Sort by total points
    sorted_players = sorted(
        player_totals.items(),
        key=lambda x: x[1]["points"],
        reverse=True
    )[:limit]
    
    result = []
    for player_id, stats in sorted_players:
        name = player_names.get(player_id, f"Player {player_id}")
        result.append({
            "player_id": player_id,
            "name": name,
            "total_points": round(stats["points"], 2),
            "games_played": stats["games"],
            "avg_points": round(stats["points"] / stats["games"], 2) if stats["games"] else 0,
        })
    
    elapsed = time.perf_counter() - start
    log.info("get_top_players_for_season completed in %.3fs", elapsed)
    
    return {
        "season": season,
        "top_players": result,
    }


def get_player_weekly_scores(season: str, player_name: str) -> dict:
    """
    Get week-by-week scores for a specific player in a season.
    Searches by partial name match.
    """
    start = time.perf_counter()
    log.info("get_player_weekly_scores: season=%s player=%s", season, player_name)
    
    conn = _conn()
    
    league_id = settings.default_leagues.get(season)
    if not league_id:
        conn.close()
        return {"error": f"No league configured for season {season}"}
    
    # Get player names to find the player ID
    player_names = _get_player_names()
    
    # Find matching player IDs (case-insensitive partial match)
    search_lower = player_name.lower()
    matching_ids = [
        pid for pid, name in player_names.items()
        if search_lower in name.lower()
    ]
    
    if not matching_ids:
        conn.close()
        return {
            "error": f"No player found matching '{player_name}'",
            "suggestion": "Try a different spelling or just the last name",
        }
    
    # Get matchups
    rows = conn.execute(
        """
        SELECT week, roster_id, data_json
        FROM matchups
        WHERE league_id = ? AND season = ?
        ORDER BY week
        """,
        (league_id, season),
    ).fetchall()
    
    # Get roster -> manager name mapping
    name_rows = conn.execute(
        """
        SELECT r.roster_id, COALESCE(u.display_name, u.username, 'Team ' || r.roster_id)
        FROM rosters r
        LEFT JOIN users u ON r.owner_id = u.user_id
        WHERE r.league_id = ? AND r.season = ?
        """,
        (league_id, season),
    ).fetchall()
    manager_names = {int(rid): name for rid, name in name_rows}
    
    conn.close()
    
    # Find scores for matching players
    weekly_scores = defaultdict(list)
    
    for week, roster_id, data_json in rows:
        if not data_json:
            continue
        try:
            data = json.loads(data_json)
            players_points = data.get("players_points", {})
            starters = set(data.get("starters", []))
            
            for pid in matching_ids:
                if pid in players_points:
                    points = players_points[pid]
                    if points is not None:
                        weekly_scores[pid].append({
                            "week": week,
                            "points": float(points),
                            "started": pid in starters,
                            "manager": manager_names.get(int(roster_id), f"Team {roster_id}"),
                        })
        except (json.JSONDecodeError, TypeError):
            continue
    
    # Build results
    results = []
    for pid, scores in weekly_scores.items():
        name = player_names.get(pid, f"Player {pid}")
        total = sum(s["points"] for s in scores)
        results.append({
            "player_id": pid,
            "name": name,
            "total_points": round(total, 2),
            "weeks": sorted(scores, key=lambda x: x["week"]),
        })
    
    elapsed = time.perf_counter() - start
    log.info("get_player_weekly_scores completed in %.3fs", elapsed)
    
    return {
        "season": season,
        "search_term": player_name,
        "players_found": results,
    }


def get_manager_roster_history(manager_name: str, season: str) -> dict:
    """
    Get the roster and performance for a specific manager in a season.
    """
    start = time.perf_counter()
    log.info("get_manager_roster_history: manager=%s season=%s", manager_name, season)
    
    conn = _conn()
    
    league_id = settings.default_leagues.get(season)
    if not league_id:
        conn.close()
        return {"error": f"No league configured for season {season}"}
    
    # Find the roster_id for this manager
    name_rows = conn.execute(
        """
        SELECT r.roster_id, COALESCE(u.display_name, u.username, 'Team ' || r.roster_id) as name
        FROM rosters r
        LEFT JOIN users u ON r.owner_id = u.user_id
        WHERE r.league_id = ? AND r.season = ?
        """,
        (league_id, season),
    ).fetchall()
    
    search_lower = manager_name.lower()
    matching = [(rid, name) for rid, name in name_rows if search_lower in name.lower()]
    
    if not matching:
        conn.close()
        available = [name for _, name in name_rows]
        return {
            "error": f"No manager found matching '{manager_name}'",
            "available_managers": available,
        }
    
    roster_id, actual_name = matching[0]
    
    # Get season metrics
    metrics = conn.execute(
        """
        SELECT exp_wins, actual_wins, luck, points_for, weeks_played, exp_win_pct
        FROM metrics_team_season
        WHERE league_id = ? AND season = ? AND roster_id = ?
        """,
        (league_id, season, roster_id),
    ).fetchone()
    
    # Get weekly performance
    weeks = conn.execute(
        """
        SELECT week, points_for, all_play_wins, all_play_games
        FROM metrics_team_week
        WHERE league_id = ? AND season = ? AND roster_id = ?
        ORDER BY week
        """,
        (league_id, season, roster_id),
    ).fetchall()
    
    conn.close()
    
    weekly_data = [
        {
            "week": w,
            "points": round(pf, 2) if pf else 0,
            "all_play_wins": round(apw, 1) if apw else 0,
            "all_play_games": apg or 0,
        }
        for w, pf, apw, apg in weeks
    ]
    
    result = {
        "manager": actual_name,
        "season": season,
        "summary": {},
        "weekly": weekly_data,
    }
    
    if metrics:
        exp_w, act_w, luck, pf, weeks_played, exp_pct = metrics
        result["summary"] = {
            "expected_wins": round(float(exp_w or 0), 2),
            "actual_wins": float(act_w or 0),
            "luck": round(float(luck or 0), 2),
            "total_points": round(float(pf or 0), 1),
            "weeks_played": int(weeks_played or 0),
            "expected_win_pct": round(float(exp_pct or 0) * 100, 1),
        }
    
    elapsed = time.perf_counter() - start
    log.info("get_manager_roster_history completed in %.3fs", elapsed)
    
    return result
