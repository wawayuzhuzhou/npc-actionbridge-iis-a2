import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adapter.qwen_baseline.config import ConfigurationError
from adapter.qwen_baseline.retrieval import build_faiss_store
from adapter.qwen_baseline.run import build_runtime_app, preflight_runtime


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "runtime.db"
        self.db_path.write_bytes(b"disposable")
        self.world_facts_path = root / "world_facts.txt"
        self.world_facts_path.write_text("A fact.\n", encoding="utf-8")
        self.store_path = root / "vector_store"
        self.previous = {
            key: os.environ.get(key)
            for key in (
                "A2_PROXY_BASE_URL",
                "A2_PROXY_API_KEY",
                "A2_PROXY_MODEL",
                "A2_UPSTREAM_DB_PATH",
                "A2_QWEN_WORLD_FACTS_PATH",
                "A2_QWEN_FAISS_PATH",
            )
        }
        os.environ.update(
            {
                "A2_PROXY_BASE_URL": "https://offline.invalid/v1",
                "A2_PROXY_API_KEY": "offline-only",
                "A2_PROXY_MODEL": "qwen3.7-flash",
                "A2_UPSTREAM_DB_PATH": str(self.db_path),
                "A2_QWEN_WORLD_FACTS_PATH": str(self.world_facts_path),
                "A2_QWEN_FAISS_PATH": str(self.store_path),
            }
        )

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_preflight_does_not_build_missing_index(self):
        result = preflight_runtime()
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["startup_ready"])
        self.assertFalse(result["faiss_index_present"])
        self.assertEqual(result["provider_requests"], 0)
        self.assertFalse(self.store_path.exists())

    def test_server_start_requires_existing_index(self):
        with patch("adapter.qwen_baseline.run.build_qwen_chain"):
            with self.assertRaises(ConfigurationError):
                build_runtime_app()
        self.assertFalse(self.store_path.exists())

    def test_build_refuses_non_empty_output_directory(self):
        self.store_path.mkdir()
        (self.store_path / "existing-index.faiss").write_bytes(b"preserve")
        settings = type(
            "Settings",
            (),
            {
                "embedding_dimensions": 1024,
                "embedding_model": "text-embedding-v4",
                "api_key": "offline-only",
                "base_url": "https://offline.invalid/v1",
            },
        )()
        with self.assertRaises(ConfigurationError):
            build_faiss_store(
                settings=settings,
                world_facts_path=self.world_facts_path,
                store_path=self.store_path,
            )
        self.assertEqual(
            (self.store_path / "existing-index.faiss").read_bytes(),
            b"preserve",
        )


if __name__ == "__main__":
    unittest.main()
