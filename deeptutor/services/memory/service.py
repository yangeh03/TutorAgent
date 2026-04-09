"""
Two-file public memory system: SUMMARY.md and PROFILE.md.

- SUMMARY: Running summary of the user's learning journey (auto-updated).
- PROFILE: User identity, preferences, knowledge levels (auto-updated).

When mem0 is enabled (``MEM0_ENABLED=true``), the underlying long-term facts
are stored in a local ChromaDB vector store via mem0.  PROFILE.md and
SUMMARY.md become *projected governance views* — still human-editable, but
regenerated from mem0 when facts change.

Per-bot files (SOUL.md, TOOLS.md, USER.md, etc.) live in each bot's
workspace directory, not in the shared memory dir.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from deeptutor.services.llm import stream as llm_stream
from deeptutor.services.path_service import PathService, get_path_service
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, get_sqlite_session_store

from .contracts import MemoryCategory, MemoryRecord
from .ingestion import SharedMemoryIngestion
from .projection import SharedMemoryProjection
from .provider import (
    BaseLongTermMemoryProvider,
    NullLongTermMemoryProvider,
    create_long_term_memory_provider,
)

logger = logging.getLogger(__name__)

MemoryFile = Literal["summary", "profile"]
MEMORY_FILES: list[MemoryFile] = ["summary", "profile"]

_NO_CHANGE = "NO_CHANGE"

_FILENAMES: dict[MemoryFile, str] = {
    "summary": "SUMMARY.md",
    "profile": "PROFILE.md",
}

# ── Category mapping for manual edit sync-back ───────────────────────

_SECTION_TO_CATEGORY: dict[str, MemoryCategory] = {
    "identity": MemoryCategory.IDENTITY,
    "preferences": MemoryCategory.PREFERENCE,
    "learning style": MemoryCategory.PREFERENCE,
    "knowledge level": MemoryCategory.KNOWLEDGE_LEVEL,
    "learning goals": MemoryCategory.LEARNING_GOAL,
    "current focus": MemoryCategory.CURRENT_TOPIC,
    "accomplishments": MemoryCategory.COMPLETED_NODE,
    "open questions": MemoryCategory.OPEN_QUESTION,
    "areas for improvement": MemoryCategory.RECURRING_MISTAKE,
}


@dataclass
class MemorySnapshot:
    summary: str
    profile: str
    summary_updated_at: str | None
    profile_updated_at: str | None


@dataclass
class MemoryUpdateResult:
    content: str
    changed: bool
    updated_at: str | None


class MemoryService:
    """Two-file public memory with optional mem0 L2 backend."""

    def __init__(
        self,
        path_service: PathService | None = None,
        store: SQLiteSessionStore | None = None,
        provider: BaseLongTermMemoryProvider | None = None,
    ) -> None:
        self._path_service = path_service or get_path_service()
        self._store = store or get_sqlite_session_store()

        self._provider = provider or create_long_term_memory_provider()
        self._ingestion = SharedMemoryIngestion(self._provider)
        self._projection = SharedMemoryProjection(self._provider)

        self._migrate_legacy()

    @property
    def provider(self) -> BaseLongTermMemoryProvider:
        return self._provider

    @property
    def _memory_dir(self) -> Path:
        return self._path_service.get_memory_dir()

    def _path(self, which: MemoryFile) -> Path:
        return self._memory_dir / _FILENAMES[which]

    def _migrate_legacy(self) -> None:
        """One-time migration from old memory.md to the two-file system."""
        legacy = self._memory_dir / "memory.md"
        if not legacy.exists():
            return
        if self._path("profile").exists() or self._path("summary").exists():
            return

        content = legacy.read_text(encoding="utf-8").strip()
        if not content:
            legacy.rename(legacy.with_suffix(".md.bak"))
            return

        preferences, context = self._extract_legacy_sections(content)
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        if preferences:
            self._path("profile").write_text(
                f"## Preferences\n{preferences}", encoding="utf-8",
            )
        if context:
            self._path("summary").write_text(
                f"## Learning Journey\n{context}", encoding="utf-8",
            )
        legacy.rename(legacy.with_suffix(".md.bak"))

    # ── Read ──────────────────────────────────────────────────────────

    def read_file(self, which: MemoryFile) -> str:
        path = self._path(which)
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def read_summary(self) -> str:
        return self.read_file("summary")

    def read_profile(self) -> str:
        return self.read_file("profile")

    def _file_updated_at(self, which: MemoryFile) -> str | None:
        path = self._path(which)
        if not path.exists():
            return None
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
        except Exception:
            return None

    def read_snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(
            summary=self.read_summary(),
            profile=self.read_profile(),
            summary_updated_at=self._file_updated_at("summary"),
            profile_updated_at=self._file_updated_at("profile"),
        )

    # ── Write ─────────────────────────────────────────────────────────

    def write_file(self, which: MemoryFile, content: str) -> MemorySnapshot:
        normalized = str(content or "").strip()
        path = self._path(which)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not normalized:
            if path.exists():
                path.unlink()
        else:
            path.write_text(normalized, encoding="utf-8")
        return self.read_snapshot()

    def write_memory(self, content: str) -> MemorySnapshot:
        """Legacy compat: write to profile (primary editable file)."""
        return self.write_file("profile", content)

    def clear_file(self, which: MemoryFile) -> MemorySnapshot:
        return self.write_file(which, "")

    def clear_memory(self) -> MemorySnapshot:
        for f in MEMORY_FILES:
            path = self._path(f)
            if path.exists():
                path.unlink()
        return self.read_snapshot()

    # ── Context building (injected into LLM prompts) ─────────────────

    def build_memory_context(
        self,
        max_chars: int = 4000,
        *,
        capability: str = "chat",
        query: str = "",
    ) -> str:
        """Build the memory_context string for a capability.

        When mem0 is available, generates a capability-aware context from
        the vector store.  Otherwise falls back to reading the Markdown files.
        """
        if self._provider.is_available():
            try:
                ctx = self._projection.project_capability_context(
                    capability=capability,
                    query=query,
                    max_chars=max_chars,
                )
                if ctx:
                    return ctx
            except Exception:
                logger.debug("mem0 projection failed; falling back to files", exc_info=True)

        return self._build_memory_context_from_files(max_chars)

    def _build_memory_context_from_files(self, max_chars: int = 4000) -> str:
        """Original file-based memory context builder (fallback)."""
        parts: list[str] = []

        profile = self.read_profile()
        if profile:
            parts.append(f"### User Profile\n{profile}")

        summary = self.read_summary()
        if summary:
            parts.append(f"### Learning Context\n{summary}")

        if not parts:
            return ""

        combined = "\n\n".join(parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars].rstrip() + "\n...[truncated]"

        return (
            "## Background Memory\n"
            "Use this memory sparingly — only when directly relevant.\n\n"
            f"{combined}"
        )

    def get_preferences_text(self) -> str:
        profile = self.read_profile()
        return f"## User Profile\n{profile}" if profile else ""

    # ── Auto-refresh from conversation ────────────────────────────────

    async def refresh_from_turn(
        self,
        *,
        user_message: str,
        assistant_message: str,
        session_id: str = "",
        capability: str = "",
        language: str = "en",
        timestamp: str = "",
    ) -> MemoryUpdateResult:
        if not user_message.strip() or not assistant_message.strip():
            return MemoryUpdateResult(content="", changed=False, updated_at=None)

        # ── mem0 path ────────────────────────────────────────────────
        if self._provider.is_available():
            try:
                result = await self._ingestion.ingest_turn(
                    user_message=user_message,
                    assistant_message=assistant_message,
                    session_id=session_id,
                    capability=capability or "chat",
                    language=language,
                )
                if result.changed:
                    self._refresh_files_from_projection()
                snap = self.read_snapshot()
                return MemoryUpdateResult(
                    content=snap.profile,
                    changed=result.changed,
                    updated_at=snap.profile_updated_at,
                )
            except Exception:
                logger.debug("mem0 ingestion failed; falling back to legacy", exc_info=True)

        # ── Legacy LLM-rewrite path ─────────────────────────────────
        return await self._refresh_from_turn_legacy(
            user_message=user_message,
            assistant_message=assistant_message,
            session_id=session_id,
            capability=capability,
            language=language,
            timestamp=timestamp,
        )

    async def refresh_from_session(
        self,
        session_id: str | None = None,
        *,
        language: str = "en",
        max_messages: int = 10,
    ) -> MemoryUpdateResult:
        target = (session_id or "").strip()
        if not target:
            sessions = await self._store.list_sessions(limit=1)
            if sessions:
                target = str(sessions[0].get("session_id", "") or "")

        if not target:
            return MemoryUpdateResult(content="", changed=False, updated_at=None)

        messages = await self._store.get_messages_for_context(target)
        relevant = [
            m for m in messages
            if str(m.get("role", "")) in {"user", "assistant"}
            and str(m.get("content", "") or "").strip()
        ][-max_messages:]

        if not relevant:
            return MemoryUpdateResult(content="", changed=False, updated_at=None)

        # ── mem0 path: ingest message pairs ──────────────────────────
        if self._provider.is_available():
            any_changed = False
            for i in range(0, len(relevant) - 1, 2):
                user_msg = str(relevant[i].get("content", "")).strip()
                asst_msg = str(relevant[i + 1].get("content", "")).strip() if i + 1 < len(relevant) else ""
                if user_msg and asst_msg:
                    try:
                        result = await self._ingestion.ingest_turn(
                            user_message=user_msg,
                            assistant_message=asst_msg,
                            session_id=target,
                            language=language,
                        )
                        any_changed = any_changed or result.changed
                    except Exception:
                        logger.debug("mem0 session ingestion failed for pair", exc_info=True)
            if any_changed:
                self._refresh_files_from_projection()
            snap = self.read_snapshot()
            return MemoryUpdateResult(
                content=snap.profile,
                changed=any_changed,
                updated_at=snap.profile_updated_at,
            )

        # ── Legacy path ──────────────────────────────────────────────
        transcript = "\n\n".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: "
            f"{str(m.get('content', '') or '').strip()}"
            for m in relevant
        )

        cap = ""
        sess = await self._store.get_session(target)
        if sess:
            cap = str(sess.get("capability", "") or "")

        source = (
            f"[Session] {target}\n"
            f"[Capability] {cap or 'chat'}\n\n"
            f"[Recent Transcript]\n{transcript}"
        )

        p_changed = await self._rewrite_one("profile", source, language)
        s_changed = await self._rewrite_one("summary", source, language)

        snap = self.read_snapshot()
        return MemoryUpdateResult(
            content=snap.profile,
            changed=p_changed or s_changed,
            updated_at=snap.profile_updated_at,
        )

    # ── Projection refresh ────────────────────────────────────────────

    def _refresh_files_from_projection(self) -> None:
        """Re-generate PROFILE.md and SUMMARY.md from mem0 records."""
        try:
            profile_text = self._projection.project_profile()
            if profile_text:
                self.write_file("profile", profile_text)

            summary_text = self._projection.project_summary()
            if summary_text:
                self.write_file("summary", summary_text)
        except Exception:
            logger.debug("Failed to project files from mem0", exc_info=True)

    # ── Manual edit sync-back ─────────────────────────────────────────

    async def sync_file_to_provider(self, which: MemoryFile) -> None:
        """Sync a manually-edited Markdown file back to mem0.

        Parses the file into bullet items, deletes old records for the
        relevant categories, and re-adds each item with ``source=manual``.
        Manual edits always take priority over auto-extracted facts.
        """
        if not self._provider.is_available():
            return

        content = self.read_file(which)
        items = self._parse_markdown_items(content)
        if not items:
            return

        # Determine which categories this file covers
        from .contracts import PROFILE_CATEGORIES, SUMMARY_CATEGORIES
        categories = PROFILE_CATEGORIES if which == "profile" else SUMMARY_CATEGORIES

        # Delete existing records for these categories
        existing = self._provider.get_all(categories=categories)
        for record in existing:
            self._provider.delete(record.id)

        # Re-add parsed items
        for category, text in items:
            self._provider.add(
                text,
                category=category,
                metadata={"source": "manual"},
            )

    @staticmethod
    def _parse_markdown_items(content: str) -> list[tuple[MemoryCategory, str]]:
        """Parse Markdown into (category, text) pairs from ``## Section`` headers."""
        items: list[tuple[MemoryCategory, str]] = []
        current_cat = MemoryCategory.PREFERENCE

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("## "):
                heading = stripped[3:].strip().lower()
                current_cat = _SECTION_TO_CATEGORY.get(heading, MemoryCategory.PREFERENCE)
            elif stripped.startswith("- "):
                text = stripped[2:].strip()
                if text:
                    items.append((current_cat, text))

        return items

    # ── Provider-level operations ─────────────────────────────────────

    def search(self, query: str, *, limit: int = 20) -> list[MemoryRecord]:
        """Semantic search over mem0 records."""
        if not self._provider.is_available():
            return []
        return self._provider.search(query, limit=limit)

    def clear_provider_memories(self) -> None:
        """Wipe all mem0 records for the current user."""
        if self._provider.is_available():
            self._provider.delete_all()

    # ── Legacy LLM rewrite helpers ────────────────────────────────────

    async def _refresh_from_turn_legacy(
        self,
        *,
        user_message: str,
        assistant_message: str,
        session_id: str = "",
        capability: str = "",
        language: str = "en",
        timestamp: str = "",
    ) -> MemoryUpdateResult:
        """Original LLM-rewrite path (used when mem0 is unavailable)."""
        source = (
            f"[Session] {session_id or '(unknown)'}\n"
            f"[Capability] {capability or 'chat'}\n"
            f"[Timestamp] {timestamp or datetime.now().isoformat()}\n\n"
            f"[User]\n{user_message.strip()}\n\n"
            f"[Assistant]\n{assistant_message.strip()}"
        )

        p_changed = await self._rewrite_one("profile", source, language)
        s_changed = await self._rewrite_one("summary", source, language)

        snap = self.read_snapshot()
        return MemoryUpdateResult(
            content=snap.profile,
            changed=p_changed or s_changed,
            updated_at=snap.profile_updated_at,
        )

    async def _rewrite_one(self, which: MemoryFile, source: str, language: str) -> bool:
        """Rewrite a single memory file. Returns True if changed."""
        current = self.read_file(which)
        zh = str(language).lower().startswith("zh")

        if which == "profile":
            sys_prompt, user_prompt = self._profile_prompts(current, source, zh)
        else:
            sys_prompt, user_prompt = self._summary_prompts(current, source, zh)

        chunks: list[str] = []
        async for c in llm_stream(
            prompt=user_prompt,
            system_prompt=sys_prompt,
            temperature=0.2,
            max_tokens=900,
        ):
            chunks.append(c)

        raw = _strip_code_fence("".join(chunks)).strip()
        if not raw or raw == _NO_CHANGE:
            return False

        if raw == current:
            return False

        self.write_file(which, raw)
        return True

    @staticmethod
    def _profile_prompts(current: str, source: str, zh: bool) -> tuple[str, str]:
        if zh:
            return (
                "你负责维护一份用户画像文档。只保留稳定的用户身份、偏好、知识水平。"
                f"如果无需修改，请只返回 {_NO_CHANGE}。",
                "如果需要更新，请重写用户画像，可使用以下标题：\n"
                "## Identity\n## Learning Style\n## Knowledge Level\n## Preferences\n\n"
                "规则：保持简短，删除过时内容，不要记录临时对话。\n\n"
                f"[当前画像]\n{current or '(empty)'}\n\n"
                f"[新增材料]\n{source}"
            )
        return (
            "You maintain a user profile document. Only keep stable identity, "
            "preferences, and knowledge levels. "
            f"If nothing should change, return exactly {_NO_CHANGE}.",
            "Rewrite the user profile if needed. Suggested sections:\n"
            "## Identity\n## Learning Style\n## Knowledge Level\n## Preferences\n\n"
            "Rules: keep it short, remove stale items, no transient chatter.\n\n"
            f"[Current profile]\n{current or '(empty)'}\n\n"
            f"[New material]\n{source}"
        )

    @staticmethod
    def _summary_prompts(current: str, source: str, zh: bool) -> tuple[str, str]:
        if zh:
            return (
                "你负责维护一份学习旅程摘要。记录用户正在学什么、完成了什么、有哪些待解决的问题。"
                f"如果无需修改，请只返回 {_NO_CHANGE}。",
                "如果需要更新，请重写学习旅程摘要，可使用以下标题：\n"
                "## Current Focus\n## Accomplishments\n## Open Questions\n\n"
                "规则：保持简短，删除已完成或过时的条目。\n\n"
                f"[当前摘要]\n{current or '(empty)'}\n\n"
                f"[新增材料]\n{source}"
            )
        return (
            "You maintain a learning journey summary. Track what the user is studying, "
            "what they've accomplished, and what open questions remain. "
            f"If nothing should change, return exactly {_NO_CHANGE}.",
            "Rewrite the learning summary if needed. Suggested sections:\n"
            "## Current Focus\n## Accomplishments\n## Open Questions\n\n"
            "Rules: keep it short, remove completed/stale items.\n\n"
            f"[Current summary]\n{current or '(empty)'}\n\n"
            f"[New material]\n{source}"
        )

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_legacy_sections(content: str) -> tuple[str, str]:
        text = content.replace("\r\n", "\n").strip()
        preferences = ""
        context = ""
        pref_match = re.search(
            r"##\s*Preferences\s*(.*?)(?=\n##\s*Context\b|\Z)",
            text, flags=re.IGNORECASE | re.DOTALL,
        )
        ctx_match = re.search(
            r"##\s*Context\s*(.*)$",
            text, flags=re.IGNORECASE | re.DOTALL,
        )
        if pref_match:
            preferences = pref_match.group(1).strip()
        if ctx_match:
            context = ctx_match.group(1).strip()
        return preferences, context


def _strip_code_fence(content: str) -> str:
    cleaned = str(content or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


__all__ = [
    "MemoryFile",
    "MemoryService",
    "MemorySnapshot",
    "MemoryUpdateResult",
    "get_memory_service",
]
