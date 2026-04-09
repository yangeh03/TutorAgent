from __future__ import annotations

from collections import OrderedDict
import re
from typing import Iterable

from .contracts import LongTermMemoryRecord, MemoryView, ProjectedMemoryViews

PROFILE_SECTION_TO_CATEGORY = {
    "identity": "identity",
    "learning style": "learning_style",
    "knowledge level": "knowledge_level",
    "preferences": "preference",
}

SUMMARY_SECTION_TO_CATEGORY = {
    "current focus": "focus",
    "accomplishments": "accomplishment",
    "open questions": "open_question",
}

PROFILE_CATEGORY_TO_SECTION = OrderedDict(
    [
        ("identity", "Identity"),
        ("learning_style", "Learning Style"),
        ("knowledge_level", "Knowledge Level"),
        ("preference", "Preferences"),
    ]
)

SUMMARY_CATEGORY_TO_SECTION = OrderedDict(
    [
        ("focus", "Current Focus"),
        ("goal", "Current Focus"),
        ("accomplishment", "Accomplishments"),
        ("open_question", "Open Questions"),
        ("misconception", "Open Questions"),
    ]
)

PROFILE_CATEGORIES = set(PROFILE_CATEGORY_TO_SECTION)
SUMMARY_CATEGORIES = set(SUMMARY_CATEGORY_TO_SECTION)


class SharedMemoryProjection:
    """Projection utilities for governance views and prompt context."""

    def project_views(self, records: Iterable[LongTermMemoryRecord]) -> ProjectedMemoryViews:
        items = list(records)
        profile_records = self._dedupe_and_prioritize(self._records_for_scope(items, "profile"))
        summary_records = self._dedupe_and_prioritize(self._records_for_scope(items, "summary"))
        return ProjectedMemoryViews(
            profile=self._render_view("profile", profile_records),
            summary=self._render_view("summary", summary_records),
        )

    def build_context(
        self,
        *,
        all_records: Iterable[LongTermMemoryRecord],
        search_records: Iterable[LongTermMemoryRecord] | None = None,
        capability: str = "chat",
        max_chars: int = 4000,
    ) -> str:
        all_items = list(all_records)
        ranked = self._rank_for_context(
            all_records=all_items,
            search_records=list(search_records or []),
            capability=capability,
        )
        if not ranked:
            return ""

        views = self.project_views(ranked)
        parts: list[str] = []
        if views.profile:
            parts.append(f"### User Profile\n{views.profile}")
        if views.summary:
            parts.append(f"### Learning Context\n{views.summary}")
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

    def preferences_markdown(self, records: Iterable[LongTermMemoryRecord]) -> str:
        filtered = [
            item for item in self._records_for_scope(list(records), "profile")
            if self._resolve_category(item) in {"preference", "learning_style", "knowledge_level"}
        ]
        rendered = self._render_view("profile", self._dedupe_and_prioritize(filtered))
        return f"## User Profile\n{rendered}" if rendered else ""

    def parse_manual_view(self, view: MemoryView, content: str) -> list[dict[str, str]]:
        text = str(content or "").replace("\r\n", "\n").strip()
        if not text:
            return []
        section_map = PROFILE_SECTION_TO_CATEGORY if view == "profile" else SUMMARY_SECTION_TO_CATEGORY
        current_category = ""
        bucket: list[dict[str, str]] = []
        paragraph_lines: list[str] = []

        def _flush_paragraph() -> None:
            body = " ".join(line.strip() for line in paragraph_lines if line.strip()).strip()
            paragraph_lines.clear()
            if body and current_category:
                bucket.append({"category": current_category, "text": body})

        for raw in text.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            heading = self._heading_name(stripped)
            if heading is not None:
                _flush_paragraph()
                current_category = section_map.get(heading.lower(), current_category)
                continue
            if not stripped:
                _flush_paragraph()
                continue
            if stripped.startswith(("- ", "* ")):
                _flush_paragraph()
                if current_category:
                    bucket.append({"category": current_category, "text": stripped[2:].strip()})
                continue
            paragraph_lines.append(stripped)
        _flush_paragraph()
        return bucket

    def infer_scope(self, record: LongTermMemoryRecord) -> str:
        scope = str(record.scope or record.metadata.get("scope", "") or "").strip().lower()
        if scope in {"profile", "summary"}:
            return scope
        category = self._resolve_category(record)
        if category in PROFILE_CATEGORIES:
            return "profile"
        if category in SUMMARY_CATEGORIES:
            return "summary"
        return "summary"

    def _records_for_scope(
        self,
        records: list[LongTermMemoryRecord],
        scope: MemoryView,
    ) -> list[LongTermMemoryRecord]:
        selected: list[LongTermMemoryRecord] = []
        for item in records:
            resolved = self.infer_scope(item)
            if resolved != scope:
                continue
            selected.append(self._normalized_record(item, resolved))
        return selected

    def _normalized_record(
        self,
        item: LongTermMemoryRecord,
        scope: str,
    ) -> LongTermMemoryRecord:
        category = self._resolve_category(item)
        if not category:
            category = "open_question" if scope == "summary" else "preference"
        return LongTermMemoryRecord(
            id=item.id,
            text=item.text.strip(),
            category=category,
            scope=scope,
            source=item.source,
            priority=item.priority,
            metadata=item.metadata,
            created_at=item.created_at,
            updated_at=item.updated_at,
            score=item.score,
        )

    def _resolve_category(self, record: LongTermMemoryRecord) -> str:
        category = str(record.category or record.metadata.get("category", "") or "").strip().lower()
        if category:
            return category
        text = str(record.text or "").strip().lower()
        if not text:
            return ""
        if re.search(r"\b(prefer|prefers|like concise|likes concise|want short|wants short|prefer chinese|prefer english)\b", text):
            return "preference"
        if re.search(r"\b(beginner|intermediate|advanced|familiar with|struggles with|strong in)\b", text):
            return "knowledge_level"
        if re.search(r"\b(student|major|phd|undergrad|background|speaks|native language|works as|i am an?|i'm an?)\b", text):
            return "identity"
        if re.search(r"\b(study style|learn best|step-by-step|visual|examples first|socratic)\b", text):
            return "learning_style"
        if re.search(r"\b(goal|objective|preparing for|studying|working on|currently learning|current focus)\b", text):
            return "focus"
        if re.search(r"\b(finished|completed|learned|mastered|solved|wrapped up)\b", text):
            return "accomplishment"
        if re.search(r"\b(confused|unclear|stuck|open question|misconception|keeps mixing|mistake|doesn't understand)\b", text):
            return "misconception"
        return "open_question"

    def _render_view(self, view: MemoryView, records: list[LongTermMemoryRecord]) -> str:
        section_map = PROFILE_CATEGORY_TO_SECTION if view == "profile" else SUMMARY_CATEGORY_TO_SECTION
        buckets: OrderedDict[str, list[str]] = OrderedDict((title, []) for title in section_map.values())
        for item in records:
            category = self._resolve_category(item)
            section = section_map.get(category)
            if not section:
                continue
            text = self._normalize_line(item.text)
            if text and text not in buckets[section]:
                buckets[section].append(text)
        parts: list[str] = []
        for section, lines in buckets.items():
            if not lines:
                continue
            parts.append(f"## {section}")
            parts.extend(f"- {line}" for line in lines[:6])
        return "\n".join(parts).strip()

    def _dedupe_and_prioritize(self, records: list[LongTermMemoryRecord]) -> list[LongTermMemoryRecord]:
        manual_by_category: OrderedDict[str, list[LongTermMemoryRecord]] = OrderedDict()
        auto_by_category: OrderedDict[str, list[LongTermMemoryRecord]] = OrderedDict()
        for item in records:
            category = self._resolve_category(item)
            target = manual_by_category if item.source == "manual_view" else auto_by_category
            target.setdefault(category, []).append(item)

        merged: list[LongTermMemoryRecord] = []
        categories = list(OrderedDict.fromkeys([*manual_by_category.keys(), *auto_by_category.keys()]))
        for category in categories:
            items = manual_by_category.get(category) or auto_by_category.get(category) or []
            items = sorted(
                items,
                key=lambda item: (
                    item.priority,
                    item.updated_at or "",
                    item.created_at or "",
                    item.score or 0.0,
                ),
                reverse=True,
            )
            merged.extend(items[:4])

        seen: set[str] = set()
        deduped: list[LongTermMemoryRecord] = []
        for item in merged:
            key = self._normalize_line(item.text).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _rank_for_context(
        self,
        *,
        all_records: list[LongTermMemoryRecord],
        search_records: list[LongTermMemoryRecord],
        capability: str,
    ) -> list[LongTermMemoryRecord]:
        relevant = self._capability_categories(capability)
        candidate_map: OrderedDict[str, LongTermMemoryRecord] = OrderedDict()

        manual = [
            item for item in all_records
            if item.source == "manual_view" and self._resolve_category(item) in relevant
        ]
        recent = [
            item for item in search_records
            if self._resolve_category(item) in relevant
        ]
        fallback = [
            item for item in all_records
            if self._resolve_category(item) in relevant
        ]

        for item in [*manual, *recent, *fallback]:
            normalized = self._normalize_line(item.text).lower()
            if not normalized or normalized in candidate_map:
                continue
            candidate_map[normalized] = self._normalized_record(item, self.infer_scope(item))
        return self._dedupe_and_prioritize(list(candidate_map.values()))

    @staticmethod
    def _capability_categories(capability: str) -> set[str]:
        name = str(capability or "chat").strip().lower()
        if name in {"deep_solve", "solve"}:
            return {"preference", "learning_style", "knowledge_level", "focus", "open_question", "misconception"}
        if name in {"deep_question", "question", "guide"}:
            return {"knowledge_level", "preference", "focus", "goal", "accomplishment", "open_question", "misconception"}
        if name in {"tutorbot"}:
            return {"identity", "learning_style", "knowledge_level", "preference", "focus", "goal", "open_question"}
        return {"identity", "learning_style", "knowledge_level", "preference", "focus", "goal", "accomplishment", "open_question"}

    @staticmethod
    def _heading_name(line: str) -> str | None:
        match = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        return match.group(1).strip() if match else None

    @staticmethod
    def _normalize_line(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip()).strip("- ").strip()


__all__ = ["SharedMemoryProjection", "PROFILE_CATEGORIES", "SUMMARY_CATEGORIES"]
