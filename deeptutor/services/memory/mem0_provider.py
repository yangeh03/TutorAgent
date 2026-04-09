from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .contracts import LongTermMemoryRecord
from .provider import BaseLongTermMemoryProvider

logger = logging.getLogger(__name__)


class Mem0LongTermMemoryProvider(BaseLongTermMemoryProvider):
    """mem0-backed provider for shared long-term memory."""

    backend = "mem0"

    def __init__(
        self,
        client: Any,
        *,
        mode: str,
        user_id: str,
    ) -> None:
        super().__init__(user_id=user_id)
        self._client = client
        self._mode = mode

    @classmethod
    def from_env(cls) -> "Mem0LongTermMemoryProvider":
        from mem0 import Memory, MemoryClient

        user_id = str(os.getenv("MEM0_USER_ID", "deeptutor-default-user") or "deeptutor-default-user")
        config_json = str(os.getenv("MEM0_OSS_CONFIG_JSON", "") or "").strip()
        config_path = str(os.getenv("MEM0_OSS_CONFIG", "") or "").strip()

        if config_json or config_path:
            config: dict[str, Any]
            if config_json:
                try:
                    config = json.loads(config_json)
                except json.JSONDecodeError:
                    import yaml

                    config = yaml.safe_load(config_json) or {}
            else:
                raw = Path(config_path).read_text(encoding="utf-8")
                try:
                    config = json.loads(raw)
                except json.JSONDecodeError:
                    import yaml

                    config = yaml.safe_load(raw) or {}
            try:
                client = Memory.from_config(config)
            except TypeError:
                client = Memory.from_config(config_dict=config)
            return cls(client, mode="oss", user_id=user_id)

        api_key = str(os.getenv("MEM0_API_KEY", "") or "").strip()
        if not api_key:
            raise RuntimeError("MEM0_API_KEY or MEM0_OSS_CONFIG[_JSON] is required for mem0 mode")
        kwargs = {"api_key": api_key}
        org_id = str(os.getenv("MEM0_ORG_ID", "") or "").strip()
        project_id = str(os.getenv("MEM0_PROJECT_ID", "") or "").strip()
        if org_id:
            kwargs["org_id"] = org_id
        if project_id:
            kwargs["project_id"] = project_id
        client = MemoryClient(**kwargs)
        return cls(client, mode="platform", user_id=user_id)

    def add_conversation(
        self,
        *,
        messages: list[dict[str, str]],
        metadata: dict[str, object] | None = None,
    ) -> bool:
        payload = [m for m in messages if str(m.get("content", "") or "").strip()]
        if not payload:
            return False
        kwargs = {
            "user_id": self.user_id,
            "metadata": metadata or {},
        }
        self._call_variants(
            "add",
            [
                ((payload,), {**kwargs, "version": "v2"}),
                (tuple(), {"messages": payload, **kwargs, "version": "v2"}),
                ((payload,), {**kwargs}),
                (tuple(), {"messages": payload, **kwargs}),
            ],
        )
        return True

    def add_fact(
        self,
        *,
        text: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        body = str(text or "").strip()
        if not body:
            return False
        kwargs = {
            "user_id": self.user_id,
            "metadata": metadata or {},
            "infer": False,
        }
        self._call_variants(
            "add",
            [
                ((body,), {**kwargs, "version": "v2"}),
                (tuple(), {"text": body, **kwargs, "version": "v2"}),
                (tuple(), {"memory": body, **kwargs, "version": "v2"}),
                ((body,), {**kwargs}),
                (tuple(), {"text": body, **kwargs}),
                (tuple(), {"memory": body, **kwargs}),
                (tuple(), {"messages": [{"role": "user", "content": body}], **kwargs, "version": "v2"}),
                (tuple(), {"messages": [{"role": "user", "content": body}], **kwargs}),
            ],
        )
        return True

    def search(
        self,
        *,
        query: str,
        limit: int = 8,
    ) -> list[LongTermMemoryRecord]:
        q = str(query or "").strip()
        if not q:
            return []
        raw = self._call_variants(
            "search",
            [
                ((q,), {"user_id": self.user_id, "limit": limit, "version": "v2"}),
                (tuple(), {"query": q, "user_id": self.user_id, "limit": limit, "version": "v2"}),
                ((q,), {"user_id": self.user_id, "top_k": limit, "version": "v2"}),
                (tuple(), {"query": q, "user_id": self.user_id, "top_k": limit, "version": "v2"}),
                ((q,), {"user_id": self.user_id, "limit": limit}),
                (tuple(), {"query": q, "user_id": self.user_id, "limit": limit}),
                ((q,), {"user_id": self.user_id, "top_k": limit}),
                (tuple(), {"query": q, "user_id": self.user_id, "top_k": limit}),
            ],
        )
        return self._normalize_records(raw)

    def list_memories(self) -> list[LongTermMemoryRecord]:
        raw = self._call_variants(
            "get_all",
            [
                (tuple(), {"filters": {"user_id": self.user_id}, "version": "v2"}),
                (tuple(), {"user_id": self.user_id, "version": "v2"}),
                (tuple(), {"filters": {"user_id": self.user_id}}),
                (tuple(), {"user_id": self.user_id}),
            ],
        )
        return self._normalize_records(raw)

    def delete_memories(self, memory_ids: list[str]) -> int:
        ids = [str(item).strip() for item in memory_ids if str(item).strip()]
        if not ids:
            return 0

        if hasattr(self._client, "batch_delete"):
            try:
                self._call_variants(
                    "batch_delete",
                    [
                        (tuple(), {"memory_ids": ids}),
                        ((ids,), {}),
                        (tuple(), {"ids": ids}),
                        (tuple(), {"delete_memories": [{"memory_id": item} for item in ids]}),
                        (tuple(), {"memories": ids}),
                    ],
                )
                return len(ids)
            except Exception:
                logger.debug("mem0 batch delete failed, falling back to per-memory delete", exc_info=True)

        deleted = 0
        for memory_id in ids:
            try:
                self._call_variants(
                    "delete",
                    [
                        ((memory_id,), {}),
                        (tuple(), {"memory_id": memory_id}),
                        (tuple(), {"id": memory_id}),
                        (tuple(), {"memory_id": memory_id, "user_id": self.user_id}),
                    ],
                )
                deleted += 1
            except Exception:
                logger.debug("mem0 delete failed for %s", memory_id, exc_info=True)
        return deleted

    def clear(self) -> int:
        if hasattr(self._client, "delete_all"):
            try:
                self._call_variants(
                    "delete_all",
                    [
                        (tuple(), {"user_id": self.user_id}),
                        (tuple(), {"filters": {"user_id": self.user_id}}),
                    ],
                )
                return 1
            except Exception:
                logger.debug("mem0 delete_all failed, falling back to list+delete", exc_info=True)
        return super().clear()

    def _normalize_records(self, raw: Any) -> list[LongTermMemoryRecord]:
        items: list[Any]
        if isinstance(raw, dict):
            for key in ("results", "memories", "data", "items"):
                candidate = raw.get(key)
                if isinstance(candidate, list):
                    items = candidate
                    break
            else:
                items = [raw]
        elif isinstance(raw, list):
            items = raw
        else:
            items = []

        normalized: list[LongTermMemoryRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = (
                item.get("memory")
                or item.get("text")
                or item.get("content")
                or item.get("value")
                or ""
            )
            text = str(text or "").strip()
            if not text:
                continue
            metadata = item.get("metadata", {}) or {}
            category = str(metadata.get("category", "") or "")
            if not category:
                categories = item.get("categories")
                if isinstance(categories, list) and categories:
                    category = str(categories[0] or "")
            source = str(metadata.get("source", "") or "auto")
            priority = int(metadata.get("priority", 0) or 0)
            score = item.get("score")
            try:
                score_value = float(score) if score is not None else None
            except (TypeError, ValueError):
                score_value = None
            normalized.append(
                LongTermMemoryRecord(
                    id=str(item.get("id") or item.get("memory_id") or ""),
                    text=text,
                    category=category,
                    scope=str(metadata.get("scope", "") or ""),
                    source=source,
                    priority=priority,
                    metadata=metadata if isinstance(metadata, dict) else {},
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                    score=score_value,
                )
            )
        return normalized

    def _call_variants(
        self,
        method_name: str,
        variants: list[tuple[tuple[Any, ...], dict[str, Any]]],
    ) -> Any:
        method = getattr(self._client, method_name)
        last_error: Exception | None = None
        for args, kwargs in variants:
            try:
                return method(*args, **kwargs)
            except TypeError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        return method()


__all__ = ["Mem0LongTermMemoryProvider"]
