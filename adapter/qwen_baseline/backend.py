from __future__ import annotations

from typing import Any

from .contract import Response
from .prompt import ORIGINAL_PROMPT_TEMPLATE


def build_qwen_chain(settings: Any) -> Any:
    """Create the original structured-output chain with Qwen-compatible transport."""
    from langchain_core.prompts import PromptTemplate
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.chat_model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        max_retries=0,
        api_key=settings.api_key,
        base_url=settings.base_url,
        # Qwen3.7 defaults to thinking; it exhausted all 1024 output tokens in
        # recorded gameplay failures before producing the required JSON.
        extra_body={"enable_thinking": settings.enable_thinking},
    )
    structured_llm = llm.with_structured_output(Response, method="json_mode")
    prompt = PromptTemplate(
        template=ORIGINAL_PROMPT_TEMPLATE,
        input_variables=[
            "player_name",
            "npc_name",
            "personality",
            "allowed_actions",
            "world_facts",
            "chat_history",
            "held_items",
            "player_input",
        ],
    )
    return prompt | structured_llm
