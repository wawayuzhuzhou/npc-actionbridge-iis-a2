from __future__ import annotations

import sqlite3
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import NameCheckQuery, NameCheckResponse, Query


def _log_generation(level: int, **event: Any) -> None:
    """Retain local transport evidence without logging provider credentials."""
    message = json.dumps(
        {"time_utc": datetime.now(timezone.utc).isoformat(), **event},
        ensure_ascii=False,
    )
    secret = os.getenv("A2_PROXY_API_KEY", "")
    if secret:
        message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(?i)(bearer\s+)[^\s\"\\]+", r"\1[REDACTED]", message)
    message = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", message)
    logging.getLogger("uvicorn.error").log(level, "Qwen generation: %s", message)


def create_app(*, db_path: Path, chain: Any, vector_store: Any, on_conversation_saved: Any = None) -> Any:
    """Create the original endpoint surface with injected Qwen components."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    # Upstream Godot dialogue requests omit Content-Type despite sending JSON.
    # Restore legacy parsing; current FastAPI otherwise rejects them with 422.
    app = FastAPI(strict_content_type=False)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/get_response")
    def get_response(query: Query):
        stage = "read_context"
        calls = {"retriever_invocations_client_path": 0, "chain_invocations_client_path": 0}
        context = query.model_dump()
        try:
            connection = sqlite3.connect(db_path)
            try:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT personality, allowed_actions
                    FROM NPCs
                    WHERE npc_name = ?
                    """,
                    (query.npc_name,),
                )
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail=f"NPC with name {query.npc_name} not found.",
                    )
                personality, allowed_actions = result
                cursor.execute(
                    """
                    SELECT player_name, player_input, npc_response
                    FROM Conversations
                    WHERE player_name = ? AND npc_name = ?
                    ORDER BY timestamp ASC
                    """,
                    (query.player_name, query.npc_name),
                )
                chat_history = cursor.fetchall()
            finally:
                connection.close()

            chat_history_text = "\n".join(
                f"Player: {player_input}\nNPC: {response}"
                for _, player_input, response in chat_history
            )
            stage = "retrieval"
            calls["retriever_invocations_client_path"] += 1
            world_facts = vector_store.similarity_search(query.player_input, k=5)
            stage = "chat_and_structured_output"
            calls["chain_invocations_client_path"] += 1
            response = chain.invoke(
                {
                    "player_name": query.player_name,
                    "npc_name": query.npc_name,
                    "personality": personality,
                    "allowed_actions": allowed_actions,
                    "world_facts": "\n".join(
                        document.page_content for document in world_facts
                    ),
                    "chat_history": chat_history_text,
                    "held_items": query.held_items,
                    "player_input": query.player_input,
                }
            )

            stage = "persist_conversation"
            connection = sqlite3.connect(db_path)
            try:
                inserted = connection.execute(
                    """
                    INSERT INTO Conversations
                    (player_name, npc_name, held_items, player_input,
                     npc_response, npc_action, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        query.player_name,
                        query.npc_name,
                        query.held_items,
                        query.player_input,
                        response.response,
                        response.action.value,
                    ),
                )
                connection.commit()
                conversation_id = inserted.lastrowid
            finally:
                connection.close()
            if on_conversation_saved is not None:
                on_conversation_saved(conversation_id, response)
            _log_generation(
                logging.INFO, status=200, stage="completed", action=response.action.value,
                **context, **calls,
            )
            return response
        except HTTPException:
            raise
        except Exception as exc:
            _log_generation(
                logging.ERROR, status=500, stage=stage,
                error_type=type(exc).__name__, error=str(exc), **context, **calls,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Error generating response: {exc}",
            ) from exc

    @app.post("/get_latest_response")
    def get_latest_response(query: Query):
        try:
            with sqlite3.connect(db_path) as connection:
                result = connection.execute(
                    """
                    SELECT npc_response
                    FROM Conversations
                    WHERE (player_name = ? OR player_name = "All")
                      AND npc_name = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (query.player_name, query.npc_name),
                ).fetchone()
            response = {
                "npc_name": query.npc_name,
                "action": "",
                "response": result[0],
            }
            if result:
                return response
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No conversations found for player "
                    f"'{query.player_name}' and NPC '{query.npc_name}'."
                ),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Error retrieving the latest response: {exc}",
            ) from exc

    @app.get("/")
    def root():
        return {"message": "Hello World, the API works!"}

    @app.post("/check_name_availability")
    def check_name_availability(query: NameCheckQuery):
        try:
            with sqlite3.connect(db_path) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT 1 FROM Players WHERE player_name = ?",
                    (query.player_name,),
                )
                result = cursor.fetchone()
            if not result:
                cursor.execute(
                    """
                    INSERT INTO Players (player_name, creation_timestamp)
                    VALUES (?, datetime('now'))
                    """,
                    (query.player_name,),
                )
                connection.commit()
            return NameCheckResponse(available=result is None)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Error checking name availability: {exc}",
            ) from exc

    @app.get("/conversations")
    def get_conversations():
        with sqlite3.connect(db_path) as connection:
            rows = connection.execute("SELECT * FROM Conversations").fetchall()
        return {
            "conversations": [
                {
                    "id": row[0],
                    "player_name": row[1],
                    "npc_name": row[2],
                    "held_items": row[3],
                    "player_input": row[4],
                    "npc_response": row[5],
                    "npc_action": row[6],
                    "timestamp": row[7],
                }
                for row in rows
            ]
        }

    @app.get("/players")
    def get_players():
        with sqlite3.connect(db_path) as connection:
            rows = connection.execute("SELECT * FROM Players").fetchall()
        return {
            "players": [
                {
                    "player_name": row[0],
                    "creation_timestamp": row[1],
                }
                for row in rows
            ]
        }

    return app
