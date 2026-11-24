from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .backend import build_qwen_chain
from .config import QwenSettings, assert_runtime_db_path
from .fastapi_app import create_app
from .retrieval import build_faiss_store, load_faiss_store


def _runtime_paths() -> tuple[Path, Path, Path]:
    db_path = assert_runtime_db_path(
        Path(os.environ["A2_UPSTREAM_DB_PATH"]),
        frozen_root=(
            Path(os.environ["A2_FROZEN_UPSTREAM_ROOT"])
            if os.getenv("A2_FROZEN_UPSTREAM_ROOT")
            else None
        ),
    )
    if not db_path.is_file():
        raise FileNotFoundError(f"A2_UPSTREAM_DB_PATH does not exist: {db_path}")
    store_path = Path(
        os.getenv("A2_QWEN_FAISS_PATH", "adapter/qwen_baseline/runtime/vector_store")
    )
    world_facts_path = Path(
        os.getenv(
            "A2_QWEN_WORLD_FACTS_PATH",
            "adapter/qwen_baseline/world_facts.txt",
        )
    )
    if not world_facts_path.is_file():
        raise FileNotFoundError(
            f"A2_QWEN_WORLD_FACTS_PATH does not exist: {world_facts_path}"
        )
    return db_path, store_path, world_facts_path


def preflight_runtime() -> dict[str, object]:
    """Validate local runtime inputs without making provider requests."""
    settings = QwenSettings.from_environment()
    db_path, store_path, world_facts_path = _runtime_paths()

    import faiss  # noqa: F401
    import fastapi  # noqa: F401
    import langchain_community  # noqa: F401
    import langchain_openai  # noqa: F401

    index_present = (
        (store_path / "index.faiss").is_file()
        and (store_path / "index.pkl").is_file()
    )
    if index_present:
        load_faiss_store(settings=settings, store_path=store_path)
    return {
        "status": "PASS",
        "startup_ready": index_present,
        "database_path": str(db_path),
        "world_facts_path": str(world_facts_path),
        "faiss_path": str(store_path),
        "faiss_index_present": index_present,
        "settings": settings.safe_summary(),
        "provider_requests": 0,
    }


def build_runtime_index() -> dict[str, object]:
    """Explicitly build the runtime index; this is the only paid build path."""
    settings = QwenSettings.from_environment()
    db_path, store_path, world_facts_path = _runtime_paths()
    vector_store = build_faiss_store(
        settings=settings,
        world_facts_path=world_facts_path,
        store_path=store_path,
    )
    vector_count = vector_store.index.ntotal
    return {
        "status": "PASS",
        "database_path": str(db_path),
        "world_facts_path": str(world_facts_path),
        "faiss_path": str(store_path),
        "vector_count": vector_count,
        "vector_dimensions": vector_store.index.d,
        "settings": settings.safe_summary(),
        "embedding_requests_expected": (vector_count + 9) // 10,
        "provider_requests": "embedding build only; batches contain at most 10 inputs",
    }


def build_runtime_app():
    settings = QwenSettings.from_environment()
    db_path, store_path, _ = _runtime_paths()
    chain = build_qwen_chain(settings)
    vector_store = load_faiss_store(
        settings=settings,
        store_path=store_path,
    )
    return create_app(db_path=db_path, chain=chain, vector_store=vector_store)


app = None
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dotenv",
        help="Optional local dotenv path; values are loaded without printing them",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--preflight",
        action="store_true",
        help="Validate local runtime inputs without provider requests",
    )
    modes.add_argument(
        "--build-index",
        action="store_true",
        help="Explicitly build the FAISS index using provider embeddings and exit",
    )
    args = parser.parse_args()
    if args.dotenv:
        from dotenv import load_dotenv

        load_dotenv(args.dotenv, override=False)

    if args.preflight:
        print(json.dumps(preflight_runtime(), indent=2))
    elif args.build_index:
        print(json.dumps(build_runtime_index(), indent=2))
    else:
        import uvicorn

        app = build_runtime_app()
        uvicorn.run(app, host="127.0.0.1", port=8000)
