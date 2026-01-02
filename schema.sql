PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS leagues (
  league_id TEXT PRIMARY KEY,
  season TEXT,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  league_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  username TEXT,
  display_name TEXT,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league_id, user_id)
);

CREATE TABLE IF NOT EXISTS rosters (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  roster_id INTEGER NOT NULL,
  owner_id TEXT,
  settings_json TEXT,
  players_json TEXT,
  starters_json TEXT,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league_id, season, roster_id)
);

CREATE TABLE IF NOT EXISTS drafts (
  league_id TEXT NOT NULL,
  draft_id TEXT NOT NULL,
  season TEXT,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league_id, draft_id)
);

CREATE TABLE IF NOT EXISTS draft_picks (
  draft_id TEXT NOT NULL,
  pick_no INTEGER NOT NULL,
  round INTEGER,
  roster_id INTEGER,
  player_id TEXT,
  metadata_json TEXT,
  picked_at INTEGER,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (draft_id, pick_no)
);

CREATE TABLE IF NOT EXISTS matchups (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  week INTEGER NOT NULL,
  roster_id INTEGER NOT NULL,
  points REAL,
  starters_json TEXT,
  players_json TEXT,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league_id, season, week, roster_id)
);

CREATE TABLE IF NOT EXISTS transactions (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  week INTEGER NOT NULL,
  transaction_id TEXT NOT NULL,
  type TEXT,
  status TEXT,
  creator TEXT,
  roster_ids_json TEXT,
  adds_json TEXT,
  drops_json TEXT,
  waivers_json TEXT,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league_id, season, week, transaction_id)
);

CREATE TABLE IF NOT EXISTS metrics_team_week (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  week INTEGER NOT NULL,
  roster_id INTEGER NOT NULL,

  points_for REAL,
  bench_points REAL,

  all_play_wins REAL,
  all_play_games INTEGER,

  fetched_at TEXT NOT NULL,

  PRIMARY KEY (league_id, season, week, roster_id)
);

CREATE TABLE IF NOT EXISTS metrics_team_season (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  roster_id INTEGER NOT NULL,

  weeks_played INTEGER,

  points_for REAL,
  bench_points REAL,

  all_play_wins REAL,
  all_play_games INTEGER,

  exp_wins REAL,
  exp_win_pct REAL,

  actual_wins REAL,
  luck REAL,

  computed_at TEXT NOT NULL,

  PRIMARY KEY (league_id, season, roster_id)
);

CREATE TABLE IF NOT EXISTS player_events (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  event_ts INTEGER NOT NULL,          -- ms epoch
  transaction_id TEXT NOT NULL,
  roster_id INTEGER,                  -- who did it / who received
  event_type TEXT NOT NULL,           -- add|drop|trade_add|trade_drop|waiver_add|waiver_drop
  player_id TEXT NOT NULL,
  related_player_id TEXT,             -- for “add X dropped Y” pairing when possible
  faab_bid INTEGER,                   -- if present
  data_json TEXT NOT NULL,
  PRIMARY KEY (league_id, season, transaction_id, event_type, player_id, roster_id)
);

CREATE INDEX IF NOT EXISTS idx_player_events_lookup
  ON player_events (league_id, season, player_id, event_ts);

CREATE TABLE IF NOT EXISTS player_stints (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  roster_id INTEGER NOT NULL,
  player_id TEXT NOT NULL,
  start_ts INTEGER NOT NULL,
  end_ts INTEGER,                     -- null if still held
  start_transaction_id TEXT,
  end_transaction_id TEXT,
  faab_total INTEGER DEFAULT 0,
  dropped_player_id TEXT,             -- if we can infer
  PRIMARY KEY (league_id, season, roster_id, player_id, start_ts)
);


CREATE TABLE IF NOT EXISTS players_ref (
  player_id TEXT PRIMARY KEY,
  full_name TEXT,
  position TEXT,
  team TEXT,
  data_json TEXT NOT NULL
);

-- NFL state (current week/season info)
CREATE TABLE IF NOT EXISTS nfl_state (
  sport TEXT PRIMARY KEY,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);

-- Playoff brackets (winners / losers)
CREATE TABLE IF NOT EXISTS league_brackets (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  bracket_type TEXT NOT NULL, -- winners | losers
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league_id, season, bracket_type)
);

-- Traded picks
CREATE TABLE IF NOT EXISTS traded_picks (
  league_id TEXT NOT NULL,
  season TEXT NOT NULL,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league_id, season)
);

-- Optional: full players dump cache (big)
CREATE TABLE IF NOT EXISTS players_dump (
  sport TEXT PRIMARY KEY,
  data_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);



CREATE INDEX IF NOT EXISTS idx_matchups_league_season_week
  ON matchups (league_id, season, week);

CREATE INDEX IF NOT EXISTS idx_transactions_league_season_week
  ON transactions (league_id, season, week);
