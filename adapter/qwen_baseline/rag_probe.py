from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from openai import APIError

from .config import QwenSettings
from .retrieval import load_faiss_store


QUERY = "How much does the katana cost?"
KATANA_FACT = "The merchant will sell a katana for 8 gold."


def _redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    return re.sub(r"sk-ws-[A-Za-z0-9_-]+", "[REDACTED]", value)


def format_matches(matches: list[tuple[object, object]]) -> list[dict[str, object]]:
    return [
        {
            "rank": rank,
            "fact": document.page_content,
            "score_or_distance": float(score),
        }
        for rank, (document, score) in enumerate(matches, start=1)
    ]


def build_success_result(
    *,
    settings: QwenSettings,
    matches: list[tuple[object, object]],
    latency_ms: float,
) -> dict[str, object]:
    top5 = format_matches(matches)
    katana_rank = next(
        (item["rank"] for item in top5 if item["fact"] == KATANA_FACT),
        None,
    )
    retrieval_status = "PASS" if katana_rank is not None else "FAIL"
    result = {
        "status": retrieval_status,
        "execution_status": "PASS",
        "evidence_serialization_status": "PENDING",
        "retrieval_correctness_status": retrieval_status,
        "query": QUERY,
        "retrieval_k": 5,
        "model": settings.embedding_model,
        "configured_dimensions": settings.embedding_dimensions,
        "request_count_expected": 1,
        "request_count_actual": 1,
        "automatic_retries": 0,
        "chat_requests": 0,
        "latency_ms": latency_ms,
        "score_semantics": "FAISS IndexFlatL2 squared L2 distance; smaller is closer",
        "top5": top5,
        "katana_8_gold_fact": KATANA_FACT,
        "katana_8_gold_retrieved": katana_rank is not None,
        "katana_8_gold_rank": katana_rank,
        "follow_up_requests": 0,
        "natural_language_queries_after_this_probe": 0,
    }
    json.dumps(result)
    result["evidence_serialization_status"] = "PASS"
    return result


def run_probe(*, output_path: Path, store_path: Path) -> None:
    settings = QwenSettings.from_environment()
    start = time.perf_counter()
    vector_store = load_faiss_store(settings=settings, store_path=store_path)
    matches = vector_store.similarity_search_with_score(QUERY, k=5)
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    result = build_success_result(
        settings=settings,
        matches=matches,
        latency_ms=latency_ms,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotenv", help="Optional local dotenv path")
    parser.add_argument(
        "--confirm-live-retrieval",
        action="store_true",
        help="Required explicit authorization for one retrieval request",
    )
    parser.add_argument(
        "--faiss-path",
        type=Path,
        default=Path("adapter/qwen_baseline/runtime/vector_store"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("audit_evidence/11_qwen_baseline/rag_probe.json"),
    )
    args = parser.parse_args()
    if not args.confirm_live_retrieval:
        parser.error("--confirm-live-retrieval is required")
    if args.dotenv:
        from dotenv import load_dotenv

        load_dotenv(args.dotenv, override=False)
    try:
        run_probe(output_path=args.output, store_path=args.faiss_path)
    except (APIError, OSError, RuntimeError, ValueError) as exc:
        safe_error = {
            "status": "ERROR",
            "execution_status": "ERROR",
            "evidence_serialization_status": "PASS",
            "retrieval_correctness_status": "NOT_EVALUATED",
            "query": QUERY,
            "retrieval_k": 5,
            "request_count_expected": 1,
            "request_count_actual": "unknown; inspect provider/network logs",
            "automatic_retries": 0,
            "chat_requests": 0,
            "follow_up_requests": 0,
            "error_type": type(exc).__name__,
            "error": _redact(str(exc))[:500],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(safe_error, indent=2) + "\n",
            encoding="utf-8",
        )
        raise
