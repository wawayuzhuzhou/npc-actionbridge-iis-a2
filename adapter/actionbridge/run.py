"""Enhanced runtime on port 8001 with an explicitly selected disposable DB."""
import argparse
from pathlib import Path

from adapter.qwen_baseline.backend import build_qwen_chain
from adapter.qwen_baseline.config import QwenSettings, assert_runtime_db_path
from adapter.qwen_baseline.retrieval import load_faiss_store
from .api import create_app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotenv", required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--faiss-path", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(args.dotenv, override=False)
    db_path = assert_runtime_db_path(args.db)
    if not db_path.is_file():
        parser.error("--db must be an existing separate disposable ActionBridge DB")
    settings = QwenSettings.from_environment()
    app = create_app(
        db_path=db_path, chain=build_qwen_chain(settings),
        vector_store=load_faiss_store(settings=settings, store_path=args.faiss_path),
    )
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)
