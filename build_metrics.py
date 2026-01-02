import sqlite3
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from src.common.logging import setup_logging
from src.config import settings

log = logging.getLogger(__name__)

DB_PATH = Path(settings.db_path)

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def get_manager_map(conn, league_id, season):
    rows = conn.execute("""
      SELECT r.roster_id, COALESCE(u.display_name, u.username, 'Team ' || r.roster_id)
      FROM rosters r
      LEFT JOIN users u ON r.owner_id = u.user_id
      WHERE r.league_id = ? AND r.season = ?
    """, (league_id, season)).fetchall()
    return {int(rid): name for rid, name in rows}

def load_roster_records(conn, league_id, season):
    rows = conn.execute("""
      SELECT roster_id, settings_json
      FROM rosters
      WHERE league_id = ? AND season = ?
    """, (league_id, season)).fetchall()

    out = {}
    for roster_id, settings_json in rows:
        wins = ties = 0
        if settings_json:
            s = json.loads(settings_json)
            wins = int(s.get("wins", 0) or 0)
            ties = int(s.get("ties", 0) or 0)
        out[int(roster_id)] = wins + 0.5 * ties
    return out

def iter_matchups(conn, league_id, season, week_start=None, week_end=None):
    params = [league_id, season]
    where = "WHERE league_id = ? AND season = ?"
    if week_start is not None:
        where += " AND week >= ?"
        params.append(int(week_start))
    if week_end is not None:
        where += " AND week <= ?"
        params.append(int(week_end))

    rows = conn.execute(f"""
      SELECT week, roster_id, points, starters_json, players_json, data_json
      FROM matchups
      {where}
      ORDER BY week, roster_id
    """, params).fetchall()

    for week, roster_id, points, starters_json, players_json, data_json in rows:
        yield int(week), int(roster_id), (points or 0.0), starters_json, players_json, data_json

def compute_all_play_for_week(entries):
    # entries: [(roster_id, points_for)]
    expected_wins = defaultdict(float)
    games = defaultdict(int)
    for i, (ri, pi) in enumerate(entries):
        for j, (rj, pj) in enumerate(entries):
            if i == j:
                continue
            games[ri] += 1
            if pi > pj:
                expected_wins[ri] += 1
            elif pi == pj:
                expected_wins[ri] += 0.5
    return expected_wins, games

def bench_points_from_json(matchup_data, starters):
    # Tries to compute bench points if player-level points exist
    # Common key: "players_points" or similar map player_id -> points
    pp = matchup_data.get("players_points")
    if not isinstance(pp, dict):
        return None

    starters_set = set(starters or [])
    bench = [pid for pid in pp.keys() if pid not in starters_set]
    total = 0.0
    for pid in bench:
        try:
            total += float(pp.get(pid, 0.0) or 0.0)
        except Exception:
            pass
    return total

def main(league_id: str, season: str, week_start=None, week_end=None):
    start_time = time.perf_counter()
    log.info(
        "Building metrics for league_id=%s season=%s weeks=%s-%s",
        league_id,
        season,
        week_start or "start",
        week_end or "end",
    )
    
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(Path("schema.sql").read_text(encoding="utf-8"))  # ensure metrics tables exist

    # Group matchup rows by week
    by_week = defaultdict(list)
    raw_rows = []
    for week, roster_id, points_for, starters_json, players_json, data_json in iter_matchups(conn, league_id, season, week_start, week_end):
        starters = json.loads(starters_json) if starters_json else []
        matchup_data = json.loads(data_json) if data_json else {}

        bench_pts = bench_points_from_json(matchup_data, starters)
        # If not available, leave NULL for now (we can improve later)
        raw_rows.append((week, roster_id, points_for, bench_pts))
        by_week[week].append((roster_id, points_for))

    # Compute weekly all-play
    weekly_all_play = {}
    for week, entries in by_week.items():
        ap_wins, ap_games = compute_all_play_for_week(entries)
        weekly_all_play[week] = (ap_wins, ap_games)

    # Write metrics_team_week
    now = utc_now()
    week_rows = []
    for week, roster_id, points_for, bench_pts in raw_rows:
        ap_wins, ap_games = weekly_all_play[week]
        week_rows.append((
            league_id, season, week, roster_id,
            float(points_for),
            float(bench_pts) if bench_pts is not None else None,
            float(ap_wins.get(roster_id, 0.0)),
            int(ap_games.get(roster_id, 0)),
            now
        ))

    conn.executemany("""
      INSERT OR REPLACE INTO metrics_team_week
      (league_id, season, week, roster_id, points_for, bench_points, all_play_wins, all_play_games, fetched_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, week_rows)
    conn.commit()

    # Season rollup
    season_rows = conn.execute("""
      SELECT roster_id,
             COUNT(*) as weeks,
             SUM(points_for) as pf,
             SUM(COALESCE(bench_points,0)) as bp,
             SUM(all_play_wins) as apw,
             SUM(all_play_games) as apg
      FROM metrics_team_week
      WHERE league_id = ? AND season = ?
      GROUP BY roster_id
    """, (league_id, season)).fetchall()

    actual = load_roster_records(conn, league_id, season)

    out_rows = []
    for roster_id, weeks, pf, bp, apw, apg in season_rows:
        exp_wins = float(apw or 0.0)
        apg = int(apg or 0)
        exp_pct = (exp_wins / apg) if apg else 0.0
        act = float(actual.get(int(roster_id), 0.0))
        luck = act - exp_wins

        out_rows.append((
            league_id, season, int(roster_id),
            int(weeks or 0),
            float(pf or 0.0),
            float(bp or 0.0),
            float(apw or 0.0),
            int(apg),
            float(exp_wins),
            float(exp_pct),
            float(act),
            float(luck),
            utc_now()
        ))

    conn.executemany("""
      INSERT OR REPLACE INTO metrics_team_season
      (league_id, season, roster_id, weeks_played, points_for, bench_points, all_play_wins, all_play_games, exp_wins, exp_win_pct, actual_wins, luck, computed_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, out_rows)
    conn.commit()

    conn.close()
    elapsed = time.perf_counter() - start_time
    log.info(
        "Completed metrics for league_id=%s season=%s: %d weekly rows, %d season rows (%.2fs)",
        league_id,
        season,
        len(week_rows),
        len(out_rows),
        elapsed,
    )

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--league-id", required=True)
    p.add_argument("--season", required=True)
    p.add_argument("--week-start", type=int)
    p.add_argument("--week-end", type=int)
    p.add_argument("--log-level", default="INFO", help="Logging level")
    args = p.parse_args()
    
    setup_logging(args.log_level)
    main(args.league_id, args.season, args.week_start, args.week_end)
