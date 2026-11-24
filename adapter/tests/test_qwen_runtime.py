from pathlib import Path
import gc
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from adapter.qwen_baseline.config import ConfigurationError, assert_runtime_db_path
from adapter.qwen_baseline.contract import NPCAction, Response
from adapter.qwen_baseline.fastapi_app import create_app
from adapter.qwen_baseline.retrieval import RetrievedFact


class MockChain:
    def __init__(self):
        self.payloads = []

    def invoke(self, payload):
        self.payloads.append(payload)
        return Response(
            action=NPCAction.SELL_KATANA,
            response="Here is your katana.",
        )


class MockRetriever:
    def similarity_search(self, query, *, k):
        return [RetrievedFact("The merchant sells a katana for 8 gold.")]


def create_database(path: Path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE NPCs (
                npc_name TEXT PRIMARY KEY,
                personality TEXT,
                allowed_actions TEXT
            );
            CREATE TABLE Players (
                player_name TEXT PRIMARY KEY,
                creation_timestamp TEXT
            );
            CREATE TABLE Conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT,
                npc_name TEXT,
                held_items TEXT,
                player_input TEXT,
                npc_response TEXT,
                npc_action TEXT,
                timestamp TEXT
            );
            INSERT INTO NPCs VALUES
                ('Merchant', 'Calm merchant', 'sell_katana'),
                ('Guard', 'Harsh guard', 'open_door');
            INSERT INTO Players VALUES ('Alice', datetime('now'));
            INSERT INTO Conversations
                (player_name, npc_name, player_input, npc_response, timestamp)
            VALUES ('Alice', 'Merchant', '', 'Hello.', datetime('now'));
            """
        )


class RuntimeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "game_data.db"
        create_database(self.db_path)
        self.chain = MockChain()
        self.retriever = MockRetriever()
        app = create_app(
            db_path=self.db_path,
            chain=self.chain,
            vector_store=self.retriever,
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        gc.collect()
        self.temp_dir.cleanup()

    def test_get_response_injects_original_context_and_persists_history(self):
        response = self.client.post(
            "/get_response",
            json={
                "player_name": "Alice",
                "npc_name": "Merchant",
                "held_items": "8 Gold",
                "player_input": "I want to buy the katana.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "sell_katana")
        payload = self.chain.payloads[0]
        self.assertEqual(payload["allowed_actions"], "sell_katana")
        self.assertIn("Player: \nNPC: Hello.", payload["chat_history"])
        self.assertIn("8 gold", payload["world_facts"])

        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT held_items, player_input, npc_action
                FROM Conversations
                WHERE player_name = 'Alice'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
        self.assertEqual(row, ("8 Gold", "I want to buy the katana.", "sell_katana"))

    def test_route_surface_and_latest_response(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/conversations").status_code, 200)
        self.assertEqual(self.client.get("/players").status_code, 200)
        response = self.client.post(
            "/get_latest_response",
            json={
                "player_name": "Alice",
                "npc_name": "Merchant",
                "held_items": "",
                "player_input": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["response"], "Hello.")

    def test_unknown_npc_is_not_sent_to_chain(self):
        response = self.client.post(
            "/get_response",
            json={
                "player_name": "Alice",
                "npc_name": "Unknown",
                "held_items": "",
                "player_input": "Hello",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.chain.payloads, [])

    def test_godot_headerless_mother_greeting_uses_seed_without_model_calls(self):
        greeting = (
            "Good morning, darling! You seem to have overslept, "
            "even though today is such an important day for you!"
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO Conversations
                    (player_name, npc_name, player_input, npc_response, timestamp)
                VALUES ('All', 'Mother', '', ?, datetime('now'))
                """,
                (greeting,),
            )
        with (
            patch.object(self.chain, "invoke") as chat,
            patch.object(self.retriever, "similarity_search") as retrieval,
        ):
            response = self.client.post(
                "/get_latest_response",
                content=json.dumps({
                    "player_name": "Alice",
                    "npc_name": "Mother",
                    "held_items": "0 Gold",
                    "player_input": "",
                }),
            )
            self.assertNotIn("content-type", response.request.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {
                "npc_name": "Mother", "action": "", "response": greeting,
            })
            chat.assert_not_called()
            retrieval.assert_not_called()

    def test_godot_headerless_dialogue_keeps_original_action_dispatch_contract(self):
        response = self.client.post(
            "/get_response",
            content=json.dumps({
                "player_name": "Alice",
                "npc_name": "Merchant",
                "held_items": "8 Gold",
                "player_input": "I want to buy the katana.",
            }),
        )
        self.assertNotIn("content-type", response.request.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "action": "sell_katana", "response": "Here is your katana.",
        })
        self.assertEqual(len(self.chain.payloads), 1)

    def test_godot_headerless_invalid_body_still_returns_422(self):
        for body in ('{"npc_name": "Mother"}', '{invalid json'):
            with self.subTest(body=body):
                response = self.client.post("/get_latest_response", content=body)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.chain.payloads, [])

    def test_generation_failure_logs_stage_without_retry_or_secret(self):
        secret = "offline-test-provider-key"
        query = {
            "player_name": "Alice", "npc_name": "Guard",
            "held_items": "0 Gold", "player_input": "What?",
        }
        cases = (
            ("retrieval", self.retriever, "similarity_search", 0),
            ("chat_and_structured_output", self.chain, "invoke", 1),
        )
        for stage, target, method, expected_chain_calls in cases:
            with (
                self.subTest(stage=stage),
                patch.dict(os.environ, {"A2_PROXY_API_KEY": secret}),
                patch.object(target, method, side_effect=ValueError(f"Failure {secret}")) as failed,
                self.assertLogs("uvicorn.error", level="ERROR") as logs,
            ):
                response = self.client.post("/get_response", content=json.dumps(query))
                self.assertEqual(response.status_code, 500)
                failed.assert_called_once()
                self.assertEqual(len(logs.output), 1)
                self.assertNotIn(secret, logs.output[0])
                event = json.loads(logs.records[0].getMessage().split(": ", 1)[1])
                self.assertEqual(event["stage"], stage)
                self.assertEqual(event["player_input"], "What?")
                self.assertEqual(event["held_items"], "0 Gold")
                self.assertEqual(event["error_type"], "ValueError")
                self.assertEqual(event["retriever_invocations_client_path"], 1)
                self.assertEqual(event["chain_invocations_client_path"], expected_chain_calls)
                self.assertIn("[REDACTED]", event["error"])
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM Conversations WHERE npc_name='Guard'"
            ).fetchone()[0], 0)

    def test_generation_success_logs_context_and_client_path_counts(self):
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.client.post("/get_response", json={
                "player_name": "Alice", "npc_name": "Merchant",
                "held_items": "8 Gold", "player_input": "I want to buy the katana.",
            })
        self.assertEqual(response.status_code, 200)
        event = json.loads(logs.records[0].getMessage().split(": ", 1)[1])
        self.assertEqual(event["action"], "sell_katana")
        self.assertEqual(event["retriever_invocations_client_path"], 1)
        self.assertEqual(event["chain_invocations_client_path"], 1)
        self.assertEqual(event["stage"], "completed")

    def test_name_check_preserves_original_behavior(self):
        response = self.client.post(
            "/check_name_availability",
            json={"player_name": "NewPlayer"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"available": True})

    def test_empty_latest_history_preserves_original_500(self):
        response = self.client.post(
            "/get_latest_response",
            json={
                "player_name": "Alice",
                "npc_name": "Sensei",
                "held_items": "",
                "player_input": "",
            },
        )
        self.assertEqual(response.status_code, 500)

    def test_runtime_rejects_frozen_database_path(self):
        frozen_root = Path(self.temp_dir.name) / "frozen_source"
        frozen_db = frozen_root / "api" / "data" / "game_data.db"
        frozen_db.parent.mkdir(parents=True)
        frozen_db.write_bytes(b"frozen")

        with self.assertRaises(ConfigurationError):
            assert_runtime_db_path(frozen_db, frozen_root=frozen_root)

        nested_db = frozen_root / "runtime" / "game_data.db"
        with self.assertRaises(ConfigurationError):
            assert_runtime_db_path(nested_db, frozen_root=frozen_root)

        alias_root = Path(self.temp_dir.name) / "runtime-alias"
        try:
            os.symlink(frozen_root, alias_root, target_is_directory=True)
        except OSError as exc:
            if getattr(exc, "winerror", None) != 1314:
                raise
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "New-Item -ItemType Junction "
                        f"-Path '{alias_root}' -Target '{frozen_root}'"
                    ),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        symlink_path = alias_root / "api" / "data" / "game_data.db"
        with self.assertRaises(ConfigurationError):
            assert_runtime_db_path(symlink_path, frozen_root=frozen_root)


if __name__ == "__main__":
    unittest.main()
