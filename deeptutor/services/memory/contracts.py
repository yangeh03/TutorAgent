"""
L2 shared long-term memory data contracts.

These types form the boundary between DeepTutor's memory module and any
backend provider (mem0, file-only, etc.).  Nothing in this file imports
mem0 or any other provider-specific library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryCategory(str, Enum):
    """Taxonomy for L2 long-term memory facts."""

    PREFERENCE = "preference"
    LEARNING_GOAL = "learning_goal"
    KNOWLEDGE_LEVEL = "knowledge_level"
    CURRENT_TOPIC = "current_topic"
    OPEN_QUESTION = "open_question"
    COMPLETED_NODE = "completed_node"
    RECURRING_MISTAKE = "recurring_mistake"
    IDENTITY = "identity"


# Categories that map to PROFILE.md
PROFILE_CATEGORIES: list[MemoryCategory] = [
    MemoryCategory.IDENTITY,
    MemoryCategory.PREFERENCE,
    MemoryCategory.KNOWLEDGE_LEVEL,
    MemoryCategory.LEARNING_GOAL,
]

# Categories that map to SUMMARY.md
SUMMARY_CATEGORIES: list[MemoryCategory] = [
    MemoryCategory.CURRENT_TOPIC,
    MemoryCategory.OPEN_QUESTION,
    MemoryCategory.COMPLETED_NODE,
    MemoryCategory.RECURRING_MISTAKE,
]


@dataclass
class MemoryRecord:
    """A single long-term memory fact."""

    id: str
    text: str
    category: MemoryCategory
    score: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    """Outcome of a write / ingestion operation."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def changed(self) -> bool:
        return self.added > 0 or self.updated > 0
