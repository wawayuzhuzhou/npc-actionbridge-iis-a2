"""Paired E2 fixtures through real B/A APIs and copied Godot state functions.
No Qwen client is constructed. External Python socket connects are prohibited.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from adapter.actionbridge.api import create_app as create_a
from adapter.qwen_baseline.fastapi_app import create_app as create_b
from adapter.qwen_baseline.contract import Response
from adapter.qwen_baseline.retrieval import FixtureRetriever, load_world_facts


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Replay:
    def __init__(self, raw):
        self.raw, self.contexts = raw, []

    def invoke(self, context):
        self.contexts.append(context)
        return Response(**self.raw)


def prepare_copy(source, target):
    if target.exists():
        raise FileExistsError("Use a fresh disposable destination")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"))
    project = target / "project.godot"
    text = project.read_text(encoding="utf-8")
    import re
    text = re.sub(r'config/name="[^"]+"', 'config/name="PhaseII Offline Fixture"', text, count=1)
    project.write_text(text, encoding="utf-8")
    shutil.copy2(Path(__file__).with_name("state_fixture.gd"), target / "phase2_fixture.gd")


def main():
    p = argparse.ArgumentParser()
    for name in ("baseline-game", "enhanced-game", "seed-db", "godot", "work", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    work = args.work.resolve()
    if work.exists() or any(x.lower() == "upstream_frozen" for x in work.parts):
        raise ValueError("Use a new disposable work path outside frozen upstream")
    protected_before = sha(args.seed_db)
    matrix_path = Path(__file__).with_name("matrix.json")
    matrix = json.loads(matrix_path.read_text())
    historical = ROOT / "evidence/offline_action_fixture.json"
    raws = json.loads(historical.read_text(encoding="utf-8"))["actions"]
    work.mkdir(parents=True)
    games = {}
    for condition, source in (("B", args.baseline_game), ("A", args.enhanced_game)):
        games[condition] = work / condition / "game"
        prepare_copy(source.resolve(), games[condition])
    output = {
        "category": "E2 offline deterministic paired API/Godot fixtures",
        "time_utc": datetime.now(timezone.utc).isoformat(), "provider_requests": 0,
        "transport": "ASGI TestClient; external Python socket connects blocked, loopback wakeup sockets allowed; Godot receives file payloads",
        "matrix_sha256": sha(matrix_path),
        "sanitised_action_fixture": str(historical.relative_to(ROOT)),
        "sanitised_action_fixture_sha256": sha(historical),
        "injection_limitation": "Raw proposals from valid E3 states replayed under counterfactual states; not Qwen action-selection evidence.",
        "source_tree_hashes": {
            c: {f.relative_to(src).as_posix(): sha(f)
                for f in src.rglob("*") if f.is_file() and f.suffix in (".gd", ".tscn", ".godot")
                and ".godot" not in f.relative_to(src).parts}
            for c, src in (("B", args.baseline_game), ("A", args.enhanced_game))
        }, "cases": []
    }
    contexts, case_records = {}, {}
    original_connect = socket.socket.connect
    def local_only(sock, address):
        # Windows asyncio creates a loopback socket pair for its wakeup pipe.
        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "::1"):
            raise AssertionError("Offline: external network forbidden")
        return original_connect(sock, address)
    with patch.object(socket.socket, "connect", new=local_only):
        for case in matrix["cases"] + matrix["auxiliary_offline"]:
            records = {}
            for condition, factory in (("B", create_b), ("A", create_a)):
                family = "M2_G2" if case["id"] in ("M2", "G2") else case["id"]
                db = work / condition / (family + ".db")
                if not db.exists():
                    shutil.copy2(args.seed_db, db)
                raw, replay = raws[case["action"]], Replay(raws[case["action"]])
                app = factory(db_path=db, chain=replay, vector_store=FixtureRetriever(
                    load_world_facts(ROOT / "adapter/qwen_baseline/world_facts.txt")))
                query = {"player_name": matrix["player_name"], "npc_name": case["npc"],
                         "held_items": case["held_items"], "player_input": case["input"]}
                with TestClient(app) as client:
                    greeting = client.post("/get_latest_response", json=query)
                    assert greeting.status_code == 200
                    response = client.post("/get_response", json=query)
                    assert response.status_code == 200, response.text
                    payload = response.json()
                    assert len(replay.contexts) == 1
                    context = replay.contexts[0]
                    assert context["chat_history"] == "", context
                    contexts[case["id"], condition] = context
                    job = work / condition / (case["id"] + "_input.json")
                    result = work / condition / (case["id"] + "_state.json")
                    job.write_text(json.dumps({"condition": condition, "case": case, "response": payload}))
                    command = [str(args.godot), "--headless", "--path", str(games[condition]),
                               "--log-file", str(work / condition / (case["id"] + "_godot.log")),
                               "--script", "res://phase2_fixture.gd", "--", str(job), str(result)]
                    completed = subprocess.run(command, capture_output=True, timeout=45)
                    (work / condition / (case["id"] + "_stdout.txt")).write_bytes(completed.stdout + completed.stderr)
                    assert completed.returncode == 0 and result.exists(), completed.stdout + completed.stderr
                    state = json.loads(result.read_text())
                    expected_before = {k: case[k] for k in ("gold", "katana", "door_open")}
                    assert state["before"] == expected_before, state
                    assert state["after"] == case[condition + "_after"], state
                    outcome_http, proposal = None, None
                    if condition == "A":
                        assert state["status"] == case["A_status"], state
                        report = {"proposal_id": payload["proposal_id"], "player_name": matrix["player_name"],
                                  **{k: state[k] for k in ("status", "reason", "before", "after")}}
                        saved = client.post("/actionbridge/outcome", json=report)
                        outcome_http = saved.status_code
                        assert outcome_http == 200 and saved.json()["status"] == state["status"]
                        proposal = app.state.proposals.get(payload["proposal_id"])
                    with closing(sqlite3.connect(db)) as connection:
                        connection.row_factory = sqlite3.Row
                        row = dict(connection.execute(
                            "SELECT * FROM Conversations WHERE player_name=? AND npc_name=? ORDER BY id DESC LIMIT 1",
                            (matrix["player_name"], case["npc"])).fetchone())
                    expected_action = case["action"] if condition == "B" or state["status"] == "Committed" else "none"
                    assert row["npc_action"] == expected_action, row
                    records[condition] = {"generation_http": response.status_code,
                        "greeting_http": greeting.status_code, "greeting": greeting.json(),
                        "raw_injected": raw, "response": payload, "godot": state,
                        "outcome_http": outcome_http, "sqlite_conversation": row,
                        "sqlite_proposal": proposal, "context": context}
            assert contexts[case["id"], "B"] == contexts[case["id"], "A"]
            assert records["B"]["greeting"] == records["A"]["greeting"]
            output["cases"].append({"id": case["id"], "matched_context": True, "conditions": records})
            case_records[case["id"]] = records
        for c in ("B", "A"):
            assert case_records["M2"][c]["godot"]["after"] == case_records["G2"][c]["godot"]["before"]
    assert sha(args.seed_db) == protected_before
    output.update({"status": "PASS", "paired_cases": 6, "godot_executions": 12,
                   "seed_database_unchanged": True, "work": str(work)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({k: output[k] for k in ("status", "provider_requests", "paired_cases", "godot_executions")}))


if __name__ == "__main__":
    main()
