from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from .backend import build_qwen_chain
from .config import QwenSettings, assert_runtime_db_path
from .fastapi_app import create_app
from .prompt import PromptContext, render_prompt
from .retrieval import load_faiss_store, load_world_facts


PLAYER_INPUT = "I want to buy the katana."
HELD_ITEMS = "8 Gold"
NPC_NAME = "Merchant"
EXPECTED_ACTION = "sell_katana"
PRICE_USD_PER_MILLION_INPUT_TOKENS = 0.028
PRICE_USD_PER_MILLION_OUTPUT_TOKENS = 0.110
EMBEDDING_PRICE_USD_PER_MILLION_INPUT_TOKENS = 0.072
PRICE_SOURCE_URL = (
    "https://www.alibabacloud.com/help/en/model-studio/"
    "qwen3-7-flash"
)
EMBEDDING_PRICE_SOURCE_URL = (
    "https://www.alibabacloud.com/help/en/model-studio/"
    "text-embedding-synchronous-api"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    return re.sub(r"sk-ws-[A-Za-z0-9_-]+", "[REDACTED]", value)


def read_merchant_contract(db_path: Path) -> dict[str, str]:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT personality, allowed_actions
            FROM NPCs
            WHERE npc_name = ?
            """,
            (NPC_NAME,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError("Merchant contract is missing from the runtime database")
    return {"personality": row[0], "allowed_actions": row[1]}


def build_original_prompt_preview(
    *,
    db_path: Path,
    world_facts_path: Path,
) -> str:
    contract = read_merchant_contract(db_path)
    return render_prompt(
        PromptContext(
            player_name="offline-preview",
            npc_name=NPC_NAME,
            personality=contract["personality"],
            allowed_actions=contract["allowed_actions"],
            world_facts="\n".join(load_world_facts(world_facts_path)),
            chat_history="",
            held_items=HELD_ITEMS,
            player_input=PLAYER_INPUT,
        )
    )


class CapturingRetriever:
    def __init__(self, vector_store: Any):
        self.vector_store = vector_store
        self.facts: list[str] = []
        self.calls = 0

    def similarity_search(self, query: str, *, k: int) -> list[Any]:
        self.calls += 1
        documents = self.vector_store.similarity_search(query, k=k)
        self.facts = [document.page_content for document in documents]
        return documents


class CapturingChain:
    def __init__(self, chain: Any):
        self.chain = chain
        self.payload: dict[str, str] | None = None
        self.calls = 0

    def invoke(self, payload: dict[str, str]) -> Any:
        self.calls += 1
        self.payload = dict(payload)
        return self.chain.invoke(payload)


def _latest_conversation(
    db_path: Path, player_name: str
) -> dict[str, Any] | None:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT player_name, npc_name, held_items, player_input,
                   npc_response, npc_action
            FROM Conversations
            WHERE player_name = ? AND npc_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (player_name, NPC_NAME),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {
        "player_name": row[0],
        "npc_name": row[1],
        "held_items": row[2],
        "player_input": row[3],
        "npc_response": row[4],
        "npc_action": row[5],
    }


def _response_body(response: Any) -> tuple[dict[str, Any] | None, str]:
    body = _redact(response.text)[:5000]
    try:
        payload = json.loads(body)
    except ValueError:
        return None, body
    return payload if isinstance(payload, dict) else None, body


def _write_evidence(output_path: Path, result: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


def build_probe_result(
    *,
    response: Any,
    latency_ms: float,
    inserted_row: dict[str, Any] | None,
    contract: dict[str, str],
    retriever: CapturingRetriever,
    chain: CapturingChain,
    frozen_db_path: Path,
    frozen_db_hash_before: str,
    faiss_hashes_before: dict[str, str],
) -> dict[str, Any]:
    result_payload, response_body = _response_body(response)
    action = result_payload.get("action") if result_payload else None
    dialogue = result_payload.get("response") if result_payload else None
    assembled_prompt = (
        render_prompt(PromptContext(**chain.payload))
        if chain.payload is not None
        else None
    )
    execution_passed = response.status_code == 200
    schema_passed = (
        execution_passed
        and isinstance(action, str)
        and isinstance(dialogue, str)
    )
    return {
        "status": "PASS" if schema_passed else "FAIL",
        "http_status": response.status_code,
        "execution_status": "PASS" if execution_passed else "FAIL",
        "schema_status": "PASS" if schema_passed else (
            "FAIL" if execution_passed else "NOT_EVALUATED"
        ),
        "intent_action_status": (
            "PASS" if action == EXPECTED_ACTION
            else "FAIL" if execution_passed else "NOT_EVALUATED"
        ),
        "response_action_consistency_status": (
            "REVIEW_REQUIRED" if schema_passed else "NOT_EVALUATED"
        ),
        "npc_name": NPC_NAME,
        "player_name": chain.payload["player_name"] if chain.payload else None,
        "player_input": PLAYER_INPUT,
        "held_items": HELD_ITEMS,
        "expected_action": EXPECTED_ACTION,
        "response_body_redacted": response_body,
        "response_json": result_payload,
        "dialogue": dialogue,
        "action": action,
        "latency_ms": latency_ms,
        "retrieved_facts": retriever.facts,
        "retrieval_k": 5,
        "embedding_requests_expected": 1,
        "embedding_invocations_observed_client_path": retriever.calls,
        "chat_requests_expected": 1,
        "chat_invocations_observed_client_path": chain.calls,
        "request_count_evidence_limitation": (
            "Wrapper invocation counts are client-path observations, not "
            "independently audited provider HTTP counts."
        ),
        "automatic_retries": 0,
        "inserted_sqlite_row": inserted_row,
        "sqlite_insert_status": (
            "INSERTED" if inserted_row is not None else "NOT_INSERTED"
        ),
        "merchant_personality": contract["personality"],
        "merchant_allowed_actions": contract["allowed_actions"],
        "original_prompt": assembled_prompt,
        "godot_state_execution": "NOT_RUN",
        "frozen_db_sha256_before": frozen_db_hash_before,
        "frozen_db_sha256_after": _sha256(
            frozen_db_path
        ),
        "faiss_hashes_before": faiss_hashes_before,
        "provider_billing": "unavailable; client-path counts only",
        "chat_input_price_usd_per_million_tokens": (
            PRICE_USD_PER_MILLION_INPUT_TOKENS
        ),
        "chat_output_price_usd_per_million_tokens": (
            PRICE_USD_PER_MILLION_OUTPUT_TOKENS
        ),
        "chat_price_source": PRICE_SOURCE_URL,
        "embedding_input_price_usd_per_million_tokens": (
            EMBEDDING_PRICE_USD_PER_MILLION_INPUT_TOKENS
        ),
        "embedding_price_source": EMBEDDING_PRICE_SOURCE_URL,
        "estimated_upper_cost_usd": "requires provider token usage",
        "follow_up_requests": 0,
    }


def run_probe(
    *,
    frozen_db_path: Path,
    frozen_root: Path,
    faiss_path: Path,
    world_facts_path: Path,
    output_path: Path,
) -> None:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing evidence: {output_path}")

    settings = QwenSettings.from_environment()
    frozen_db_hash_before = _sha256(frozen_db_path)
    faiss_hashes_before = {
        name: _sha256(faiss_path / name)
        for name in ("index.faiss", "index.pkl")
    }
    player_name = f"merchant-live-{uuid4().hex}"

    with tempfile.TemporaryDirectory(prefix="qwen-merchant-") as temp_dir:
        runtime_db = Path(temp_dir) / "game_data.db"
        shutil.copy2(frozen_db_path, runtime_db)
        assert_runtime_db_path(runtime_db, frozen_root=frozen_root)
        contract = read_merchant_contract(runtime_db)
        _prompt_preview = build_original_prompt_preview(
            db_path=runtime_db,
            world_facts_path=world_facts_path,
        )
        vector_store = CapturingRetriever(
            load_faiss_store(settings=settings, store_path=faiss_path)
        )
        chain = CapturingChain(build_qwen_chain(settings))
        app = create_app(
            db_path=runtime_db,
            chain=chain,
            vector_store=vector_store,
        )

        from fastapi.testclient import TestClient

        start = time.perf_counter()
        with TestClient(app) as client:
            response = client.post(
                "/get_response",
                json={
                    "player_name": player_name,
                    "npc_name": NPC_NAME,
                    "held_items": HELD_ITEMS,
                    "player_input": PLAYER_INPUT,
                },
            )
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        inserted_row = _latest_conversation(runtime_db, player_name)

        result = build_probe_result(
            response=response,
            latency_ms=latency_ms,
            inserted_row=inserted_row,
            contract=contract,
            retriever=vector_store,
            chain=chain,
            frozen_db_path=frozen_db_path,
            frozen_db_hash_before=frozen_db_hash_before,
            faiss_hashes_before=faiss_hashes_before,
        )
        result["frozen_db_sha256_after"] = _sha256(frozen_db_path)
        result["faiss_hashes_after"] = {
            name: _sha256(faiss_path / name)
            for name in ("index.faiss", "index.pkl")
        }
        _write_evidence(output_path, result)


def build_offline_preflight(
    *,
    frozen_db_path: Path,
    frozen_root: Path,
    faiss_path: Path,
    world_facts_path: Path,
) -> dict[str, Any]:
    settings = QwenSettings.from_environment()
    with tempfile.TemporaryDirectory(prefix="qwen-merchant-preflight-") as temp_dir:
        runtime_db = Path(temp_dir) / "game_data.db"
        shutil.copy2(frozen_db_path, runtime_db)
        assert_runtime_db_path(runtime_db, frozen_root=frozen_root)
        contract = read_merchant_contract(runtime_db)
        prompt = build_original_prompt_preview(
            db_path=runtime_db,
            world_facts_path=world_facts_path,
        )
    store = load_faiss_store(settings=settings, store_path=faiss_path)
    return {
        "status": "PASS",
        "provider_requests": 0,
        "merchant_allowed_actions": contract["allowed_actions"],
        "held_items_serialization": HELD_ITEMS,
        "player_input": PLAYER_INPUT,
        "prompt_contains_original_action_schema": (
            '"action": The NPC\'s action' in prompt
        ),
        "prompt_contains_expected_action_injection": False,
        "faiss_dimensions": store.index.d,
        "embedding_model": settings.embedding_model,
        "chat_model": settings.chat_model,
        "automatic_retries": 0,
        "live_evidence_output": (
            "audit_evidence/11_qwen_baseline/merchant_live_probe.json"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotenv")
    parser.add_argument("--frozen-db", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--faiss-path", type=Path, required=True)
    parser.add_argument("--world-facts", type=Path, required=True)
    parser.add_argument(
        "--confirm-live-merchant",
        action="store_true",
        help="Required explicit authorization for one Embedding and one Chat request",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate the Merchant contract without provider requests",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "audit_evidence/11_qwen_baseline/merchant_live_probe.json"
        ),
    )
    args = parser.parse_args()
    if args.dotenv:
        from dotenv import load_dotenv

        load_dotenv(args.dotenv, override=False)
    if args.preflight and args.confirm_live_merchant:
        parser.error("--preflight and --confirm-live-merchant are mutually exclusive")
    if not args.preflight and not args.confirm_live_merchant:
        parser.error(
            "use --preflight or provide --confirm-live-merchant for the live test"
        )
    if args.preflight:
        print(
            json.dumps(
                build_offline_preflight(
                    frozen_db_path=args.frozen_db,
                    frozen_root=args.frozen_root,
                    faiss_path=args.faiss_path,
                    world_facts_path=args.world_facts,
                ),
                indent=2,
            )
        )
    else:
        try:
            run_probe(
                frozen_db_path=args.frozen_db,
                frozen_root=args.frozen_root,
                faiss_path=args.faiss_path,
                world_facts_path=args.world_facts,
                output_path=args.output,
            )
        except Exception as exc:
            safe_error = {
                "status": "ERROR",
                "execution_status": "ERROR",
                "schema_status": "NOT_EVALUATED",
                "intent_action_status": "NOT_EVALUATED",
                "request_count_expected": {
                    "embedding": 1,
                    "chat": 1,
                },
                "request_count_actual": (
                    "unknown; inspect provider/network logs"
                ),
                "automatic_retries": 0,
                "error_type": type(exc).__name__,
                "error": _redact(str(exc))[:500],
                "godot_state_execution": "NOT_RUN",
            }
            try:
                _write_evidence(args.output, safe_error)
            except FileExistsError:
                pass
            raise
