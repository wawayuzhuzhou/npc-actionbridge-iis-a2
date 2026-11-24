import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from adapter.qwen_baseline.merchant_probe import (
    CapturingChain,
    CapturingRetriever,
    EXPECTED_ACTION,
    HELD_ITEMS,
    PLAYER_INPUT,
    build_probe_result,
    build_original_prompt_preview,
    read_merchant_contract,
    run_probe,
)


class MerchantProbeOfflineTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self.text = body

        def json(self):
            return json.loads(self.text)

    def test_original_merchant_contract_and_gold_serialization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "game_data.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE NPCs (
                        npc_name TEXT PRIMARY KEY,
                        personality TEXT,
                        allowed_actions TEXT
                    );
                    INSERT INTO NPCs VALUES
                        ('Merchant', 'Calm and friendly.', 'sell_katana');
                    """
                )
            finally:
                connection.close()
            contract = read_merchant_contract(db_path)
            self.assertEqual(contract["allowed_actions"], EXPECTED_ACTION)
            self.assertEqual(HELD_ITEMS, "8 Gold")

    def test_prompt_preview_uses_original_fields_without_test_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "game_data.db"
            facts_path = root / "world_facts.txt"
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE NPCs (
                        npc_name TEXT PRIMARY KEY,
                        personality TEXT,
                        allowed_actions TEXT
                    );
                    INSERT INTO NPCs VALUES
                        ('Merchant', 'Calm and friendly.', 'sell_katana');
                    """
                )
            finally:
                connection.close()
            facts_path.write_text(
                "The merchant will sell a katana for 8 gold.\n",
                encoding="utf-8",
            )
            prompt = build_original_prompt_preview(
                db_path=db_path,
                world_facts_path=facts_path,
            )
            self.assertIn("Available actions: sell_katana", prompt)
            self.assertIn("Held items: 8 Gold", prompt)
            self.assertIn(f"Player: {PLAYER_INPUT}", prompt)
            self.assertNotIn("expected action", prompt.lower())
            json.dumps({"prompt": prompt})

    def test_http_500_without_inserted_row_is_preserved(self):
        chain = CapturingChain(object())
        retriever = CapturingRetriever(object())
        with tempfile.TemporaryDirectory() as temp_dir:
            frozen_db = Path(temp_dir) / "game_data.db"
            frozen_db.write_bytes(b"unchanged")
            result = build_probe_result(
                response=self.FakeResponse(
                    500,
                    '{"detail":"provider failure"}',
                ),
                latency_ms=14.2,
                inserted_row=None,
                contract={
                    "personality": "Calm and friendly.",
                    "allowed_actions": "sell_katana",
                },
                retriever=retriever,
                chain=chain,
                frozen_db_path=frozen_db,
                frozen_db_hash_before="BEFORE",
                faiss_hashes_before={},
            )
        self.assertEqual(result["http_status"], 500)
        self.assertEqual(result["execution_status"], "FAIL")
        self.assertEqual(result["response_body_redacted"], '{"detail":"provider failure"}')
        self.assertEqual(result["response_json"], {"detail": "provider failure"})
        self.assertEqual(result["inserted_sqlite_row"], None)
        self.assertEqual(result["sqlite_insert_status"], "NOT_INSERTED")
        self.assertEqual(result["intent_action_status"], "NOT_EVALUATED")
        self.assertEqual(result["chat_invocations_observed_client_path"], 0)

    def test_existing_evidence_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "evidence.json"
            original = b'{"historical":"keep"}\n'
            output.write_bytes(original)
            with self.assertRaises(FileExistsError):
                run_probe(
                    frozen_db_path=Path(temp_dir) / "missing.db",
                    frozen_root=Path(temp_dir),
                    faiss_path=Path(temp_dir) / "vector_store",
                    world_facts_path=Path(temp_dir) / "facts.txt",
                    output_path=output,
                )
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
