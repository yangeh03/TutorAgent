"""
Shared-memory projection: aggregates mem0 records into Markdown views
and capability-aware context strings.

Two responsibilities:
1. **File projection** — generate PROFILE.md / SUMMARY.md from mem0.
2. **Context projection** — build a capability-specific memory_context
   string for injection into LLM prompts.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from .contracts import (
    PROFILE_CATEGORIES,
    SUMMARY_CATEGORIES,
    MemoryCategory,
    MemoryRecord,
)
from .provider import BaseLongTermMemoryProvider

logger = logging.getLogger(__name__)

# Section titles used in PROFILE.md
_PROFILE_SECTION_MAP: dict[MemoryCategory, str] = {
    MemoryCategory.IDENTITY: "Identity",
    MemoryCategory.PREFERENCE: "Preferences",
    MemoryCategory.KNOWLEDGE_LEVEL: "Knowledge Level",
    MemoryCategory.LEARNING_GOAL: "Learning Goals",
}

# Section titles used in SUMMARY.md
_SUMMARY_SECTION_MAP: dict[MemoryCategory, str] = {
    MemoryCategory.CURRENT_TOPIC: "Current Focus",
    MemoryCategory.COMPLETED_NODE: "Accomplishments",
    MemoryCategory.OPEN_QUESTION: "Open Questions",
    MemoryCategory.RECURRING_MISTAKE: "Areas for Improvement",
}

# Capability → which categories to retrieve
_CAPABILITY_CATEGORIES: dict[str, list[MemoryCategory]] = {
    "chat": [
        MemoryCategory.IDENTITY,
        MemoryCategory.PREFERENCE,
        MemoryCategory.CURRENT_TOPIC,
        MemoryCategory.LEARNING_GOAL,
    ],
    "guide": [
        MemoryCategory.LEARNING_GOAL,
        MemoryCategory.COMPLETED_NODE,
        MemoryCategory.RECURRING_MISTAKE,
        MemoryCategory.OPEN_QUESTION,
        MemoryCategory.KNOWLEDGE_LEVEL,
    ],
    "deep_question": [
        MemoryCategory.LEARNING_GOAL,
        MemoryCategory.COMPLETED_NODE,
        MemoryCategory.RECURRING_MISTAKE,
        MemoryCategory.OPEN_QUESTION,
        MemoryCategory.KNOWLEDGE_LEVEL,
    ],
    "deep_solve": [
        MemoryCategory.PREFERENCE,
        MemoryCategory.KNOWLEDGE_LEVEL,
    ],
}

# Default for any unlisted capability
_DEFAULT_CATEGORIES = [
    MemoryCategory.IDENTITY,
    MemoryCategory.PREFERENCE,
    MemoryCategory.CURRENT_TOPIC,
    MemoryCategory.LEARNING_GOAL,
]

DEFAULT_USER_ID = "deeptutor-default-user"


class SharedMemoryProjection:
    """Builds Markdown views and context strings from mem0 records."""

    def __init__(self, provider: BaseLongTermMemoryProvider) -> None:
        self._provider = provider

    # ── File projection (for PROFILE.md / SUMMARY.md) ────────────────

    def project_profile(self, *, user_id: str = DEFAULT_USER_ID) -> str:
        """Generate PROFILE.md content from mem0 records."""
        records = self._provider.get_all(
            user_id=user_id,
            categories=PROFILE_CATEGORIES,
        )
        return self._format_sections(records, _PROFILE_SECTION_MAP)

    def project_summary(self, *, user_id: str = DEFAULT_USER_ID) -> str:
        """Generate SUMMARY.md content from mem0 records."""
        records = self._provider.get_all(
            user_id=user_id,
            categories=SUMMARY_CATEGORIES,
        )
        return self._format_sections(records, _SUMMARY_SECTION_MAP)

    # ── Capability-aware context projection ──────────────────────────

    def project_capability_context(
        self,
        *,
        capability: str = "chat",
        query: str = "",
        user_id: str = DEFAULT_USER_ID,
        max_chars: int = 4000,
    ) -> str:
        """Build a memory_context string tailored to a specific capability.

        For ``deep_solve`` the set is intentionally small and uses semantic
        search with the *query* to surface only relevant facts.  For other
        capabilities, all records in the capability's category set are returned.
        """
        categories = _CAPABILITY_CATEGORIES.get(capability, _DEFAULT_CATEGORIES)

        if capability == "deep_solve" and query:
            records = self._provider.search(
                query,
                user_id=user_id,
                categories=categories,
                limit=10,
            )
        else:
            records = self._provider.get_all(
                user_id=user_id,
                categories=categories,
            )

        if not records:
            return ""

        # Merge the section maps for formatting
        section_map = {**_PROFILE_SECTION_MAP, **_SUMMARY_SECTION_MAP}
        body = self._format_sections(records, section_map)
        if not body:
            return ""

        context = (
            "## Background Memory\n"
            "Use this memory sparingly — only when directly relevant.\n\n"
            f"{body}"
        )
        if len(context) > max_chars:
            context = context[:max_chars].rstrip() + "\n...[truncated]"
        return context

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _format_sections(
        records: list[MemoryRecord],
        section_map: dict[MemoryCategory, str],
    ) -> str:
        """Group records by category and render as Markdown sections."""
        grouped: dict[MemoryCategory, list[str]] = defaultdict(list)
        for r in records:
            if r.text.strip():
                grouped[r.category].append(r.text.strip())

        parts: list[str] = []
        for cat, title in section_map.items():
            items = grouped.get(cat, [])
            if not items:
                continue
            lines = "\n".join(f"- {item}" for item in items)
            parts.append(f"## {title}\n{lines}")

        return "\n\n".join(parts)
