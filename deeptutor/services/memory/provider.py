"""
Abstract base and null fallback for L2 long-term memory providers.

The provider layer isolates DeepTutor from any specific backend (mem0, etc.).
When no backend is available the ``NullLongTermMemoryProvider`` is used and the
system degrades gracefully to the original file-only behaviour.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from .contracts import IngestionResult, MemoryCategory, MemoryRecord

logger = logging.getLogger(__name__)


class BaseLongTermMemoryProvider(ABC):
    """Abstract base class for L2 long-term memory backends."""

    name: str = "base"

    # ── Write ────────────────────────────────────────────────────────

    @abstractmethod
    def add(
        self,
        text: str,
        *,
        category: MemoryCategory = MemoryCategory.PREFERENCE,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Store a single explicit fact. Returns memory_id or ``None``."""

    @abstractmethod
    def add_from_conversation(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        """Let the backend extract facts from a conversation turn."""

    # ── Read ─────────────────────────────────────────────────────────

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        user_id: str = "default",
        categories: list[MemoryCategory] | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Semantic search.  Optionally filter by category."""

    @abstractmethod
    def get_all(
        self,
        *,
        user_id: str = "default",
        categories: list[MemoryCategory] | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        """Retrieve all memories, optionally filtered."""

    # ── Mutate ───────────────────────────────────────────────────────

    @abstractmethod
    def update(self, memory_id: str, text: str, metadata: dict[str, Any] | None = None) -> bool:
        """Update a single memory by id."""

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """Delete a single memory by id."""

    @abstractmethod
    def delete_all(self, *, user_id: str = "default") -> bool:
        """Wipe all memories for a user."""

    # ── Status ───────────────────────────────────────────────────────

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if the backend is operational."""


# ─────────────────────────────────────────────────────────────────────
# Null fallback (file-only mode)
# ─────────────────────────────────────────────────────────────────────

class NullLongTermMemoryProvider(BaseLongTermMemoryProvider):
    """No-op provider used when mem0 is disabled or unavailable."""

    name = "null"

    def add(self, text, *, category=MemoryCategory.PREFERENCE, user_id="default", metadata=None):
        return None

    def add_from_conversation(self, messages, *, user_id="default", metadata=None):
        return IngestionResult()

    def search(self, query, *, user_id="default", categories=None, limit=20):
        return []

    def get_all(self, *, user_id="default", categories=None, limit=100):
        return []

    def update(self, memory_id, text, metadata=None):
        return False

    def delete(self, memory_id):
        return False

    def delete_all(self, *, user_id="default"):
        return False

    def is_available(self):
        return False


# ─────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────

def create_long_term_memory_provider() -> BaseLongTermMemoryProvider:
    """Create the best available L2 provider based on environment config.

    Returns ``Mem0LongTermMemoryProvider`` when ``MEM0_ENABLED=true`` and
    the necessary dependencies / credentials are present.  Otherwise falls
    back to ``NullLongTermMemoryProvider``.
    """
    enabled = os.getenv("MEM0_ENABLED", "").strip().lower() in ("1", "true", "yes")
    if not enabled:
        logger.debug("MEM0_ENABLED is not set; using NullProvider (file-only mode)")
        return NullLongTermMemoryProvider()

    try:
        from .mem0_provider import Mem0LongTermMemoryProvider

        provider = Mem0LongTermMemoryProvider()
        if provider.is_available():
            logger.info("mem0 L2 provider initialised (local ChromaDB)")
            return provider
        logger.warning("mem0 provider created but not available; falling back to NullProvider")
        return NullLongTermMemoryProvider()
    except Exception:
        logger.warning("Failed to create mem0 provider; falling back to NullProvider", exc_info=True)
        return NullLongTermMemoryProvider()
