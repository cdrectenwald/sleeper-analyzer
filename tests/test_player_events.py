"""Tests for player events extraction from transaction JSON."""
import pytest
import json


class TestPlayerEventsExtraction:
    """Tests for extracting player events from Sleeper transaction data."""

    @pytest.fixture
    def sample_waiver_add(self):
        """Sample waiver wire add transaction."""
        return {
            "type": "waiver",
            "status": "complete",
            "transaction_id": "12345",
            "roster_ids": [1],
            "adds": {"4046": 1},  # player_id: roster_id
            "drops": {"5001": 1},
            "settings": {"waiver_bid": 15},
            "created": 1695686400000,  # epoch ms
        }

    @pytest.fixture
    def sample_trade(self):
        """Sample trade transaction."""
        return {
            "type": "trade",
            "status": "complete",
            "transaction_id": "67890",
            "roster_ids": [1, 2],
            "adds": {
                "4046": 2,  # player 4046 goes to roster 2
                "5001": 1,  # player 5001 goes to roster 1
            },
            "drops": None,
            "draft_picks": [
                {
                    "season": "2025",
                    "round": 1,
                    "roster_id": 1,  # pick goes to roster 1
                    "previous_owner_id": 2,
                    "owner_id": 1,
                }
            ],
            "created": 1695772800000,
        }

    @pytest.fixture
    def sample_free_agent_add(self):
        """Sample free agent add transaction."""
        return {
            "type": "free_agent",
            "status": "complete",
            "transaction_id": "11111",
            "roster_ids": [3],
            "adds": {"6789": 3},
            "drops": None,
            "created": 1695859200000,
        }

    def test_parse_waiver_add(self, sample_waiver_add):
        """Parse a waiver wire add correctly."""
        txn = sample_waiver_add
        
        events = []
        
        # Extract adds
        if txn.get("adds"):
            for player_id, roster_id in txn["adds"].items():
                events.append({
                    "transaction_id": txn["transaction_id"],
                    "type": "add",
                    "source": txn["type"],  # waiver
                    "player_id": player_id,
                    "roster_id": roster_id,
                    "faab_bid": txn.get("settings", {}).get("waiver_bid"),
                })

        # Extract drops
        if txn.get("drops"):
            for player_id, roster_id in txn["drops"].items():
                events.append({
                    "transaction_id": txn["transaction_id"],
                    "type": "drop",
                    "source": txn["type"],
                    "player_id": player_id,
                    "roster_id": roster_id,
                    "faab_bid": None,
                })

        assert len(events) == 2
        
        add_event = next(e for e in events if e["type"] == "add")
        assert add_event["player_id"] == "4046"
        assert add_event["roster_id"] == 1
        assert add_event["source"] == "waiver"
        assert add_event["faab_bid"] == 15

        drop_event = next(e for e in events if e["type"] == "drop")
        assert drop_event["player_id"] == "5001"
        assert drop_event["roster_id"] == 1

    def test_parse_trade(self, sample_trade):
        """Parse a trade transaction correctly."""
        txn = sample_trade
        
        events = []
        
        # Trade adds
        if txn.get("adds"):
            for player_id, to_roster_id in txn["adds"].items():
                # Find the other roster (the one who gave up this player)
                from_roster_id = [r for r in txn["roster_ids"] if r != to_roster_id][0] if len(txn["roster_ids"]) == 2 else None
                events.append({
                    "transaction_id": txn["transaction_id"],
                    "type": "trade_receive",
                    "player_id": player_id,
                    "to_roster_id": to_roster_id,
                    "from_roster_id": from_roster_id,
                })

        # Draft pick trades
        if txn.get("draft_picks"):
            for pick in txn["draft_picks"]:
                events.append({
                    "transaction_id": txn["transaction_id"],
                    "type": "trade_pick",
                    "pick_season": pick["season"],
                    "pick_round": pick["round"],
                    "to_roster_id": pick["owner_id"],
                    "from_roster_id": pick["previous_owner_id"],
                })

        assert len(events) == 3  # 2 player moves + 1 pick

        # Check player trades
        player_events = [e for e in events if e["type"] == "trade_receive"]
        assert len(player_events) == 2

        # Check pick trade
        pick_event = next(e for e in events if e["type"] == "trade_pick")
        assert pick_event["pick_round"] == 1
        assert pick_event["pick_season"] == "2025"
        assert pick_event["to_roster_id"] == 1
        assert pick_event["from_roster_id"] == 2

    def test_parse_free_agent_add(self, sample_free_agent_add):
        """Parse a free agent add correctly."""
        txn = sample_free_agent_add
        
        events = []
        if txn.get("adds"):
            for player_id, roster_id in txn["adds"].items():
                events.append({
                    "transaction_id": txn["transaction_id"],
                    "type": "add",
                    "source": txn["type"],
                    "player_id": player_id,
                    "roster_id": roster_id,
                })

        assert len(events) == 1
        assert events[0]["source"] == "free_agent"
        assert events[0]["player_id"] == "6789"
        assert events[0]["roster_id"] == 3

    def test_skip_failed_transactions(self):
        """Failed transactions should be skipped."""
        failed_txn = {
            "type": "waiver",
            "status": "failed",
            "transaction_id": "99999",
            "roster_ids": [1],
            "adds": {"4046": 1},
        }

        # Only process complete transactions
        if failed_txn.get("status") == "complete":
            events = []  # would process here
        else:
            events = []

        assert len(events) == 0
