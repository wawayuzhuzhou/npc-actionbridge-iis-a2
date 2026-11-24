from pathlib import Path

from fastapi import HTTPException

from adapter.qwen_baseline.contract import NPCAction, Response
from adapter.qwen_baseline.fastapi_app import create_app as create_baseline_app
from .store import OutcomeReport, ProposalStore


class ProposedResponse(Response):
    proposal_id: str
    proposed_action: str
    proposal_status: str = "Pending"


class ProposalChain:
    def __init__(self, chain, store):
        self.chain, self.store = chain, store

    def invoke(self, context):
        raw = self.chain.invoke(context)
        if raw.action == NPCAction.NONE:
            return raw
        proposal = self.store.create(context, raw)
        # Baseline persistence receives truthful pending text, never the raw
        # completion-style claim. Raw output is retained in ActionProposals.
        return ProposedResponse(
            action=NPCAction.NONE, response=proposal["feedback"],
            proposal_id=proposal["proposal_id"], proposed_action=raw.action.value,
        )


def create_app(*, db_path: Path, chain, vector_store):
    store = ProposalStore(db_path)
    app = create_baseline_app(
        db_path=db_path, chain=ProposalChain(chain, store), vector_store=vector_store,
        on_conversation_saved=store.link_conversation,
    )
    app.state.proposals = store

    @app.post("/actionbridge/outcome")
    def save_outcome(report: OutcomeReport):
        try:
            event = store.finish(report)
        except KeyError:
            raise HTTPException(404, "Proposal not found for this player")
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"proposal_id": event["proposal_id"], "status": event["status"], "feedback": event["feedback"]}

    return app
