"""Phase-II-only, durable case admission and provider-dispatch ceilings.

Never imports a model client or initiates gameplay. Failed/uncertain dispatches
remain counted; admission and dispatch are separate from provider billing.
"""
import argparse
from contextlib import closing
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import httpx

ACTIVE_ATTEMPT = ContextVar("phase2_budget_attempt", default=None)
CAPS = {"A": 8, "B": 2}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normal(path):
    return os.path.normcase(str(Path(path).resolve()))


def specification(case, condition):
    matrix = json.loads(Path(__file__).with_name("matrix.json").read_text())
    if case in ("CANCEL", "FOLLOWUP") and condition == "A":
        return dict(stage="B", npc="Merchant", held="8 Gold",
                    text="I want to buy the katana." if case == "CANCEL" else "Do I own the Katana now?")
    for row in matrix["cases"]:
        if row["id"] == case and condition in ("A", "B"):
            return dict(stage="A", npc=row["npc"], held=row["held_items"], text=row["input"])
    raise Denied("unregistered_case_or_condition", 403)


class Denied(RuntimeError):
    def __init__(self, reason, status=409):
        super().__init__(reason)
        self.reason, self.status = reason, status


class Budget:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def connect(self):
        if not self.path.is_file():
            raise Denied("budget_ledger_missing", 503)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    @classmethod
    def initialise(cls, path, authorisation, audit, manifest):
        path = Path(path).resolve()
        auth, prior, scope = [json.loads(Path(p).read_text()) for p in (authorisation, audit, manifest)]
        if auth["combined"] != {"embedding_max": 10, "chat_max": 10} or auth["Stage_C_authorised"]:
            raise ValueError("Expected the existing 10+10 authorisation, excluding Stage C")
        if (auth["Stage_A"]["embedding_max"], auth["Stage_A"]["chat_max"],
            auth["Stage_B"]["additional_embedding_max"], auth["Stage_B"]["additional_chat_max"]) != (8, 8, 2, 2):
            raise ValueError("Stage allocation must remain A=8+8, B=2+2")
        if prior["observed_embedding_client_paths"] or prior["observed_chat_client_paths"]:
            raise ValueError("Existing requests need reconciliation; zero-use initialisation refused")
        if len(scope["cases"]) != 10 or len({(r["case"], r["condition"]) for r in scope["cases"]}) != 10:
            raise ValueError("Expected exactly ten registered case/condition slots")
        for row in scope["cases"]:
            specification(row["case"], row["condition"])
        if any(p.lower() == "upstream_frozen" for p in path.parts):
            raise ValueError("Budget ledger must be outside frozen upstream")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb"):  # Never reset an existing allowance.
            pass
        budget = cls(path)
        with closing(budget.connect()) as db, db:
            db.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE scopes(case_id TEXT, condition TEXT, game_db TEXT NOT NULL,
                    PRIMARY KEY(case_id,condition));
                CREATE TABLE attempts(id TEXT PRIMARY KEY, stage TEXT NOT NULL,
                    case_id TEXT NOT NULL, condition TEXT NOT NULL, admitted_at TEXT NOT NULL,
                    finished_http INTEGER, UNIQUE(case_id,condition));
                CREATE TABLE dispatches(id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL,
                    kind TEXT CHECK(kind IN ('embedding','chat')), reserved_at TEXT NOT NULL,
                    http_status INTEGER, error_type TEXT, UNIQUE(attempt_id,kind));
                CREATE TABLE denials(time_utc TEXT, case_id TEXT, condition TEXT, reason TEXT);
            """)
            values = {"caps": CAPS, "combined": 10, "stage_b_enabled": False,
                      "authorisation_sha256": digest(authorisation), "prior_audit_sha256": digest(audit),
                      "manifest_sha256": digest(manifest),
                      "matrix_sha256": digest(Path(__file__).with_name("matrix.json"))}
            db.executemany("INSERT INTO metadata VALUES (?,?)",
                           [(k, json.dumps(v)) for k, v in values.items()])
            db.executemany("INSERT INTO scopes VALUES (?,?,?)",
                           [(r["case"], r["condition"], normal(r["db"])) for r in scope["cases"]])
        return budget

    def validate(self, case, condition, game_db):
        specification(case, condition)
        with closing(self.connect()) as db:
            meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM metadata")}
            if meta["caps"] != CAPS or meta["combined"] != 10:
                raise Denied("budget_configuration_changed", 503)
            if meta["matrix_sha256"] != digest(Path(__file__).with_name("matrix.json")):
                raise Denied("registration_fingerprint_changed", 503)
            row = db.execute("SELECT game_db FROM scopes WHERE case_id=? AND condition=?",
                             (case, condition)).fetchone()
            if row is None or row["game_db"] != normal(game_db):
                raise Denied("case_database_mismatch", 403)

    def deny(self, case, condition, reason, query=None, status=409):
        with closing(self.connect()) as db, db:
            detail = json.dumps({"reason": reason, "http_status": status, "request": query}, ensure_ascii=True)
            db.execute("INSERT INTO denials VALUES (?,?,?,?)", (now(), case, condition, detail))

    def admit(self, case, condition, game_db, query):
        self.validate(case, condition, game_db)
        spec = specification(case, condition)
        expected = {"player_name": "PhaseIIPlayer", "npc_name": spec["npc"],
                    "held_items": spec["held"], "player_input": spec["text"]}
        if query != expected:
            raise Denied("request_differs_from_registered_case", 403)
        # This checks reported context/history, not hidden authoritative inventory.
        with closing(sqlite3.connect(f"file:{Path(game_db).resolve().as_posix()}?mode=ro", uri=True)) as game:
            rows = game.execute("SELECT id,npc_action FROM Conversations WHERE player_name=? AND npc_name=?",
                                ("PhaseIIPlayer", spec["npc"])).fetchall()
            if case == "FOLLOWUP":
                if len(rows) != 1:
                    raise Denied("cancellation_history_prerequisite_missing", 403)
                proposal = game.execute(
                    "SELECT status FROM ActionProposals WHERE conversation_id=?", (rows[0][0],)).fetchone()
                if proposal is None or proposal[0] != "Cancelled":
                    raise Denied("actual_persisted_cancellation_required", 403)
            elif rows:
                raise Denied("target_npc_history_not_fresh", 403)
            if case == "G2" and game.execute(
                "SELECT COUNT(*) FROM Conversations WHERE player_name=? AND npc_name='Merchant' AND npc_action='sell_katana'",
                ("PhaseIIPlayer",)).fetchone()[0] != 1:
                raise Denied("registered_purchase_prerequisite_missing", 403)
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            meta = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM metadata")}
            if spec["stage"] == "B" and not meta["stage_b_enabled"]:
                raise Denied("stage_b_not_released_after_review", 403)
            if db.execute("SELECT 1 FROM attempts WHERE case_id=? AND condition=?", (case, condition)).fetchone():
                raise Denied("case_already_admitted_no_retry")
            if db.execute("SELECT COUNT(*) FROM attempts WHERE stage=?", (spec["stage"],)).fetchone()[0] >= CAPS[spec["stage"]]:
                raise Denied("stage_attempt_ceiling", 429)
            if db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] >= 10:
                raise Denied("combined_attempt_ceiling", 429)
            attempt = uuid4().hex
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,NULL)",
                       (attempt, spec["stage"], case, condition, now()))
            db.commit()
            return attempt

    def reserve_dispatch(self, kind):
        attempt = ACTIVE_ATTEMPT.get()
        if attempt is None:
            raise Denied("provider_call_without_admitted_player_request", 403)
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM attempts WHERE id=?", (attempt,)).fetchone()
            if row is None or row["finished_http"] is not None:
                raise Denied("attempt_not_active")
            if db.execute("SELECT 1 FROM dispatches WHERE attempt_id=? AND kind=?", (attempt, kind)).fetchone():
                raise Denied("duplicate_provider_dispatch_no_retry")
            if kind == "chat" and not db.execute(
                "SELECT 1 FROM dispatches WHERE attempt_id=? AND kind='embedding' AND http_status=200",
                (attempt,)).fetchone():
                raise Denied("successful_embedding_dispatch_required")
            if db.execute("SELECT COUNT(*) FROM dispatches WHERE kind=?", (kind,)).fetchone()[0] >= 10:
                raise Denied("provider_kind_ceiling", 429)
            count = db.execute(
                "SELECT COUNT(*) FROM dispatches d JOIN attempts a ON a.id=d.attempt_id WHERE a.stage=? AND d.kind=?",
                (row["stage"], kind)).fetchone()[0]
            if count >= CAPS[row["stage"]]:
                raise Denied("stage_provider_kind_ceiling", 429)
            call = uuid4().hex
            db.execute("INSERT INTO dispatches VALUES (?,?,?,?,NULL,NULL)", (call, attempt, kind, now()))
            db.commit()
            return call

    def finish_dispatch(self, call, status=None, error=None):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE dispatches SET http_status=?,error_type=? WHERE id=?",
                       (status, error, call))

    def finish_attempt(self, attempt, http_status):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE attempts SET finished_http=? WHERE id=? AND finished_http IS NULL",
                       (http_status, attempt))

    def enable_stage_b(self, review):
        if not Path(review).is_file() or not Path(review).read_text(encoding="utf-8").strip():
            raise ValueError("A saved Stage A assessment is required")
        with closing(self.connect()) as db, db:
            db.execute("UPDATE metadata SET value='true' WHERE key='stage_b_enabled'")
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('stage_a_review',?)",
                       (json.dumps({"path": normal(review), "sha256": digest(review), "recorded_at": now()}),))

    def status(self):
        if not self.path.is_file():
            raise Denied("budget_ledger_missing", 503)
        with closing(sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            attempts = [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY admitted_at")]
            calls = [dict(r) for r in db.execute("SELECT * FROM dispatches ORDER BY reserved_at")]
            enabled = json.loads(db.execute("SELECT value FROM metadata WHERE key='stage_b_enabled'").fetchone()[0])
        return {"stage_caps_per_kind": CAPS, "combined_cap_per_kind": 10,
                "admitted_cases": attempts, "transport_dispatch_reservations": calls,
                "remaining_case_admissions": {s: CAPS[s]-sum(x["stage"]==s for x in attempts) for s in CAPS},
                "transport_reserved_per_kind": {k: sum(x["kind"]==k for x in calls) for k in ("embedding","chat")},
                "remaining_transport_ceiling": {k: 10-sum(x["kind"]==k for x in calls) for k in ("embedding","chat")},
                "stage_b_enabled": enabled, "provider_billing": "Not established by local dispatch records",
                "failure_policy": "Admissions/dispatch reservations survive failures and restart; no retry or reallocation"}


class BudgetTransport(httpx.BaseTransport):
    def __init__(self, budget, delegate=None):
        self.budget, self.delegate = budget, delegate or httpx.HTTPTransport(retries=0)

    def handle_request(self, request):
        kind = {"/embeddings": "embedding", "/chat/completions": "chat"}
        found = next((v for p, v in kind.items() if request.url.path.endswith(p)), None)
        if request.method != "POST" or found is None:
            raise Denied("unregistered_provider_endpoint", 403)
        call = self.budget.reserve_dispatch(found)
        try:
            response = self.delegate.handle_request(request)
        except Exception as exc:
            self.budget.finish_dispatch(call, error=type(exc).__name__)
            raise
        self.budget.finish_dispatch(call, status=response.status_code)
        return response

    def close(self):
        self.delegate.close()


class NoAsyncProvider(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise Denied("async_provider_route_disabled_in_sync_phase2_runtime", 403)


def install(app, budget, case, condition, game_db):
    from starlette.responses import JSONResponse
    budget.validate(case, condition, game_db)

    @app.middleware("http")
    async def guard(request, call_next):
        if request.method != "POST" or request.url.path != "/get_response":
            return await call_next(request)
        query = None
        try:
            query = await request.json()
            attempt = budget.admit(case, condition, game_db, query)
        except Denied as exc:
            budget.deny(case, condition, exc.reason, query, exc.status)
            return JSONResponse({"phase2_guard": exc.reason, "provider_contacted": False}, status_code=exc.status)
        except (ValueError, TypeError, sqlite3.Error):
            budget.deny(case, condition, "invalid_request_or_unverifiable_history", query, 403)
            return JSONResponse({"phase2_guard": "invalid_request_or_unverifiable_history",
                                 "provider_contacted": False}, status_code=403)
        token = ACTIVE_ATTEMPT.set(attempt)
        try:
            response = await call_next(request)
            budget.finish_attempt(attempt, response.status_code)
            response.headers["X-Phase2-Attempt-ID"] = attempt
            return response
        except Exception:
            budget.finish_attempt(attempt, 500)
            raise
        finally:
            ACTIVE_ATTEMPT.reset(token)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=("init", "status", "enable-stage-b"))
    p.add_argument("--db", type=Path, required=True)
    for name in ("authorisation", "audit", "manifest", "review"):
        p.add_argument("--" + name, type=Path)
    args = p.parse_args()
    if args.operation == "init":
        if not all((args.authorisation, args.audit, args.manifest)):
            p.error("init requires authorisation, audit and manifest")
        budget = Budget.initialise(args.db, args.authorisation, args.audit, args.manifest)
    else:
        budget = Budget(args.db)
        if args.operation == "enable-stage-b":
            if args.review is None:
                p.error("enable-stage-b requires --review")
            budget.enable_stage_b(args.review)
    print(json.dumps(budget.status(), indent=2))
