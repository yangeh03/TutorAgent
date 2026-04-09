"""
Shared-memory ingestion: decides what from a conversation turn enters L2.

This module is the *write-path gatekeeper* — it filters out noise
(greetings, one-time queries, tool traces) and forwards only long-term
valuable facts to the mem0 provider.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any

from .contracts import IngestionResult
from .provider import BaseLongTermMemoryProvider

logger = logging.getLogger(__name__)

# Messages shorter than this are almost certainly greetings / acks.
# Note: Chinese characters carry much more info per char than English,
# so this threshold is intentionally low (≈4 Chinese chars).
_MIN_USER_MSG_CHARS = 4

# Capabilities that rarely produce long-term memory signal.
_LOW_SIGNAL_CAPABILITIES = frozenset({"math_animator"})


class SharedMemoryIngestion:
    """Gatekeeper between turns and the L2 long-term memory provider."""

    def __init__(self, provider: BaseLongTermMemoryProvider) -> None:
        self._provider = provider

    async def ingest_turn(
        self,
        *,
        user_message: str,
        assistant_message: str,
        session_id: str = "",
        capability: str = "chat",
        language: str = "en",
    ) -> IngestionResult:
        """Extract long-term facts from a single turn and store in mem0.

        Called at turn-end instead of the old LLM-rewrite path.  Runs the
        synchronous mem0 ``add()`` in a thread executor so the event loop
        is never blocked.
        """
        if not self._should_ingest(user_message, capability):
            return IngestionResult()

        messages = self._format_messages(user_message, assistant_message)
        metadata = self._build_metadata(session_id, capability, language)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(
                self._provider.add_from_conversation,
                messages,
                metadata=metadata,
            ),
        )
        if result.changed:
            logger.debug(
                "mem0 ingestion: +%d added, ~%d updated, =%d unchanged",
                result.added, result.updated, result.unchanged,
            )
        return result

    # ── Pre-filter ───────────────────────────────────────────────────

    @staticmethod
    def _should_ingest(user_message: str, capability: str) -> bool:
        """Return False for turns unlikely to contain long-term facts."""
        text = user_message.strip()
        if len(text) < _MIN_USER_MSG_CHARS:
            return False
        if capability in _LOW_SIGNAL_CAPABILITIES:
            return False
        return True

    # ── Formatting ───────────────────────────────────────────────────

    @staticmethod
    def _format_messages(
        user_message: str,
        assistant_message: str,
    ) -> list[dict[str, str]]:
        """Build the message list that mem0 expects."""
        return [
            {"role": "user", "content": user_message.strip()},
            {"role": "assistant", "content": assistant_message.strip()},
        ]

    @staticmethod
    def _build_metadata(
        session_id: str,
        capability: str,
        language: str,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "capability": capability,
            "language": language,
        }
