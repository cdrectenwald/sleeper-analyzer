import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from src.common.logging import setup_logging
from src.sleeper.api import get_json
from src.sleeper.db import (
    connect, init_db,
    upsert_league, upsert_users, upsert_rosters,
    upsert_drafts, upsert_draft_picks,
    upsert_matchups, upsert_transactions,
)

log = logging.getLogger(__name__)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def write_raw(raw_root: Path, rel_path: str, data: Any) -> None:
    path = raw_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def safe_season(league: Dict[str, Any]) -> str:
    season = league.get("season") or league.get("settings", {}).get("season")
    return str(season)

def try_get_json(endpoint: str) -> Optional[Any]:
    try:
        return get_json(endpoint)
    except Exception:
        return None

def upsert_single_json(conn, sql: str, params: tuple) -> None:
    conn.execute(sql, params)
    conn.commit()

def main(league_id: str, max_week: int = 18, fetch_players: bool = False) -> None:
    start_time = time.perf_counter()
    base = Path(".")
    raw_root = base / "data" / "raw" / f"league={league_id}"
    db_path = base / "data" / "processed" / "sleeper.sqlite"
    schema_path = base / "schema.sql"

    conn = connect(db_path)
    init_db(conn, schema_path)

    log.info("Fetching league_id=%s max_week=%d", league_id, max_week)

    # NFL state (useful for future auto-week logic + UI)
    state = try_get_json("/state/nfl")
    if state is not None:
        write_raw(raw_root, f"state/nfl.json", state)
        upsert_single_json(
            conn,
            "INSERT OR REPLACE INTO nfl_state (sport, data_json, fetched_at) VALUES (?, ?, ?)",
            ("nfl", json.dumps(state, ensure_ascii=False), utc_now()),
        )

    # League core
    league = get_json(f"/league/{league_id}")
    season = safe_season(league)
    name = league.get("name", "(unnamed league)")
    log.info("Detected season=%s league_name=%s", season, name)

    write_raw(raw_root, f"season={season}/league.json", league)
    upsert_league(conn, league_id, season, league)
    conn.commit()

    # Brackets + traded picks (may be empty/offseason; safe_get avoids hard failure)
    winners = try_get_json(f"/league/{league_id}/winners_bracket")
    if winners is not None:
        write_raw(raw_root, f"season={season}/winners_bracket.json", winners)
        upsert_single_json(
            conn,
            "INSERT OR REPLACE INTO league_brackets (league_id, season, bracket_type, data_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (league_id, season, "winners", json.dumps(winners, ensure_ascii=False), utc_now()),
        )

    losers = try_get_json(f"/league/{league_id}/losers_bracket")
    if losers is not None:
        write_raw(raw_root, f"season={season}/losers_bracket.json", losers)
        upsert_single_json(
            conn,
            "INSERT OR REPLACE INTO league_brackets (league_id, season, bracket_type, data_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (league_id, season, "losers", json.dumps(losers, ensure_ascii=False), utc_now()),
        )

    traded = try_get_json(f"/league/{league_id}/traded_picks")
    if traded is not None:
        write_raw(raw_root, f"season={season}/traded_picks.json", traded)
        upsert_single_json(
            conn,
            "INSERT OR REPLACE INTO traded_picks (league_id, season, data_json, fetched_at) VALUES (?, ?, ?, ?)",
            (league_id, season, json.dumps(traded, ensure_ascii=False), utc_now()),
        )

    # Optional: full players dump (BIG). Good to cache once per machine.
    if fetch_players:
        players = try_get_json("/players/nfl")
        if players is not None:
            base_players = base / "data" / "raw" / "players"
            base_players.mkdir(parents=True, exist_ok=True)
            (base_players / "nfl.json").write_text(
                json.dumps(players, ensure_ascii=False),
                encoding="utf-8"
            )
            upsert_single_json(
                conn,
                "INSERT OR REPLACE INTO players_dump (sport, data_json, fetched_at) VALUES (?, ?, ?)",
                ("nfl", json.dumps(players, ensure_ascii=False), utc_now()),
            )
            log.info("Cached players/nfl (%d entries)", len(players))

    # Users / rosters
    users = get_json(f"/league/{league_id}/users")
    write_raw(raw_root, f"season={season}/users.json", users)
    upsert_users(conn, league_id, users)
    conn.commit()

    rosters = get_json(f"/league/{league_id}/rosters")
    write_raw(raw_root, f"season={season}/rosters.json", rosters)
    upsert_rosters(conn, league_id, season, rosters)
    conn.commit()

    # Drafts + picks
    drafts = get_json(f"/league/{league_id}/drafts")
    write_raw(raw_root, f"season={season}/drafts.json", drafts)
    upsert_drafts(conn, league_id, season, drafts)
    conn.commit()

    for d in drafts:
        draft_id = str(d.get("draft_id"))
        if not draft_id:
            continue
        log.debug("Fetching draft_id=%s", draft_id)
        picks = get_json(f"/draft/{draft_id}/picks")
        write_raw(raw_root, f"season={season}/draft_id={draft_id}/picks.json", picks)
        upsert_draft_picks(conn, draft_id, picks)
        conn.commit()

    # Matchups + transactions by week
    for week in range(1, max_week + 1):
        log.debug("Fetching week=%d", week)
        matchups = get_json(f"/league/{league_id}/matchups/{week}")
        write_raw(raw_root, f"season={season}/week={week:02d}/matchups.json", matchups)
        if isinstance(matchups, list) and matchups:
            upsert_matchups(conn, league_id, season, week, matchups)
            conn.commit()
        else:
            log.warning("No matchups for week=%d", week)

        txns = get_json(f"/league/{league_id}/transactions/{week}")
        write_raw(raw_root, f"season={season}/week={week:02d}/transactions.json", txns)
        if isinstance(txns, list) and txns:
            upsert_transactions(conn, league_id, season, week, txns)
            conn.commit()

    conn.close()
    elapsed = time.perf_counter() - start_time
    log.info("Completed fetch for league_id=%s in %.2fs", league_id, elapsed)
    log.info("Raw data saved under %s", raw_root)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--league-id", required=True)
    p.add_argument("--max-week", type=int, default=18)
    p.add_argument("--fetch-players", action="store_true", help="Also fetch /players/nfl and cache it (large).")
    p.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = p.parse_args()
    
    setup_logging(args.log_level)
    main(args.league_id, args.max_week, args.fetch_players)
