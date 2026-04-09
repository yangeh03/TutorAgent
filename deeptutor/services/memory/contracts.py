from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MemoryView = Literal["summary", "profile"]


@dataclass(slots=True)
class LongTermMemoryRecord:
    """Normalized memory record returned by the provider layer."""

    id: str
    text: str
    category: str = ""
    scope: str = ""
    source: str = "auto"
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    score: float | None = None


@dataclass(slots=True)
class ProjectedMemoryViews:
    """Projected Markdown governance views backed by long-term memory."""

    profile: str
    summary: str

