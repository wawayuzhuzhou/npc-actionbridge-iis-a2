from __future__ import annotations

from dataclasses import dataclass


ORIGINAL_PROMPT_TEMPLATE = """
    You are a conversational NPC in an RPG. Your task is to respond to the player's inputs based on your personality, backstory, and the world facts provided.
    **Respond only as the NPC**—do not include the player's dialogue or assume the player's perspective.
    Keep responses concise, matching the typical dialogue style of RPGs. Use the context from the chat history and world facts when crafting your response.
    When you perform an action (for example, "sell_katana"), include a clear statement in your dialogue that indicates the action. For example, if your action is "sell_katana", your response should include a phrase like "Here is your katana."
    Respond **only** in valid JSON format with the following keys:
    - "action": The NPC's action (one of: sell_katana, open_door, none)
    - "response": The NPC's spoken dialogue

    Name of the player: {player_name}
    Your (the NPC's) name: {npc_name}
    Personality: {personality}
    Available actions: {allowed_actions}
    World facts: {world_facts}
    Chat history:
    {chat_history}
    Held items: {held_items}

    Player: {player_input}
    NPC:"""


@dataclass(frozen=True)
class PromptContext:
    player_name: str
    npc_name: str
    personality: str
    allowed_actions: str
    world_facts: str
    chat_history: str
    held_items: str
    player_input: str

    def as_dict(self) -> dict[str, str]:
        return self.__dict__.copy()


def render_prompt(context: PromptContext) -> str:
    return ORIGINAL_PROMPT_TEMPLATE.format(**context.as_dict())
