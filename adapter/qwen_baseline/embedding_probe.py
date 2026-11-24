from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from openai import APIError

from .config import QwenSettings
from .retrieval import _create_embeddings


PRICE_USD_PER_MILLION_INPUT_TOKENS = 0.072
PRICE_SOURCE_URL = (
    "https://www.alibabacloud.com/help/en/model-studio/"
    "text-embedding-synchronous-api"
)


def _redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    return re.sub(r"sk-ws-[A-Za-z0-9_-]+", "[REDACTED]", value)


def run_probe(*, output_path: Path, text: str, max_input_tokens: int) -> None:
    settings = QwenSettings.from_environment()
    embeddings = _create_embeddings(settings)
    vector = embeddings.embed_query(text)
    result = {
        "status": "PASS",
        "request_count_expected": 1,
        "request_count_actual": 1,
        "model": settings.embedding_model,
        "configured_dimensions": settings.embedding_dimensions,
        "returned_dimensions": len(vector),
        "input_text": text,
        "price_usd_per_million_input_tokens": PRICE_USD_PER_MILLION_INPUT_TOKENS,
        "estimated_upper_cost_usd": (
            max_input_tokens * PRICE_USD_PER_MILLION_INPUT_TOKENS / 1_000_000
        ),
        "max_input_tokens_for_estimate": max_input_tokens,
        "price_source": PRICE_SOURCE_URL,
        "automatic_retries": 0,
        "follow_up_requests": 0,
    }
    if len(vector) != settings.embedding_dimensions:
        result["status"] = "FAIL"
        result["error"] = "Returned vector length does not match configured dimensions"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotenv", help="Optional local dotenv path")
    parser.add_argument(
        "--confirm-live-embedding",
        action="store_true",
        help="Required explicit authorization for the single provider request",
    )
    parser.add_argument(
        "--text",
        default="The merchant sells a katana for 8 gold.",
    )
    parser.add_argument(
        "--max-input-tokens",
        type=int,
        default=8192,
        help="Conservative cost-estimate ceiling for one input string",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("audit_evidence/11_qwen_baseline/embedding_probe.json"),
    )
    args = parser.parse_args()
    if not args.confirm_live_embedding:
        parser.error("--confirm-live-embedding is required")
    if args.max_input_tokens < 1 or args.max_input_tokens > 8192:
        parser.error("--max-input-tokens must be between 1 and 8192")
    if args.dotenv:
        from dotenv import load_dotenv

        load_dotenv(args.dotenv, override=False)
    try:
        run_probe(
            output_path=args.output,
            text=args.text,
            max_input_tokens=args.max_input_tokens,
        )
    except (APIError, OSError, RuntimeError, ValueError) as exc:
        safe_error = {
            "status": "ERROR",
            "request_count_expected": 1,
            "request_count_actual": "unknown; inspect provider/network logs",
            "automatic_retries": 0,
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
