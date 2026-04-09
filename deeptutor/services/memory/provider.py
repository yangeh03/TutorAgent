from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import os

from .contracts import LongTermMemoryRecord

logger = logging.getLogger(__name__)


class BaseLongTermMemoryProvider(ABC):
    """Adapter boundary for shared long-term memory backends."""

    backend = "base"

    def __init__(self, user_id: str = "deeptutor-default-user") -> None:
        self.user_id = user_id

    def is_enabled(self) -> bool:
        return True

    @abstractmethod
    def add_conversation(
        self,
        *,
        messages: list[dict[str, str]],
        metadata: dict[str, object] | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def add_fact(
        self,
        *,
        text: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        *,
        query: str,
        limit: int = 8,
    ) -> list[LongTermMemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_memories(self) -> list[LongTermMemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def delete_memories(self, memory_ids: list[str]) -> int:
        raise NotImplementedError

    def clear(self) -> int:
        items = self.list_memories()
        ids = [item.id for item in items if item.id]
        return self.delete_memories(ids)


class NullLongTermMemoryProvider(BaseLongTermMemoryProvider):
    """Disabled provider used when mem0 is not configured."""

    backend = "disabled"

    def __init__(self, reason: str = "") -> None:
        super().__init__(user_id="deeptutor-default-user")
        self.reason = reason

    def is_enabled(self) -> bool:
        return False

    def add_conversation(
        self,
        *,
        messages: list[dict[str, str]],
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return False

    def add_fact(
        self,
        *,
        text: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return False

    def search(
        self,
        *,
        query: str,
        limit: int = 8,
    ) -> list[LongTermMemoryRecord]:
        return []

    def list_memories(self) -> list[LongTermMemoryRecord]:
        return []

    def delete_memories(self, memory_ids: list[str]) -> int:
        return 0


_provider_instance: BaseLongTermMemoryProvider | None = None


def get_long_term_memory_provider() -> BaseLongTermMemoryProvider:
    """Create the configured shared long-term memory provider once."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    backend = str(os.getenv("MEMORY_PROVIDER", "auto") or "auto").strip().lower()
    if backend == "file":
        _provider_instance = NullLongTermMemoryProvider("MEMORY_PROVIDER=file")
        return _provider_instance

    mem0_hints = any(
        str(os.getenv(key, "") or "").strip()
        for key in (
            "MEM0_API_KEY",
            "MEM0_OSS_CONFIG",
            "MEM0_OSS_CONFIG_JSON",
        )
    )
    if backend not in {"auto", "mem0"}:
        logger.warning("Unknown MEMORY_PROVIDER=%s, falling back to file-backed memory", backend)
        _provider_instance = NullLongTermMemoryProvider(f"unknown backend: {backend}")
        return _provider_instance
    if backend == "auto" and not mem0_hints:
        _provider_instance = NullLongTermMemoryProvider("mem0 not configured")
        return _provider_instance

    try:
        from .mem0_provider import Mem0LongTermMemoryProvider

        _provider_instance = Mem0LongTermMemoryProvider.from_env()
    except Exception as exc:
        logger.warning("mem0 provider unavailable, using legacy file memory: %s", exc)
        _provider_instance = NullLongTermMemoryProvider(str(exc))
    return _provider_instance


__all__ = [
    "BaseLongTermMemoryProvider",
    "NullLongTermMemoryProvider",
    "get_long_term_memory_provider",
]

