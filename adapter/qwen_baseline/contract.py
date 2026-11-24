from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NPCAction(str, Enum):
    SELL_KATANA = "sell_katana"
    OPEN_DOOR = "open_door"
    NONE = "none"


class Query(BaseModel):
    player_name: str
    npc_name: str
    held_items: str
    player_input: str


class NameCheckQuery(BaseModel):
    player_name: str


class NameCheckResponse(BaseModel):
    available: bool


class Response(BaseModel):
    action: NPCAction = Field(description="The action the NPC takes")
    response: str = Field(description="What the NPC says")


def response_to_record(response: Response) -> dict[str, str]:
    """Serialize the original two-field response without adding gates."""
    return {"action": response.action.value, "response": response.response}
