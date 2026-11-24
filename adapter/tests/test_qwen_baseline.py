from pathlib import Path
import os
import unittest
from unittest.mock import patch

from adapter.qwen_baseline.config import ConfigurationError, QwenSettings
from adapter.qwen_baseline.contract import NPCAction, Response
from adapter.qwen_baseline.prompt import PromptContext, render_prompt
from adapter.qwen_baseline.retrieval import (
    FixtureRetriever,
    _create_embeddings,
    load_world_facts,
)


ROOT = Path(__file__).parents[1]


class FaithfulQwenBaselineTests(unittest.TestCase):
    def test_base_url_builds_chat_and_embedding_endpoints_once(self):
        old = {
            key: os.environ.get(key)
            for key in ("A2_PROXY_BASE_URL", "A2_PROXY_API_KEY", "A2_PROXY_MODEL")
        }
        try:
            os.environ["A2_PROXY_BASE_URL"] = (
                "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/"
            )
            os.environ["A2_PROXY_API_KEY"] = "offline-secret-not-printed"
            os.environ["A2_PROXY_MODEL"] = "qwen3.7-flash"
            settings = QwenSettings.from_environment()
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(
            settings.chat_endpoint,
            "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
        )
        self.assertEqual(
            settings.embedding_endpoint,
            "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/embeddings",
        )

    def test_endpoint_url_is_rejected_when_already_an_endpoint(self):
        old = os.environ.get("A2_PROXY_BASE_URL")
        os.environ["A2_PROXY_BASE_URL"] = "https://example.test/v1/chat/completions"
        try:
            with self.assertRaises(ConfigurationError):
                QwenSettings.from_environment(require_credentials=False)
        finally:
            if old is None:
                os.environ.pop("A2_PROXY_BASE_URL", None)
            else:
                os.environ["A2_PROXY_BASE_URL"] = old

    def test_original_prompt_has_no_proposal_only_adaptation(self):
        prompt = render_prompt(
            PromptContext(
                player_name="Test",
                npc_name="Merchant",
                personality="merchant personality",
                allowed_actions="sell_katana",
                world_facts="The merchant will sell a katana for 8 gold.",
                chat_history="",
                held_items="8 Gold",
                player_input="I want to buy the katana.",
            )
        )
        self.assertIn("Available actions: sell_katana", prompt)
        self.assertIn("Here is your katana.", prompt)
        self.assertNotIn("proposal", prompt.lower())

    def test_action_schema_matches_upstream_enum(self):
        self.assertEqual(
            {action.value for action in NPCAction},
            {"sell_katana", "open_door", "none"},
        )
        response = Response(action=NPCAction.SELL_KATANA, response="Here is your katana.")
        self.assertEqual(response.action.value, "sell_katana")

    def test_world_facts_and_fixture_retrieval_are_deterministic(self):
        facts = load_world_facts(ROOT / "qwen_baseline" / "world_facts.txt")
        self.assertEqual(len(facts), 12)
        results = FixtureRetriever(facts).similarity_search("How much gold for the katana?", k=3)
        self.assertTrue(any("8 gold" in item.page_content for item in results))

    def test_embedding_contract_is_explicit(self):
        settings = QwenSettings.from_environment(require_credentials=False)
        self.assertEqual(settings.embedding_model, "text-embedding-v4")
        self.assertEqual(settings.embedding_dimensions, 1024)
        embeddings = _create_embeddings(settings)
        self.assertEqual(embeddings.chunk_size, 10)
        self.assertFalse(embeddings.check_embedding_ctx_length)
        self.assertEqual(embeddings.max_retries, 0)

    def test_embedding_payload_uses_strings_for_qwen(self):
        settings = QwenSettings.from_environment(require_credentials=False)
        embeddings = _create_embeddings(settings)
        calls = []

        def fake_create(**kwargs):
            calls.append(kwargs)
            return {"data": [{"embedding": [0.0] * settings.embedding_dimensions}]}

        with patch.object(embeddings.client, "create", side_effect=fake_create):
            vector = embeddings.embed_query("The merchant sells a katana.")

        self.assertEqual(len(vector), settings.embedding_dimensions)
        self.assertEqual(calls[0]["input"], ["The merchant sells a katana."])


if __name__ == "__main__":
    unittest.main()
