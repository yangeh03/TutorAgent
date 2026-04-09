from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .contracts import MemoryView
from .projection import (
    PROFILE_CATEGORIES,
    PROGRESS_CATEGORIES,
    SUMMARY_CATEGORIES,
    SharedMemoryProjection,
)
from .provider import BaseLongTermMemoryProvider

_TRIVIAL_RE = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|got it|bye|goodbye)[!,. ]*$",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$")


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

    def ingest_guide_completion(
        self,
        provider: BaseLongTermMemoryProvider,
        *,
        notebook_name: str,
        knowledge_points: list[dict[str, Any]],
        chat_history: list[dict[str, Any]],
        summary: str,
        session_id: str = "",
    ) -> bool:
        if not provider.is_enabled():
            return False

        now = datetime.now().isoformat()
        changed = False
        normalized_topic = self._clip(notebook_name, 200)
        if normalized_topic:
            changed = provider.add_fact(
                text=normalized_topic,
                metadata={
                    "source": "guide",
                    "scope": "progress",
                    "category": "active_topic",
                    "topic": normalized_topic,
                    "session_id": session_id,
                    "captured_at": now,
                },
            ) or changed
            changed = provider.add_fact(
                text=f"Currently working through {normalized_topic}.",
                metadata={
                    "source": "guide",
                    "scope": "summary",
                    "category": "focus",
                    "session_id": session_id,
                    "captured_at": now,
                },
            ) or changed

        for point in knowledge_points:
            title = self._clip(str(point.get("knowledge_title", "") or ""), 240)
            if not title:
                continue
            changed = provider.add_fact(
                text=title,
                metadata={
                    "source": "guide",
                    "scope": "progress",
                    "category": "completed_point",
                    "topic": normalized_topic,
                    "knowledge_point": title,
                    "status": "completed",
                    "session_id": session_id,
                    "captured_at": now,
                },
            ) or changed
            changed = provider.add_fact(
                text=f"Completed guided learning on {title}.",
                metadata={
                    "source": "guide",
                    "scope": "summary",
                    "category": "accomplishment",
                    "topic": normalized_topic,
                    "knowledge_point": title,
                    "session_id": session_id,
                    "captured_at": now,
                },
            ) or changed

        for item in self._extract_progress_items(summary, default_topic=normalized_topic):
            changed = provider.add_fact(
                text=item["text"],
                metadata={
                    "source": "guide",
                    "scope": item["scope"],
                    "category": item["category"],
                    "topic": item.get("topic", normalized_topic),
                    "session_id": session_id,
                    "captured_at": now,
                },
            ) or changed

        interaction_count = len([msg for msg in chat_history if str(msg.get("role")) == "user"])
        if interaction_count:
            changed = provider.add_fact(
                text=f"Asked {interaction_count} questions while studying {normalized_topic}.",
                metadata={
                    "source": "guide",
                    "scope": "summary",
                    "category": "accomplishment",
                    "topic": normalized_topic,
                    "session_id": session_id,
                    "captured_at": now,
                },
            ) or changed

        return changed

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
            topic = str(item.get("topic", "") or "").strip()
            if not category or not text:
                continue
            metadata = {
                "source": "manual_view",
                "priority": 100,
                "scope": view,
                "view": view,
                "category": category,
                "captured_at": datetime.now().isoformat(),
            }
            if topic:
                metadata["topic"] = topic
            changed = provider.add_fact(text=text, metadata=metadata) or changed
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
        if view == "profile":
            return PROFILE_CATEGORIES
        if view == "progress":
            return PROGRESS_CATEGORIES
        return SUMMARY_CATEGORIES

    @staticmethod
    def _clip(text: str, limit: int = 4000) -> str:
        normalized = str(text or "").strip()
        return normalized[:limit]

    @staticmethod
    def _matches_view(value: object, expected: MemoryView) -> bool:
        return str(value or "").strip().lower() == expected

    def _extract_progress_items(self, summary: str, *, default_topic: str) -> list[dict[str, str]]:
        text = str(summary or "").replace("\r\n", "\n").strip()
        if not text:
            return []

        items: list[dict[str, str]] = []
        current_heading = ""
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            heading_match = _HEADING_RE.match(stripped)
            if heading_match:
                current_heading = heading_match.group(1).strip().lower()
                continue
            if not stripped.startswith(("- ", "* ")):
                continue
            bullet = stripped[2:].strip()
            if not bullet:
                continue
            category = self._summary_heading_category(current_heading, bullet)
            if not category:
                continue
            scope = "progress" if category in PROGRESS_CATEGORIES else "summary"
            items.append(
                {
                    "scope": scope,
                    "category": category,
                    "text": self._clip(bullet, 300),
                    "topic": default_topic,
                }
            )
        return items

    @staticmethod
    def _summary_heading_category(heading: str, bullet: str) -> str:
        normalized_heading = str(heading or "").lower()
        text = bullet.lower()
        if any(key in normalized_heading for key in ("review", "薄弱", "弱项")):
            return "needs_review"
        if any(key in normalized_heading for key in ("misconception", "误区", "问题")):
            return "misconception"
        if any(key in normalized_heading for key in ("suggest", "next", "建议", "后续")):
            return "next_step"
        if any(key in normalized_heading for key in ("overview", "概览", "学习内容")):
            return "focus"
        if "question" in text or "困惑" in text:
            return "misconception"
        if any(key in text for key in ("review", "复习", "加强", "巩固")):
            return "needs_review"
        if any(key in text for key in ("next", "建议", "practice", "练习")):
            return "next_step"
        return ""


__all__ = ["SharedMemoryIngestion"]
