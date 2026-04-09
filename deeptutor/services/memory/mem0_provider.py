"""
mem0 OSS provider for L2 shared long-term memory.

Uses local ChromaDB for vector storage — no cloud dependency.
LLM and Embedder are configured independently via ``MEM0_*`` env vars.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .contracts import IngestionResult, MemoryCategory, MemoryRecord
from .provider import BaseLongTermMemoryProvider

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "deeptutor-default-user"

# ── Custom extraction prompt for tutoring domain ─────────────────────

_FACT_EXTRACTION_PROMPT = """\
You are a memory manager for an intelligent tutoring system.
Analyze the conversation and extract ONLY long-term valuable facts about the learner.

Each fact MUST be prefixed with a category tag in square brackets, followed by the fact.
Valid categories: [identity] [preference] [learning_goal] [knowledge_level] [current_topic] [open_question] [completed_node] [recurring_mistake]

Category meanings:
- identity: name, role, background, native language
- preference: learning style, explanation preferences, response format
- learning_goal: what the user wants to learn or master
- knowledge_level: assessed proficiency on specific topics
- current_topic: what they are currently studying
- open_question: unresolved questions or confusions
- completed_node: finished learning milestones or mastered concepts
- recurring_mistake: patterns of errors the user repeatedly makes

IMPORTANT — do NOT extract:
- One-time factual questions and their answers
- Greetings, smalltalk, pleasantries
- Tool call details, code execution traces
- Temporary session state or scratchpad notes
- Information that is only relevant to the current conversation

Example output format:
- [identity] The user is a second-year college student
- [current_topic] Currently studying linear algebra
- [preference] Prefers learning through examples before abstract concepts

If there is nothing worth remembering, return an empty list.
"""


# ── Provider ─────────────────────────────────────────────────────────

class Mem0LongTermMemoryProvider(BaseLongTermMemoryProvider):
    """mem0 OSS backend with local ChromaDB vector store."""

    name = "mem0"

    def __init__(self, *, data_dir: Path | None = None) -> None:
        from mem0 import Memory

        if data_dir is None:
            from deeptutor.services.path_service import get_path_service
            data_dir = get_path_service().project_root / "data" / "mem0"

        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)

        config = self._build_config(data_dir)
        self._mem0 = Memory(config=config)
        self._available = True

    # ── Config helpers ───────────────────────────────────────────────

    @staticmethod
    def _build_config(data_dir: Path) -> Any:
        """Build a ``MemoryConfig`` object from ``MEM0_*`` env vars."""
        from mem0.configs.base import MemoryConfig
        from mem0.embeddings.configs import EmbedderConfig
        from mem0.llms.configs import LlmConfig
        from mem0.vector_stores.configs import VectorStoreConfig

        # LLM config (independent from main DeepTutor LLM)
        llm_provider = os.getenv("MEM0_LLM_PROVIDER", "openai").strip()
        llm_cfg: dict[str, Any] = {}
        llm_model = os.getenv("MEM0_LLM_MODEL", "").strip()
        llm_api_key = os.getenv("MEM0_LLM_API_KEY", "").strip()
        llm_base_url = os.getenv("MEM0_LLM_BASE_URL", "").strip()
        if llm_model:
            llm_cfg["model"] = llm_model
        if llm_api_key:
            llm_cfg["api_key"] = llm_api_key
        if llm_base_url:
            llm_cfg["openai_base_url"] = llm_base_url

        # Embedder config (independent from main DeepTutor embedding)
        emb_provider = os.getenv("MEM0_EMBEDDER_PROVIDER", "openai").strip()
        emb_cfg: dict[str, Any] = {}
        emb_model = os.getenv("MEM0_EMBEDDER_MODEL", "").strip()
        emb_api_key = os.getenv("MEM0_EMBEDDER_API_KEY", "").strip()
        emb_base_url = os.getenv("MEM0_EMBEDDER_BASE_URL", "").strip()
        if emb_model:
            emb_cfg["model"] = emb_model
        if emb_api_key:
            emb_cfg["api_key"] = emb_api_key
        if emb_base_url:
            emb_cfg["openai_base_url"] = emb_base_url

        return MemoryConfig(
            vector_store=VectorStoreConfig(
                provider="chroma",
                config={
                    "collection_name": "deeptutor_memory",
                    "path": str(data_dir / "chroma"),
                },
            ),
            llm=LlmConfig(provider=llm_provider, config=llm_cfg),
            embedder=EmbedderConfig(provider=emb_provider, config=emb_cfg),
            history_db_path=str(data_dir / "history.db"),
            custom_fact_extraction_prompt=_FACT_EXTRACTION_PROMPT,
        )

    # ── Write ────────────────────────────────────────────────────────

    def add(
        self,
        text: str,
        *,
        category: MemoryCategory = MemoryCategory.PREFERENCE,
        user_id: str = DEFAULT_USER_ID,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        meta = dict(metadata or {})
        meta["category"] = category.value
        try:
            result = self._mem0.add(
                text,
                user_id=user_id,
                metadata=meta,
                infer=False,
            )
            results = result.get("results", []) if isinstance(result, dict) else []
            if results:
                return str(results[0].get("id", ""))
            return None
        except Exception:
            logger.warning("mem0 add failed", exc_info=True)
            return None

    def add_from_conversation(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: str = DEFAULT_USER_ID,
        metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        meta = dict(metadata or {})
        try:
            result = self._mem0.add(
                messages,
                user_id=user_id,
                metadata=meta,
                infer=True,
            )
            return self._parse_ingestion_result(result)
        except Exception:
            logger.warning("mem0 add_from_conversation failed", exc_info=True)
            return IngestionResult()

    # ── Read ─────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        user_id: str = DEFAULT_USER_ID,
        categories: list[MemoryCategory] | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        try:
            # Fetch more than needed so we can filter by category in Python
            fetch_limit = limit * 3 if categories else limit
            result = self._mem0.search(query, user_id=user_id, limit=fetch_limit)
            raw_list = result.get("results", []) if isinstance(result, dict) else result
            records = [self._to_record(r, score=r.get("score", 0.0)) for r in raw_list]
            if categories:
                cat_set = set(categories)
                records = [r for r in records if r.category in cat_set]
            return records[:limit]
        except Exception:
            logger.warning("mem0 search failed", exc_info=True)
            return []

    def get_all(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        categories: list[MemoryCategory] | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        try:
            # Category lives in the text prefix, not in metadata, so we
            # fetch everything and filter in Python after _to_record parsing.
            fetch_limit = limit * 2 if categories else limit
            result = self._mem0.get_all(user_id=user_id, limit=fetch_limit)
            raw_list = result.get("results", []) if isinstance(result, dict) else result
            records = [self._to_record(r) for r in raw_list]
            if categories:
                cat_set = set(categories)
                records = [r for r in records if r.category in cat_set]
            return records[:limit]
        except Exception:
            logger.warning("mem0 get_all failed", exc_info=True)
            return []

    # ── Mutate ───────────────────────────────────────────────────────

    def update(self, memory_id: str, text: str, metadata: dict[str, Any] | None = None) -> bool:
        try:
            kwargs: dict[str, Any] = {"memory_id": memory_id, "data": text}
            if metadata:
                kwargs["metadata"] = metadata
            self._mem0.update(**kwargs)
            return True
        except Exception:
            logger.warning("mem0 update failed", exc_info=True)
            return False

    def delete(self, memory_id: str) -> bool:
        try:
            self._mem0.delete(memory_id=memory_id)
            return True
        except Exception:
            logger.warning("mem0 delete failed", exc_info=True)
            return False

    def delete_all(self, *, user_id: str = DEFAULT_USER_ID) -> bool:
        try:
            self._mem0.delete_all(user_id=user_id)
            return True
        except Exception:
            logger.warning("mem0 delete_all failed", exc_info=True)
            return False

    # ── Status ───────────────────────────────────────────────────────

    def is_available(self) -> bool:
        return self._available

    # ── Internal helpers ─────────────────────────────────────────────

    @staticmethod
    def _to_record(raw: dict[str, Any], score: float = 0.0) -> MemoryRecord:
        """Convert a mem0 result dict to ``MemoryRecord``.

        Category is resolved in priority order:
        1. ``metadata.category`` (if present)
        2. ``[category_tag]`` prefix in the memory text
        3. ``{"category": "..."}`` JSON suffix in the memory text
        4. Fallback to ``PREFERENCE``
        """
        import re

        meta = raw.get("metadata", {}) or {}
        text = str(raw.get("memory", ""))
        category = MemoryCategory.PREFERENCE

        # 1. Try metadata.category
        cat_str = meta.get("category", "")
        if cat_str:
            try:
                category = MemoryCategory(cat_str)
            except ValueError:
                pass

        # 2. Try [tag] prefix:  "[identity] The user is ..."
        if category == MemoryCategory.PREFERENCE:
            tag_match = re.match(r"^\[(\w+)\]\s*", text)
            if tag_match:
                tag = tag_match.group(1).lower()
                try:
                    category = MemoryCategory(tag)
                    text = text[tag_match.end():].strip()
                except ValueError:
                    pass

        # 3. Try JSON suffix:  'some text {"category": "identity"}'
        if category == MemoryCategory.PREFERENCE:
            json_match = re.search(r'\{"category":\s*"(\w+)"\}\s*$', text)
            if json_match:
                tag = json_match.group(1).lower()
                try:
                    category = MemoryCategory(tag)
                    text = text[:json_match.start()].strip()
                except ValueError:
                    pass

        return MemoryRecord(
            id=str(raw.get("id", "")),
            text=text,
            category=category,
            score=score,
            created_at=str(raw.get("created_at", "")),
            updated_at=str(raw.get("updated_at", "")),
            metadata=meta,
        )

    @staticmethod
    def _parse_ingestion_result(result: Any) -> IngestionResult:
        """Parse mem0 ``add()`` response into ``IngestionResult``."""
        if not isinstance(result, dict):
            return IngestionResult()
        results = result.get("results", [])
        added = sum(1 for r in results if r.get("event") == "ADD")
        updated = sum(1 for r in results if r.get("event") == "UPDATE")
        unchanged = sum(1 for r in results if r.get("event") not in ("ADD", "UPDATE"))
        return IngestionResult(added=added, updated=updated, unchanged=unchanged)
