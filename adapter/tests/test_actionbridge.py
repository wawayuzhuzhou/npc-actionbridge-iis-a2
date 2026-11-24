import gc
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from adapter.actionbridge.api import create_app
from adapter.qwen_baseline.contract import NPCAction, Response
from adapter.tests.test_qwen_runtime import create_database, MockRetriever


class FixtureChat:
    def __init__(self):
        self.payloads = []
        self.reply = Response(action=NPCAction.SELL_KATANA, response="Here is your katana.")

    def invoke(self, payload):
        self.payloads.append(payload)
        return self.reply


class ActionBridgeIntegrationTests(unittest.TestCase):
    """Deterministic injected-action fixtures, never live LLM observations."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "enhanced.db"
        create_database(self.db)
        # Production seed greetings predate new conversations (2025 vs 2026).
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE Conversations SET timestamp='2025-04-30 10:37:46'")
        self.chat = FixtureChat()
        self.app = create_app(db_path=self.db, chain=self.chat, vector_store=MockRetriever())
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        gc.collect()
        self.temp.cleanup()

    def propose(self):
        result = self.client.post("/get_response", json={
            "player_name": "Alice", "npc_name": "Merchant", "held_items": "8 Gold",
            "player_input": "I want to buy the katana.",
        })
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["action"], "none")
        self.assertEqual(result.json()["proposed_action"], "sell_katana")
        return result.json()["proposal_id"]

    def report(self, proposal_id, status, before=None, after=None, **extra):
        state = {"gold": 8, "katana": False, "door_open": None}
        return self.client.post("/actionbridge/outcome", json={
            "proposal_id": proposal_id, "player_name": "Alice", "status": status,
            "before": before or state, "after": after or state, **extra,
        })

    def test_pending_raw_claim_is_separate_from_display_and_history(self):
        proposal_id = self.propose()
        event = self.app.state.proposals.get(proposal_id)
        self.assertEqual(event["status"], "Pending")
        self.assertEqual(json.loads(event["raw_response"])["response"], "Here is your katana.")
        self.assertIsNotNone(event["conversation_id"])
        response = self.client.post("/get_latest_response", json={
            "player_name": "Alice", "npc_name": "Merchant", "held_items": "8 Gold", "player_input": "",
        })
        self.assertNotIn("Here is your katana", response.json()["response"])
        self.assertIn("no purchase has happened", response.json()["response"])

    def test_cancel_then_followup_reads_actual_outcome_without_model_repair_call(self):
        proposal_id = self.propose()
        saved = self.report(proposal_id, "Cancelled", reason="player_cancelled")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "Cancelled")
        self.assertEqual(len(self.chat.payloads), 1)  # Saving needed no extra generation.
        self.chat.reply = Response(action=NPCAction.NONE, response="Come back when ready.")
        self.client.post("/get_response", json={
            "player_name": "Alice", "npc_name": "Merchant", "held_items": "8 Gold",
            "player_input": "What happened to the purchase?",
        })
        history = self.chat.payloads[-1]["chat_history"]
        self.assertIn("Action cancelled", history)
        self.assertIn("Katana: no", history)
        self.assertNotIn("Here is your katana", history)

    def test_commit_and_duplicate_report_are_idempotent(self):
        proposal_id = self.propose()
        after = {"gold": 0, "katana": True, "door_open": None}
        first = self.report(proposal_id, "Committed", after=after)
        second = self.report(proposal_id, "Committed", after=after)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["status"], "Committed")
        self.assertEqual(self.report(proposal_id, "Cancelled").status_code, 409)
        with sqlite3.connect(self.db) as db:
            action, text = db.execute("SELECT npc_action,npc_response FROM Conversations ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(action, "sell_katana")
            self.assertIn("Purchase completed", text)
        self.assertEqual(len(self.chat.payloads), 1)

    def test_unverified_execution_is_failed_not_a_historical_success(self):
        proposal_id = self.propose()
        before = {"gold": 7, "katana": False, "door_open": None}
        after = {"gold": 0, "katana": True, "door_open": None}
        result = self.report(proposal_id, "Committed", before, after)
        self.assertEqual(result.json()["status"], "Failed")
        with sqlite3.connect(self.db) as db:
            row = db.execute("SELECT npc_action,npc_response FROM Conversations ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row[0], "none")
        self.assertIn("failed", row[1])
        self.assertNotIn("Here is your katana", row[1])

    def test_rejection_and_failure_persist_recovery_for_next_turn(self):
        for status in ("Rejected", "Failed"):
            with self.subTest(status=status):
                proposal_id = self.propose()
                current = {"gold": 7, "katana": False, "door_open": None}
                result = self.report(proposal_id, status, before=current, after=current, reason="insufficient_gold")
                self.assertEqual(result.json()["status"], status)
                self.assertIn("Collect enough gold", result.json()["feedback"])
                event = self.app.state.proposals.get(proposal_id)
                self.assertEqual(event["status"], status)

    def test_text_held_items_is_not_an_execution_report(self):
        proposal_id = self.propose()
        result = self.client.post("/actionbridge/outcome", json={
            "proposal_id": proposal_id, "player_name": "Alice", "status": "Committed", "held_items": "Katana",
        })
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.app.state.proposals.get(proposal_id)["status"], "Pending")

    def test_ordinary_dialogue_does_not_create_a_confirmation_proposal(self):
        self.chat.reply = Response(action=NPCAction.NONE, response="Hello.")
        result = self.client.post("/get_response", json={
            "player_name": "Alice", "npc_name": "Merchant", "held_items": "0 Gold", "player_input": "Hello.",
        })
        self.assertNotIn("proposal_id", result.json())
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ActionProposals").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
