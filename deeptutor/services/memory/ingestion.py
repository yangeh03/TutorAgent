from __future__ import annotations

from datetime import datetime
import re

from .contracts import MemoryView
from .projection import PROFILE_CATEGORIES, SUMMARY_CATEGORIES, SharedMemoryProjection
from .provider import BaseLongTermMemoryProvider

_TRIVIAL_RE = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|got it|bye|goodbye)[!,. ]*$",
    re.IGNORECASE,
)


class SharedMemoryIngestion:
    """Minimal ingestion guard for mem0-backed shared long-term memory."""

    def __init__(self, projection: SharedMemoryProjection | None = None) -> None:
        self._projection = projection or SharedMemoryProjection()

    def ingest_turn(
        self,
        provider: BaseLongTermMemoryProvider,
        *,
        user_message: str,
        assistant_message: str,
        session_id: str = "",
        capability: str = "",
        language: str = "en",
        timestamp: str = "",
    ) -> bool:
        if not provider.is_enabled():
            return False
        if not self.should_ingest_turn(user_message, assistant_message):
            return False

        messages = [
            {"role": "user", "content": self._clip(user_message)},
            {"role": "assistant", "content": self._clip(assistant_message)},
        ]
        return provider.add_conversation(
            messages=messages,
            metadata={
                "source": "auto",
                "scope": "shared_long_term",
                "session_id": session_id,
                "capability": capability or "chat",
                "language": language,
                "captured_at": timestamp or datetime.now().isoformat(),
            },
        )

    def ingest_session(
        self,
        provider: BaseLongTermMemoryProvider,
        *,
        messages: list[dict[str, str]],
        session_id: str = "",
        capability: str = "",
        language: str = "en",
    ) -> bool:
        if not provider.is_enabled():
            return False
        cleaned = [
            {"role": str(item.get("role", "")), "content": self._clip(str(item.get("content", "") or ""))}
            for item in messages
            if str(item.get("role", "")) in {"user", "assistant"}
            and str(item.get("content", "") or "").strip()
        ]
        if len(cleaned) < 2:
            return False
        if not any(not _TRIVIAL_RE.match(item["content"].strip()) for item in cleaned):
            return False

        return provider.add_conversation(
            messages=cleaned,
            metadata={
                "source": "auto",
                "scope": "shared_long_term",
                "session_id": session_id,
                "capability": capability or "chat",
                "language": language,
                "refresh_mode": "session",
            },
        )

    def sync_manual_view(
        self,
        provider: BaseLongTermMemoryProvider,
        *,
        view: MemoryView,
        content: str,
    ) -> bool:
        if not provider.is_enabled():
            return False

        items = self._projection.parse_manual_view(view, content)
        existing = provider.list_memories()
        to_delete = [
            item.id
            for item in existing
            if item.id
            and item.source == "manual_view"
            and self._matches_view(item.metadata.get("view"), view)
        ]
        if to_delete:
            provider.delete_memories(to_delete)

        changed = False
        for item in items:
            category = str(item.get("category", "") or "").strip().lower()
            text = str(item.get("text", "") or "").strip()
            if not category or not text:
                continue
            changed = provider.add_fact(
                text=text,
                metadata={
                    "source": "manual_view",
                    "priority": 100,
                    "scope": view,
                    "view": view,
                    "category": category,
                    "captured_at": datetime.now().isoformat(),
                },
            ) or changed
        return changed or bool(to_delete)

    @staticmethod
    def should_ingest_turn(user_message: str, assistant_message: str) -> bool:
        user = str(user_message or "").strip()
        assistant = str(assistant_message or "").strip()
        if not user or not assistant:
            return False
        if len(user) < 3 and len(assistant) < 3:
            return False
        if _TRIVIAL_RE.match(user) and _TRIVIAL_RE.match(assistant):
            return False
        return True

    @staticmethod
    def categories_for_view(view: MemoryView) -> set[str]:
        return PROFILE_CATEGORIES if view == "profile" else SUMMARY_CATEGORIES

    @staticmethod
    def _clip(text: str, limit: int = 4000) -> str:
        normalized = str(text or "").strip()
        return normalized[:limit]

    @staticmethod
    def _matches_view(value: object, expected: MemoryView) -> bool:
        return str(value or "").strip().lower() == expected


__all__ = ["SharedMemoryIngestion"]
