from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .config import ConfigurationError


@dataclass(frozen=True)
class RetrievedFact:
    page_content: str


def load_world_facts(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class FixtureRetriever:
    """Deterministic lexical fixture; it is not evidence of embedding quality."""

    def __init__(self, facts: list[str]):
        self._facts = tuple(facts)

    def similarity_search(self, query: str, *, k: int = 5) -> list[RetrievedFact]:
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked = sorted(
            self._facts,
            key=lambda fact: (
                len(terms.intersection(re.findall(r"[a-z0-9]+", fact.lower()))),
                -self._facts.index(fact),
            ),
            reverse=True,
        )
        return [RetrievedFact(fact) for fact in ranked[:k]]


def _create_embeddings(settings: Any) -> Any:
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_key=settings.api_key,
        base_url=settings.base_url,
        chunk_size=10,
        check_embedding_ctx_length=False,
        max_retries=0,
    )


def load_faiss_store(*, settings: Any, store_path: Path) -> Any:
    """Load an existing validated FAISS store without making provider calls."""
    from langchain_community.vectorstores import FAISS

    index_path = store_path / "index.faiss"
    metadata_path = store_path / "index.pkl"
    if not index_path.is_file() or not metadata_path.is_file():
        raise ConfigurationError(
            "FAISS index is missing; run with --build-index explicitly"
        )
    vector_store = FAISS.load_local(
        str(store_path),
        _create_embeddings(settings),
        allow_dangerous_deserialization=True,
    )
    if vector_store.index.d != settings.embedding_dimensions:
        raise ConfigurationError(
            "Existing FAISS index dimensions do not match Qwen embeddings"
        )
    return vector_store


def build_faiss_store(
    *,
    settings: Any,
    world_facts_path: Path,
    store_path: Path,
) -> Any:
    """Build the Qwen-compatible FAISS store; provider calls are explicit."""
    import faiss
    from langchain_community.docstore.in_memory import InMemoryDocstore
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document

    if not world_facts_path.is_file():
        raise FileNotFoundError(f"World facts file does not exist: {world_facts_path}")
    if store_path.exists() and any(store_path.iterdir()):
        raise ConfigurationError(
            "FAISS output directory is not empty; refusing to overwrite it"
        )
    store_path.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatL2(settings.embedding_dimensions)
    documents = [Document(page_content=fact) for fact in load_world_facts(world_facts_path)]
    vector_store = FAISS(
        embedding_function=_create_embeddings(settings),
        index=index,
        docstore=InMemoryDocstore(),
        index_to_docstore_id={},
    )
    vector_store.add_documents(documents)
    vector_store.save_local(str(store_path))
    if vector_store.index.d != settings.embedding_dimensions:
        raise ConfigurationError("Built FAISS index dimensions are inconsistent")
    return vector_store
