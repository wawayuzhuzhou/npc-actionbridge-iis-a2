import json
from types import SimpleNamespace
import unittest

import numpy as np

from adapter.qwen_baseline.rag_probe import (
    KATANA_FACT,
    build_success_result,
    format_matches,
)


class RagProbeTests(unittest.TestCase):
    settings = SimpleNamespace(
        embedding_model="text-embedding-v4",
        embedding_dimensions=1024,
    )

    def test_exact_katana_fact_is_a_true_positive_with_rank(self):
        matches = [
            (SimpleNamespace(page_content="Other fact."), np.float32(3.0)),
            (SimpleNamespace(page_content=KATANA_FACT), np.float32(1.25)),
        ]
        result = build_success_result(
            settings=self.settings,
            matches=matches,
            latency_ms=12.3,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["retrieval_correctness_status"], "PASS")
        self.assertTrue(result["katana_8_gold_retrieved"])
        self.assertEqual(result["katana_8_gold_rank"], 2)

    def test_missing_katana_fact_is_a_retrieval_failure(self):
        matches = [
            (SimpleNamespace(page_content="Other fact."), np.float32(3.0)),
        ]
        result = build_success_result(
            settings=self.settings,
            matches=matches,
            latency_ms=12.3,
        )
        self.assertEqual(result["execution_status"], "PASS")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["retrieval_correctness_status"], "FAIL")
        self.assertFalse(result["katana_8_gold_retrieved"])
        self.assertIsNone(result["katana_8_gold_rank"])

    def test_scores_are_native_floats_and_order_is_stable(self):
        matches = [
            (SimpleNamespace(page_content="First."), np.float32(0.5)),
            (SimpleNamespace(page_content="Second."), np.float32(1.5)),
        ]
        formatted = format_matches(matches)
        self.assertEqual([item["rank"] for item in formatted], [1, 2])
        self.assertEqual([item["fact"] for item in formatted], ["First.", "Second."])
        self.assertTrue(all(isinstance(item["score_or_distance"], float) for item in formatted))
        json.dumps(formatted)


if __name__ == "__main__":
    unittest.main()
