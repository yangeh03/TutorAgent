"""
Shared governance views for long-term memory.

- PROFILE: Stable user identity, preferences, knowledge levels.
- SUMMARY: High-level learning journey summary.
- PROGRESS: Topic-level learning progress across guided learning.

Per-bot files (SOUL.md, TOOLS.md, USER.md, etc.) live in each bot's
workspace directory, not in the shared memory dir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import re
from typing import Literal

from deeptutor.services.llm import stream as llm_stream
from deeptutor.services.memory.ingestion import SharedMemoryIngestion
from deeptutor.services.memory.projection import (
    PROFILE_CATEGORIES,
    PROGRESS_CATEGORIES,
    SUMMARY_CATEGORIES,
    SharedMemoryProjection,
)
from deeptutor.services.memory.provider import (
    BaseLongTermMemoryProvider,
    get_long_term_memory_provider,
)
from deeptutor.services.path_service import PathService, get_path_service
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, get_sqlite_session_store

MemoryFile = Literal["summary", "profile", "progress"]
MEMORY_FILES: list[MemoryFile] = ["summary", "profile", "progress"]

_NO_CHANGE = "NO_CHANGE"

_FILENAMES: dict[MemoryFile, str] = {
    "summary": "SUMMARY.md",
    "profile": "PROFILE.md",
    "progress": "PROGRESS.md",
}

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    summary: str
    profile: str
    progress: str
    summary_updated_at: str | None
    profile_updated_at: str | None
    progress_updated_at: str | None


@dataclass
class MemoryUpdateResult:
    content: str
    changed: bool
    updated_at: str | None


class MemoryService:
    """Shared governance views for long-term memory."""

    def __init__(
        self,
        path_service: PathService | None = None,
        store: SQLiteSessionStore | None = None,
        provider: BaseLongTermMemoryProvider | None = None,
        ingestor: SharedMemoryIngestion | None = None,
        projection: SharedMemoryProjection | None = None,
    ) -> None:
        self._path_service = path_service or get_path_service()
        self._store = store or get_sqlite_session_store()
        self._provider = provider or get_long_term_memory_provider()
        self._projection = projection or SharedMemoryProjection()
        self._ingestor = ingestor or SharedMemoryIngestion(self._projection)
        self._migrate_legacy()
        self._bootstrap_provider_from_views()

    @property
    def _memory_dir(self) -> Path:
        return self._path_service.get_memory_dir()

    def _path(self, which: MemoryFile) -> Path:
        return self._memory_dir / _FILENAMES[which]

    def _migrate_legacy(self) -> None:
        """One-time migration from old memory.md to the governance-view system."""
        legacy = self._memory_dir / "memory.md"
        if not legacy.exists():
            return
        if any(self._path(view).exists() for view in MEMORY_FILES):
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

    def _bootstrap_provider_from_views(self) -> None:
        """Seed mem0 from existing governance views when enabling it on an existing install."""
        if not self._provider.is_enabled():
            return
        try:
            if self._provider.list_memories():
                return
            for view in MEMORY_FILES:
                content = self.read_file(view)
                if content:
                    self._ingestor.sync_manual_view(
                        self._provider,
                        view=view,
                        content=content,
                    )
        except Exception:
            logger.debug("Failed to bootstrap provider from existing views", exc_info=True)

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

    def read_progress(self) -> str:
        return self.read_file("progress")

    def _file_updated_at(self, which: MemoryFile) -> str | None:
        path = self._path(which)
        if not path.exists():
            return None
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
        except Exception:
            return None

    def read_snapshot(self) -> MemorySnapshot:
        if self._provider.is_enabled():
            try:
                self._sync_views_from_provider()
            except Exception:
                logger.debug("Failed to sync provider views before snapshot read", exc_info=True)
        return MemorySnapshot(
            summary=self.read_summary(),
            profile=self.read_profile(),
            progress=self.read_progress(),
            summary_updated_at=self._file_updated_at("summary"),
            profile_updated_at=self._file_updated_at("profile"),
            progress_updated_at=self._file_updated_at("progress"),
        )

    # ── Write ─────────────────────────────────────────────────────────

    def write_file(self, which: MemoryFile, content: str) -> MemorySnapshot:
        normalized = str(content or "").strip()
        path = self._path(which)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self._provider.is_enabled() and not normalized:
            try:
                self._clear_provider_view(which)
            except Exception:
                logger.debug(
                    "Failed to clear provider-backed %s memories on empty save",
                    which,
                    exc_info=True,
                )
        if not normalized:
            if path.exists():
                path.unlink()
        else:
            path.write_text(normalized, encoding="utf-8")
        if self._provider.is_enabled():
            try:
                self._ingestor.sync_manual_view(
                    self._provider,
                    view=which,
                    content=normalized,
                )
            except Exception:
                logger.debug("Failed to sync manual %s view to provider", which, exc_info=True)
        return self.read_snapshot()

    def write_memory(self, content: str) -> MemorySnapshot:
        """Legacy compat: write to profile (primary editable file)."""
        return self.write_file("profile", content)

    def clear_file(self, which: MemoryFile) -> MemorySnapshot:
        return self.write_file(which, "")

    def clear_memory(self) -> MemorySnapshot:
        if self._provider.is_enabled():
            try:
                self._provider.clear()
            except Exception:
                logger.debug("Failed to clear provider-backed memories", exc_info=True)
        for view in MEMORY_FILES:
            path = self._path(view)
            if path.exists():
                path.unlink()
        return self.read_snapshot()

    # ── Context building (injected into LLM prompts) ─────────────────

    def build_memory_context(
        self,
        max_chars: int = 4000,
        *,
        query: str = "",
        capability: str = "chat",
    ) -> str:
        if self._provider.is_enabled():
            try:
                all_records = self._provider.list_memories()
                search_records = self._provider.search(query=query, limit=12) if str(query or "").strip() else []
                projected = self._projection.build_context(
                    all_records=all_records,
                    search_records=search_records,
                    capability=capability,
                    max_chars=max_chars,
                )
                if projected:
                    return projected
            except Exception:
                logger.debug("Provider-backed memory context build failed", exc_info=True)

        parts: list[str] = []

        profile = self.read_profile()
        if profile:
            parts.append(f"### User Profile\n{profile}")

        summary = self.read_summary()
        if summary:
            parts.append(f"### Learning Context\n{summary}")

        progress = self.read_progress()
        if progress:
            parts.append(f"### Learning Progress\n{progress}")

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
        if self._provider.is_enabled():
            try:
                rendered = self._projection.preferences_markdown(self._provider.list_memories())
                if rendered:
                    return rendered
            except Exception:
                logger.debug("Provider-backed preference projection failed", exc_info=True)
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

        if self._provider.is_enabled():
            changed = self._ingestor.ingest_turn(
                self._provider,
                user_message=user_message,
                assistant_message=assistant_message,
                session_id=session_id,
                capability=capability,
                language=language,
                timestamp=timestamp,
            )
            snap = self.read_snapshot()
            return MemoryUpdateResult(
                content=snap.profile,
                changed=changed,
                updated_at=snap.profile_updated_at,
            )

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
            message
            for message in messages
            if str(message.get("role", "")) in {"user", "assistant"}
            and str(message.get("content", "") or "").strip()
        ][-max_messages:]

        if not relevant:
            return MemoryUpdateResult(content="", changed=False, updated_at=None)

        if self._provider.is_enabled():
            capability = ""
            session = await self._store.get_session(target)
            if session:
                capability = str(session.get("capability", "") or "")
            changed = self._ingestor.ingest_session(
                self._provider,
                messages=relevant,
                session_id=target,
                capability=capability or "chat",
                language=language,
            )
            snap = self.read_snapshot()
            return MemoryUpdateResult(
                content=snap.profile,
                changed=changed,
                updated_at=snap.profile_updated_at,
            )

        transcript = "\n\n".join(
            f"{'User' if message.get('role') == 'user' else 'Assistant'}: "
            f"{str(message.get('content', '') or '').strip()}"
            for message in relevant
        )

        capability = ""
        session = await self._store.get_session(target)
        if session:
            capability = str(session.get("capability", "") or "")

        source = (
            f"[Session] {target}\n"
            f"[Capability] {capability or 'chat'}\n\n"
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

    async def refresh_from_guide_completion(
        self,
        *,
        notebook_name: str,
        knowledge_points: list[dict[str, object]],
        chat_history: list[dict[str, object]],
        summary: str,
        session_id: str = "",
        language: str = "en",
    ) -> MemoryUpdateResult:
        if self._provider.is_enabled():
            changed = self._ingestor.ingest_guide_completion(
                self._provider,
                notebook_name=notebook_name,
                knowledge_points=knowledge_points,
                chat_history=chat_history,
                summary=summary,
                session_id=session_id,
            )
            snap = self.read_snapshot()
            return MemoryUpdateResult(
                content=snap.progress,
                changed=changed,
                updated_at=snap.progress_updated_at,
            )

        progress_doc = self._build_progress_markdown(
            notebook_name=notebook_name,
            knowledge_points=knowledge_points,
            summary=summary,
        )
        summary_doc = self._build_guide_summary_markdown(
            notebook_name=notebook_name,
            knowledge_points=knowledge_points,
            summary=summary,
        )
        self.write_file("progress", progress_doc)
        if summary_doc:
            self.write_file("summary", summary_doc)
        snap = self.read_snapshot()
        return MemoryUpdateResult(
            content=snap.progress,
            changed=bool(progress_doc or summary_doc),
            updated_at=snap.progress_updated_at,
        )

    # ── LLM rewrite for individual files ──────────────────────────────

    async def _rewrite_one(self, which: MemoryFile, source: str, language: str) -> bool:
        """Rewrite a single memory file. Returns True if changed."""
        current = self.read_file(which)
        zh = str(language).lower().startswith("zh")

        if which == "profile":
            sys_prompt, user_prompt = self._profile_prompts(current, source, zh)
        elif which == "summary":
            sys_prompt, user_prompt = self._summary_prompts(current, source, zh)
        else:
            return False

        chunks: list[str] = []
        async for chunk in llm_stream(
            prompt=user_prompt,
            system_prompt=sys_prompt,
            temperature=0.2,
            max_tokens=900,
        ):
            chunks.append(chunk)

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

    def _sync_views_from_provider(self) -> None:
        records = self._provider.list_memories()
        projected = self._projection.project_views(records)
        self._write_projection_file("profile", projected.profile)
        self._write_projection_file("summary", projected.summary)
        self._write_projection_file("progress", projected.progress)

    def _write_projection_file(self, which: MemoryFile, content: str) -> None:
        path = self._path(which)
        normalized = str(content or "").strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not normalized:
            if path.exists():
                path.unlink()
            return
        path.write_text(normalized, encoding="utf-8")

    def _clear_provider_view(self, which: MemoryFile) -> None:
        if which == "profile":
            scope_categories = PROFILE_CATEGORIES
        elif which == "progress":
            scope_categories = PROGRESS_CATEGORIES
        else:
            scope_categories = SUMMARY_CATEGORIES
        to_delete = []
        for item in self._provider.list_memories():
            category = str(item.category or item.metadata.get("category", "") or "").strip().lower()
            scope = str(item.scope or item.metadata.get("scope", "") or "").strip().lower()
            if scope == which or category in scope_categories:
                if item.id:
                    to_delete.append(item.id)
        if to_delete:
            self._provider.delete_memories(to_delete)

    def _build_progress_markdown(
        self,
        *,
        notebook_name: str,
        knowledge_points: list[dict[str, object]],
        summary: str,
    ) -> str:
        topic = str(notebook_name or "").strip() or "Guided Learning"
        completed = [
            str(point.get("knowledge_title", "") or "").strip()
            for point in knowledge_points
            if str(point.get("knowledge_title", "") or "").strip()
        ]
        needs_review, misconceptions, next_steps = self._extract_progress_sections(summary)

        parts = ["## Active Topics", f"- {topic}", "", f"## Topic: {topic}"]
        if completed:
            parts.append("### Completed Points")
            parts.extend(f"- {line}" for line in completed[:12])
            parts.append("")
        if needs_review:
            parts.append("### Needs Review")
            parts.extend(f"- {line}" for line in needs_review[:8])
            parts.append("")
        if misconceptions:
            parts.append("### Recurring Misconceptions")
            parts.extend(f"- {line}" for line in misconceptions[:8])
            parts.append("")
        if next_steps:
            parts.append("### Next Steps")
            parts.extend(f"- {line}" for line in next_steps[:8])
            parts.append("")
        while parts and not parts[-1]:
            parts.pop()
        return "\n".join(parts).strip()

    def _build_guide_summary_markdown(
        self,
        *,
        notebook_name: str,
        knowledge_points: list[dict[str, object]],
        summary: str,
    ) -> str:
        topic = str(notebook_name or "").strip() or "Guided Learning"
        completed = [
            str(point.get("knowledge_title", "") or "").strip()
            for point in knowledge_points
            if str(point.get("knowledge_title", "") or "").strip()
        ]
        needs_review, misconceptions, _next_steps = self._extract_progress_sections(summary)
        parts = ["## Current Focus", f"- Guided learning: {topic}", ""]
        if completed:
            parts.append("## Accomplishments")
            parts.extend(f"- Completed guided learning on {line}" for line in completed[:10])
            parts.append("")
        if needs_review or misconceptions:
            parts.append("## Open Questions")
            parts.extend(f"- {line}" for line in [*needs_review[:6], *misconceptions[:6]])
            parts.append("")
        while parts and not parts[-1]:
            parts.pop()
        return "\n".join(parts).strip()

    @staticmethod
    def _extract_progress_sections(summary: str) -> tuple[list[str], list[str], list[str]]:
        needs_review: list[str] = []
        misconceptions: list[str] = []
        next_steps: list[str] = []
        current_heading = ""
        for raw in str(summary or "").replace("\r\n", "\n").splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            match = re.match(r"^#{2,3}\s+(.+?)\s*$", stripped)
            if match:
                current_heading = match.group(1).strip().lower()
                continue
            if not stripped.startswith(("- ", "* ")):
                continue
            bullet = stripped[2:].strip()
            if not bullet:
                continue
            if any(key in current_heading for key in ("review", "薄弱", "弱项")):
                if bullet not in needs_review:
                    needs_review.append(bullet)
                continue
            if any(key in current_heading for key in ("question", "misconception", "误区")):
                if bullet not in misconceptions:
                    misconceptions.append(bullet)
                continue
            if any(key in current_heading for key in ("suggest", "next", "建议", "后续")):
                if bullet not in next_steps:
                    next_steps.append(bullet)
        return needs_review, misconceptions, next_steps

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
