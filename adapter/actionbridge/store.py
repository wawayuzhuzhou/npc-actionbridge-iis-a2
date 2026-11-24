from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from adapter.qwen_baseline.config import assert_runtime_db_path


class GameSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    gold: int = Field(ge=0)
    katana: bool
    door_open: bool | None = None


class OutcomeReport(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    proposal_id: str
    player_name: str
    status: Literal["Cancelled", "Rejected", "Committed", "Failed"]
    before: GameSnapshot
    after: GameSnapshot
    reason: str = Field(default="", max_length=120)


class ProposalStore:
    """Persist proposals separately; only Godot execution reports become history.

    Godot is the trusted single-player authority. This is not a server-owned
    inventory or protection against a malicious client forging state reports.
    """

    def __init__(self, db_path: Path):
        self.path = assert_runtime_db_path(db_path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS ActionProposals (
                proposal_id TEXT PRIMARY KEY, player_name TEXT NOT NULL,
                npc_name TEXT NOT NULL, action TEXT NOT NULL,
                raw_response TEXT NOT NULL, context_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN
                    ('Pending','Cancelled','Rejected','Committed','Failed')),
                feedback TEXT NOT NULL, conversation_id INTEGER,
                before_json TEXT, after_json TEXT, reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")

    def create(self, context, response):
        proposal_id = uuid4().hex
        action = response.action.value
        feedback = (
            "Proposed purchase: Katana for 8 Gold. Awaiting your decision; no purchase has happened."
            if action == "sell_katana" else
            "Proposed action: open the dojo door. Awaiting validation and your decision."
        )
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""INSERT INTO ActionProposals
                (proposal_id,player_name,npc_name,action,raw_response,context_json,status,feedback)
                VALUES (?,?,?,?,?,?,'Pending',?)""", (
                proposal_id, context["player_name"], context["npc_name"], action,
                response.model_dump_json(), json.dumps(context), feedback,
            ))
        return self.get(proposal_id)

    def get(self, proposal_id):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM ActionProposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        return dict(row)

    def link_conversation(self, conversation_id, response):
        proposal_id = getattr(response, "proposal_id", None)
        if proposal_id:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("UPDATE ActionProposals SET conversation_id=? WHERE proposal_id=?",
                           (conversation_id, proposal_id))

    @staticmethod
    def _verified(event, before, after):
        allowed = event["action"] in json.loads(event["context_json"])["allowed_actions"].split(",")
        if not allowed:
            return False
        if event["npc_name"] == "Merchant" and event["action"] == "sell_katana":
            return (before.gold >= 8 and not before.katana and after.katana
                    and after.gold == before.gold - 8 and after.door_open == before.door_open)
        if event["npc_name"] == "Guard" and event["action"] == "open_door":
            return (before.katana and after.katana and before.door_open is False
                    and after.door_open is True and before.gold == after.gold)
        return False

    @staticmethod
    def _feedback(event, status, after, reason):
        state = f"Current state: {after.gold} Gold; Katana: {'yes' if after.katana else 'no'}."
        if status == "Committed":
            return (f"Purchase completed: 8 Gold paid and Katana received. {state}"
                    if event["action"] == "sell_katana" else "The dojo door is now open. You may enter.")
        if status == "Cancelled":
            return f"Action cancelled; it was not executed. {state} You may make a new request when ready."
        hints = {
            "insufficient_gold": "Collect enough gold to reach 8 Gold, then ask to buy the Katana.",
            "no_katana": "Obtain a Katana from the Merchant, then return to the Guard.",
            "already_has_katana": "You already have a Katana; you can go to the dojo.",
            "door_unavailable": "Return to the dojo entrance before asking to enter.",
            "door_already_open": "The door is already open; you can enter.",
            "wrong_npc_action": "Ask the Merchant about a purchase or the Guard about entry.",
        }
        return f"Action {status.lower()}; no successful execution is confirmed. {state} " + hints.get(
            reason, "Check the current state before making another request.")

    def finish(self, report: OutcomeReport):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM ActionProposals WHERE proposal_id=? AND player_name=?",
                             (report.proposal_id, report.player_name)).fetchone()
            if row is None:
                raise KeyError(report.proposal_id)
            event = dict(row)
            status, reason = report.status, report.reason
            if status == "Committed" and not self._verified(event, report.before, report.after):
                status, reason = "Failed", "unverified_execution"
            before = json.dumps(report.before.model_dump(), sort_keys=True)
            after = json.dumps(report.after.model_dump(), sort_keys=True)
            if event["status"] != "Pending":
                if (event["status"], event["before_json"], event["after_json"], event["reason"]) != (
                    status, before, after, reason
                ):
                    raise ValueError("A terminal proposal cannot be changed or executed again")
                return event
            if event["conversation_id"] is None:
                raise ValueError("Proposal conversation is not yet linked; retry saving the same outcome")
            feedback = self._feedback(event, status, report.after, reason)
            db.execute("""UPDATE ActionProposals SET status=?,feedback=?,before_json=?,after_json=?,
                       reason=?,updated_at=CURRENT_TIMESTAMP WHERE proposal_id=?""",
                       (status, feedback, before, after, reason, report.proposal_id))
            db.execute("UPDATE Conversations SET npc_response=?,npc_action=? WHERE id=?", (
                feedback, event["action"] if status == "Committed" else "none", event["conversation_id"],
            ))
        return self.get(report.proposal_id)
