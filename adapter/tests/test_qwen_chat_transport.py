import json
import unittest
from unittest.mock import patch

import httpx
from langchain_openai import ChatOpenAI

from adapter.qwen_baseline.backend import build_qwen_chain
from adapter.qwen_baseline.config import QwenSettings
from adapter.qwen_baseline.prompt import ORIGINAL_PROMPT_TEMPLATE


class ChatTransportTests(unittest.TestCase):
    def test_non_thinking_json_payload_uses_unchanged_prompt_without_network(self):
        calls = []

        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "offline-chat", "object": "chat.completion", "created": 0,
                "model": "qwen3.7-flash",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": '{"action":"none","response":"Hello."}',
                }}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            })

        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            def make_llm(**kwargs):
                return ChatOpenAI(**kwargs, http_client=client)

            with patch("langchain_openai.ChatOpenAI", side_effect=make_llm):
                settings = QwenSettings(
                    base_url="https://offline.invalid/v1", api_key="offline-key",
                    chat_model="qwen3.7-flash",
                )
                chain = build_qwen_chain(settings)
            context = dict(
                player_name="Test", npc_name="Mother", personality="Original personality",
                allowed_actions="none", world_facts="Original facts", chat_history="",
                held_items="0 Gold", player_input="Hello.",
            )
            result = chain.invoke(context)
        self.assertEqual(result.action.value, "none")
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["enable_thinking"])
        self.assertEqual(calls[0].get("max_completion_tokens", calls[0].get("max_tokens")), 1024)
        self.assertEqual(calls[0]["messages"][0]["content"], ORIGINAL_PROMPT_TEMPLATE.format(**context))
        self.assertEqual(calls[0]["response_format"]["type"], "json_object")


if __name__ == "__main__":
    unittest.main()
