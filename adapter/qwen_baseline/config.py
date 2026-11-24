from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class ConfigurationError(ValueError):
    """Raised when the local provider configuration is unsafe or incomplete."""


def assert_runtime_db_path(
    db_path: Path,
    *,
    frozen_root: Path | None = None,
) -> Path:
    """Reject database paths that could mutate the frozen upstream copy."""
    resolved = db_path.expanduser().resolve(strict=False)
    roots = []
    if frozen_root is not None:
        roots.append(frozen_root.expanduser().resolve(strict=False))
    if any(part.lower() == "upstream_frozen" for part in resolved.parts):
        raise ConfigurationError(
            "A2_UPSTREAM_DB_PATH must not point inside upstream_frozen"
        )
    for root in roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        raise ConfigurationError(
            "A2_UPSTREAM_DB_PATH must be outside the frozen upstream root"
        )
    return resolved


def _normalise_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    if not candidate:
        raise ConfigurationError("A2_PROXY_BASE_URL is empty")
    parsed = urlsplit(candidate)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigurationError("A2_PROXY_BASE_URL must be an HTTPS URL")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions") or path.endswith("/embeddings"):
        raise ConfigurationError(
            "A2_PROXY_BASE_URL must be a provider base URL, not an endpoint"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


@dataclass(frozen=True)
class QwenSettings:
    base_url: str
    api_key: str
    chat_model: str
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    temperature: float = 0.6
    max_tokens: int = 1024
    enable_thinking: bool = False

    @classmethod
    def from_environment(cls, *, require_credentials: bool = True) -> "QwenSettings":
        base_url = os.getenv("A2_PROXY_BASE_URL", "")
        api_key = os.getenv("A2_PROXY_API_KEY", "")
        chat_model = os.getenv("A2_PROXY_MODEL", "")
        missing = [
            name
            for name, value in (
                ("A2_PROXY_BASE_URL", base_url),
                ("A2_PROXY_API_KEY", api_key),
                ("A2_PROXY_MODEL", chat_model),
            )
            if not value
        ]
        if missing and require_credentials:
            raise ConfigurationError("Missing configuration: " + ", ".join(missing))
        if not base_url:
            base_url = "https://invalid.local/compatible-mode/v1"
        if not api_key:
            api_key = "[offline-not-configured]"
        if not chat_model:
            chat_model = "offline-not-configured"

        dimensions_text = os.getenv("A2_QWEN_EMBEDDING_DIMENSIONS", "1024")
        try:
            dimensions = int(dimensions_text)
        except ValueError as exc:
            raise ConfigurationError(
                "A2_QWEN_EMBEDDING_DIMENSIONS must be an integer"
            ) from exc
        if dimensions not in {64, 128, 256, 512, 768, 1024, 1536, 2048}:
            raise ConfigurationError("Unsupported Qwen embedding dimensions")

        thinking_text = os.getenv("A2_QWEN_ENABLE_THINKING", "false").strip().lower()
        if thinking_text not in {"true", "false"}:
            raise ConfigurationError("A2_QWEN_ENABLE_THINKING must be true or false")
        return cls(
            base_url=_normalise_base_url(base_url),
            api_key=api_key,
            chat_model=chat_model,
            embedding_model=os.getenv(
                "A2_QWEN_EMBEDDING_MODEL", "text-embedding-v4"
            ),
            embedding_dimensions=dimensions,
            enable_thinking=thinking_text == "true",
        )

    @property
    def chat_endpoint(self) -> str:
        return self.base_url + "/chat/completions"

    @property
    def embedding_endpoint(self) -> str:
        return self.base_url + "/embeddings"

    def safe_summary(self) -> dict[str, object]:
        return {
            "base_url_configured": self.base_url != "https://invalid.local/compatible-mode/v1",
            "api_key_configured": self.api_key != "[offline-not-configured]",
            "chat_model": self.chat_model,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "enable_thinking": self.enable_thinking,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "chat_endpoint": self.chat_endpoint,
            "embedding_endpoint": self.embedding_endpoint,
        }
