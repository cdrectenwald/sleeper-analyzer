import sqlite3
import json
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("data/processed/sleeper.sqlite")


def detect_default_season(conn: sqlite3.Connection) -> str:
    rows = conn.execute("SELECT DISTINCT season FROM matchups ORDER BY season").fetchall()
    if rows:
        return str(rows[-1][0])

    rows = conn.execute("SELECT DISTINCT season FROM rosters ORDER BY season").fetchall()
    if rows:
        return str(rows[-1][0])

    rows = conn.execute("SELECT DISTINCT season FROM leagues ORDER BY season").fetchall()
    if rows and rows[0][0] is not None:
        return str(rows[-1][0])

    raise RuntimeError("Could not detect a season in the database.")


def detect_week_range(conn: sqlite3.Connection, season: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT MIN(week), MAX(week) FROM matchups WHERE season = ?",
        (season,),
    ).fetchone()
    if not row or row[0] is None:
        raise RuntimeError(f"No matchups found for season={season}.")
    return int(row[0]), int(row[1])


def load_points(conn: sqlite3.Connection, season: str, week_start: int, week_end: int):
    sql = """
        SELECT week, roster_id, points
        FROM matchups
        WHERE season = ?
          AND week >= ?
          AND week <= ?
        ORDER BY week, roster_id
    """
    rows = conn.execute(sql, (season, week_start, week_end)).fetchall()

    weeks = defaultdict(list)
    for week, roster_id, points in rows:
        if points is None:
            points = 0.0
        weeks[int(week)].append((int(roster_id), float(points)))
    return weeks


def load_records(conn: sqlite3.Connection, season: str):
    rows = conn.execute("""
        SELECT roster_id, settings_json
        FROM rosters
        WHERE season = ?
    """, (season,)).fetchall()

    record = {}
    for roster_id, settings_json in rows:
        wins = losses = ties = 0
        if settings_json:
            try:
                settings = json.loads(settings_json)
                wins = int(settings.get("wins", 0) or 0)
                losses = int(settings.get("losses", 0) or 0)
                ties = int(settings.get("ties", 0) or 0)
            except Exception:
                pass

        games = wins + losses + ties
        record[int(roster_id)] = dict(
            wins=wins,
            losses=losses,
            ties=ties,
            games=games,
        )
    return record


def load_usernames(conn: sqlite3.Connection, season: str):
    rows = conn.execute("""
        SELECT r.roster_id, u.display_name, u.username
        FROM rosters r
        LEFT JOIN users u
          ON r.owner_id = u.user_id
        WHERE r.season = ?
    """, (season,)).fetchall()

    mapping = {}
    for roster_id, display, user in rows:
        mapping[int(roster_id)] = display or user or f"Team {roster_id}"
    return mapping


def compute_all_play(weeks):
    expected = defaultdict(float)
    games = defaultdict(int)

    for week, entries in weeks.items():
        n = len(entries)
        if n <= 1:
            continue

        for i, (rid_i, pts_i) in enumerate(entries):
            for j, (rid_j, pts_j) in enumerate(entries):
                if i == j:
                    continue
                games[rid_i] += 1
                if pts_i > pts_j:
                    expected[rid_i] += 1
                elif pts_i == pts_j:
                    expected[rid_i] += 0.5  # tie

    return expected, games


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="All-play luck (expected vs actual wins) for a given season / week range."
    )
    parser.add_argument("--season", help="Season/year (e.g. 2024). If omitted, uses latest season in DB.")
    parser.add_argument("--week-start", type=int, help="First week to include (e.g. 1).")
    parser.add_argument("--week-end", type=int, help="Last week to include (e.g. 14).")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    # Season resolution
    season = args.season or detect_default_season(conn)

    # Week range resolution
    min_w, max_w = detect_week_range(conn, season)
    week_start = args.week_start if args.week_start is not None else min_w
    week_end = args.week_end if args.week_end is not None else max_w

    if week_start < min_w or week_end > max_w:
        raise RuntimeError(f"Requested weeks {week_start}-{week_end}, but data is only {min_w}-{max_w} for season={season}.")

    print(f"Using season={season}, weeks={week_start}-{week_end}")

    weeks = load_points(conn, season, week_start, week_end)
    if not weeks:
        raise RuntimeError(f"No matchup data in that range for season={season}, weeks={week_start}-{week_end}.")

    record = load_records(conn, season)
    names = load_usernames(conn, season)

    expected, games = compute_all_play(weeks)

    rows = []
    for roster_id in sorted(expected.keys()):
        exp = expected[roster_id]
        g = games[roster_id] or 1  # avoid div-by-zero

        exp_perc = exp / g

        rec = record.get(roster_id, {})
        actual_w = rec.get("wins", 0)
        actual_t = rec.get("ties", 0)

        # NOTE: ActW here is still full-season wins, even if you're slicing weeks.
        # If you want "actual in that slice", you'd need to recompute per-week win/loss
        # from matchups. For now, treat ActW as season-long baseline vs slice exp.
        actual = actual_w + 0.5 * actual_t
        luck = actual - exp

        rows.append(dict(
            roster_id=roster_id,
            name=names.get(roster_id, f"Team {roster_id}"),
            expected_wins=round(exp, 3),
            actual_wins=round(actual, 3),
            games=g,
            luck=round(luck, 3),
            exp_pct=round(exp_perc, 3),
        ))

    rows.sort(key=lambda r: r["luck"], reverse=True)

    print(f"{'Roster':>6}  {'Manager':25s}  {'ExpW':>6} {'ActW':>6} {'Luck':>7}  {'G':>3}  {'Exp%':>6}")
    print("-" * 75)
    for r in rows:
        print(
            f"{r['roster_id']:>6}  "
            f"{r['name'][:25]:25s}  "
            f"{r['expected_wins']:>6.2f} "
            f"{r['actual_wins']:>6.2f} "
            f"{r['luck']:>7.2f}  "
            f"{r['games']:>3d}  "
            f"{r['exp_pct']:>6.3f}"
        )

    conn.close()


if __name__ == "__main__":
    main()
