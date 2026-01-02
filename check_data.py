#!/usr/bin/env python
"""
Data health check script.

Run after ingestion to verify data integrity:
  python check_data.py

Checks:
  - Weeks are contiguous where expected
  - metrics_team_week rows exist for each (league_id, season, week)
  - metrics_team_season exists for every roster
  - Rosters and users are populated
"""
import sqlite3
import argparse
import logging
from pathlib import Path

from src.common.logging import setup_logging
from src.config import settings

log = logging.getLogger(__name__)


def check_league_data(conn: sqlite3.Connection, league_id: str, season: str) -> list[str]:
    """Check data health for a specific league/season. Returns list of warnings."""
    warnings = []

    # Check matchups exist and are contiguous
    matchup_weeks = conn.execute(
        "SELECT DISTINCT week FROM matchups WHERE league_id = ? AND season = ? ORDER BY week",
        (league_id, season),
    ).fetchall()
    matchup_weeks = [w[0] for w in matchup_weeks]

    if not matchup_weeks:
        warnings.append(f"League {league_id} season {season}: No matchups found")
    else:
        # Check for gaps in weeks
        expected_weeks = list(range(1, max(matchup_weeks) + 1))
        missing_weeks = set(expected_weeks) - set(matchup_weeks)
        if missing_weeks:
            warnings.append(
                f"League {league_id} season {season}: Missing matchups for weeks {sorted(missing_weeks)}"
            )

    # Check metrics_team_week
    metric_weeks = conn.execute(
        "SELECT DISTINCT week FROM metrics_team_week WHERE league_id = ? AND season = ? ORDER BY week",
        (league_id, season),
    ).fetchall()
    metric_weeks = [w[0] for w in metric_weeks]

    if matchup_weeks and not metric_weeks:
        warnings.append(
            f"League {league_id} season {season}: Matchups exist but metrics not built yet. Run build_metrics.py"
        )
    elif matchup_weeks and metric_weeks:
        missing_metric_weeks = set(matchup_weeks) - set(metric_weeks)
        if missing_metric_weeks:
            warnings.append(
                f"League {league_id} season {season}: Missing metrics for weeks {sorted(missing_metric_weeks)}"
            )

    # Check rosters
    roster_count = conn.execute(
        "SELECT COUNT(*) FROM rosters WHERE league_id = ? AND season = ?",
        (league_id, season),
    ).fetchone()[0]

    if roster_count == 0:
        warnings.append(f"League {league_id} season {season}: No rosters found")

    # Check metrics_team_season
    season_metric_count = conn.execute(
        "SELECT COUNT(*) FROM metrics_team_season WHERE league_id = ? AND season = ?",
        (league_id, season),
    ).fetchone()[0]

    if roster_count > 0 and season_metric_count == 0:
        warnings.append(
            f"League {league_id} season {season}: {roster_count} rosters but no season metrics. Run build_metrics.py"
        )
    elif roster_count > 0 and season_metric_count < roster_count:
        warnings.append(
            f"League {league_id} season {season}: Only {season_metric_count}/{roster_count} rosters have season metrics"
        )

    # Check users
    user_count = conn.execute(
        "SELECT COUNT(*) FROM users WHERE league_id = ?",
        (league_id,),
    ).fetchone()[0]

    if user_count == 0:
        warnings.append(f"League {league_id}: No users found")

    return warnings


def main():
    parser = argparse.ArgumentParser(description="Check data health after ingestion")
    parser.add_argument("--db-path", default=settings.db_path, help="Path to SQLite database")
    parser.add_argument("--league-id", help="Check specific league (optional)")
    parser.add_argument("--season", help="Check specific season (optional)")
    args = parser.parse_args()

    setup_logging(settings.log_level)

    db_path = Path(args.db_path)
    if not db_path.exists():
        log.error("Database not found at %s", db_path)
        log.info("Run fetch_all.py first to ingest data")
        return

    conn = sqlite3.connect(db_path)

    # Get all league/season combinations
    if args.league_id and args.season:
        leagues_seasons = [(args.league_id, args.season)]
    elif args.league_id:
        rows = conn.execute(
            "SELECT DISTINCT league_id, season FROM rosters WHERE league_id = ?",
            (args.league_id,),
        ).fetchall()
        leagues_seasons = [(r[0], r[1]) for r in rows]
    else:
        rows = conn.execute(
            "SELECT DISTINCT league_id, season FROM rosters ORDER BY season DESC, league_id"
        ).fetchall()
        leagues_seasons = [(r[0], r[1]) for r in rows]

    if not leagues_seasons:
        log.warning("No league/season data found in database")
        conn.close()
        return

    log.info("Checking %d league/season combinations...", len(leagues_seasons))

    all_warnings = []
    for league_id, season in leagues_seasons:
        log.info("Checking league=%s season=%s", league_id, season)
        warnings = check_league_data(conn, league_id, season)
        all_warnings.extend(warnings)

    conn.close()

    # Summary
    print("\n" + "=" * 60)
    if all_warnings:
        print(f"HEALTH CHECK: {len(all_warnings)} warning(s) found\n")
        for w in all_warnings:
            print(f"  ⚠️  {w}")
    else:
        print("HEALTH CHECK: All data looks good! ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
