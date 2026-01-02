import sqlite3, json
from pathlib import Path

DB = Path("data/processed/sleeper.sqlite")

def jloads(s):
    return json.loads(s) if s else None

def main(league_id: str, season: str):
    conn = sqlite3.connect(DB)
    conn.executescript(Path("schema.sql").read_text(encoding="utf-8"))

    rows = conn.execute("""
      SELECT week, transaction_id, type, status, data_json
      FROM transactions
      WHERE league_id = ? AND season = ?
      ORDER BY week
    """, (league_id, season)).fetchall()

    out = []
    for week, txn_id, txn_type, status, data_json in rows:
        d = json.loads(data_json)
        created = d.get("created") or d.get("created_ts") or d.get("created_at") or d.get("created_at_ms")
        # Sleeper commonly uses "created" (ms). If missing, fall back to 0.
        event_ts = int(created or 0)

        adds = d.get("adds") or {}
        drops = d.get("drops") or {}
        waivers = d.get("waivers") or []
        settings = d.get("settings") or {}
        bid = settings.get("waiver_bid")

        # Adds/drops maps are usually: player_id -> roster_id
        for player_id, roster_id in (adds.items() if isinstance(adds, dict) else []):
            out.append((
                league_id, season, event_ts, str(txn_id), int(roster_id) if roster_id is not None else None,
                "add", str(player_id), None, int(bid) if bid is not None else None,
                json.dumps(d, ensure_ascii=False)
            ))

        for player_id, roster_id in (drops.items() if isinstance(drops, dict) else []):
            out.append((
                league_id, season, event_ts, str(txn_id), int(roster_id) if roster_id is not None else None,
                "drop", str(player_id), None, int(bid) if bid is not None else None,
                json.dumps(d, ensure_ascii=False)
            ))

        # Waivers list sometimes contains objects with player_id/roster_id; keep it as extra signal
        if isinstance(waivers, list):
            for w in waivers:
                pid = w.get("player_id")
                rid = w.get("roster_id")
                if pid is None:
                    continue
                out.append((
                    league_id, season, event_ts, str(txn_id), int(rid) if rid is not None else None,
                    "waiver", str(pid), None, int(bid) if bid is not None else None,
                    json.dumps(d, ensure_ascii=False)
                ))

    conn.executemany("""
      INSERT OR REPLACE INTO player_events
      (league_id, season, event_ts, transaction_id, roster_id, event_type, player_id, related_player_id, faab_bid, data_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, out)
    conn.commit()
    conn.close()
    print(f"Inserted/updated {len(out)} player_events for league_id={league_id} season={season}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--league-id", required=True)
    p.add_argument("--season", required=True)
    args = p.parse_args()
    main(args.league_id, args.season)
