import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(conn: sqlite3.Connection, schema_path: Path) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()

def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)

def upsert_league(conn, league_id: str, season: Optional[str], data: Dict[str, Any]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO leagues (league_id, season, data_json, fetched_at) VALUES (?, ?, ?, ?)",
        (league_id, season, dumps(data), utc_now_iso()),
    )

def upsert_users(conn, league_id: str, users: list[Dict[str, Any]]) -> None:
    now = utc_now_iso()
    rows = []
    for u in users:
        rows.append((
            league_id,
            str(u.get("user_id")),
            u.get("username"),
            u.get("display_name"),
            dumps(u),
            now
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO users (league_id, user_id, username, display_name, data_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )

def upsert_rosters(conn, league_id: str, season: str, rosters: list[Dict[str, Any]]) -> None:
    now = utc_now_iso()
    rows = []
    for r in rosters:
        rows.append((
            league_id,
            season,
            int(r.get("roster_id")),
            str(r.get("owner_id")) if r.get("owner_id") is not None else None,
            dumps(r.get("settings")) if r.get("settings") is not None else None,
            dumps(r.get("players")) if r.get("players") is not None else None,
            dumps(r.get("starters")) if r.get("starters") is not None else None,
            dumps(r),
            now
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO rosters (league_id, season, roster_id, owner_id, settings_json, players_json, starters_json, data_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )

def upsert_drafts(conn, league_id: str, season: Optional[str], drafts: list[Dict[str, Any]]) -> None:
    now = utc_now_iso()
    rows = []
    for d in drafts:
        rows.append((league_id, str(d.get("draft_id")), season, dumps(d), now))
    conn.executemany(
        "INSERT OR REPLACE INTO drafts (league_id, draft_id, season, data_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
        rows,
    )

def upsert_draft_picks(conn, draft_id: str, picks: list[Dict[str, Any]]) -> None:
    now = utc_now_iso()
    rows = []
    for p in picks:
        # Sleeper uses "pick_no" as overall pick number
        pick_no = int(p.get("pick_no"))
        rows.append((
            str(draft_id),
            pick_no,
            int(p.get("round")) if p.get("round") is not None else None,
            int(p.get("roster_id")) if p.get("roster_id") is not None else None,
            str(p.get("player_id")) if p.get("player_id") is not None else None,
            dumps(p.get("metadata")) if p.get("metadata") is not None else None,
            int(p.get("picked_at")) if p.get("picked_at") is not None else None,
            dumps(p),
            now
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO draft_picks (draft_id, pick_no, round, roster_id, player_id, metadata_json, picked_at, data_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )

def upsert_matchups(conn, league_id: str, season: str, week: int, matchups: list[Dict[str, Any]]) -> None:
    now = utc_now_iso()
    rows = []
    for m in matchups:
        rows.append((
            league_id,
            season,
            int(week),
            int(m.get("roster_id")),
            float(m.get("points")) if m.get("points") is not None else None,
            dumps(m.get("starters")) if m.get("starters") is not None else None,
            dumps(m.get("players")) if m.get("players") is not None else None,
            dumps(m),
            now
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO matchups (league_id, season, week, roster_id, points, starters_json, players_json, data_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )

def upsert_transactions(conn, league_id: str, season: str, week: int, txns: list[Dict[str, Any]]) -> None:
    now = utc_now_iso()
    rows = []
    for t in txns:
        rows.append((
            league_id,
            season,
            int(week),
            str(t.get("transaction_id")),
            t.get("type"),
            t.get("status"),
            str(t.get("creator")) if t.get("creator") is not None else None,
            dumps(t.get("roster_ids")) if t.get("roster_ids") is not None else None,
            dumps(t.get("adds")) if t.get("adds") is not None else None,
            dumps(t.get("drops")) if t.get("drops") is not None else None,
            dumps(t.get("waivers")) if t.get("waivers") is not None else None,
            dumps(t),
            now
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO transactions (league_id, season, week, transaction_id, type, status, creator, roster_ids_json, adds_json, drops_json, waivers_json, data_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
