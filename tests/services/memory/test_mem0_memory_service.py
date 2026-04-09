from __future__ import annotations

from deeptutor.services.memory.contracts import LongTermMemoryRecord
from deeptutor.services.memory.provider import BaseLongTermMemoryProvider
from deeptutor.services.memory.service import MemoryService
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


class FakeMem0Provider(BaseLongTermMemoryProvider):
    backend = "fake-mem0"

    def __init__(self) -> None:
        super().__init__(user_id="test-user")
        self._items: list[LongTermMemoryRecord] = []
        self._seq = 0

    def add_conversation(self, *, messages, metadata=None) -> bool:
        text = "\n".join(str(item.get("content", "") or "") for item in messages).lower()
        changed = False
        if "concise answers" in text:
            changed = self.add_fact(
                text="Prefers concise answers.",
                metadata={"scope": "profile", "category": "preference", "source": "auto"},
            ) or changed
        if "linear algebra" in text:
            changed = self.add_fact(
                text="Currently studying linear algebra.",
                metadata={"scope": "summary", "category": "focus", "source": "auto"},
            ) or changed
        if "mixing eigenvalues and eigenvectors" in text:
            changed = self.add_fact(
                text="Keeps mixing eigenvalues and eigenvectors.",
                metadata={"scope": "summary", "category": "misconception", "source": "auto"},
            ) or changed
        return changed

    def add_fact(self, *, text, metadata=None) -> bool:
        self._seq += 1
        item = LongTermMemoryRecord(
            id=f"m{self._seq}",
            text=str(text),
            category=str((metadata or {}).get("category", "") or ""),
            scope=str((metadata or {}).get("scope", "") or ""),
            source=str((metadata or {}).get("source", "auto") or "auto"),
            priority=int((metadata or {}).get("priority", 0) or 0),
            metadata=dict(metadata or {}),
        )
        self._items.append(item)
        return True

    def search(self, *, query, limit=8):
        q = str(query or "").lower()
        items = [item for item in self._items if q in item.text.lower()]
        manual = [item for item in self._items if item.source == "manual_view"]
        merged = []
        seen = set()
        for item in [*manual, *items]:
            if item.id in seen:
                continue
            seen.add(item.id)
            merged.append(item)
        return merged[:limit]

    def list_memories(self):
        return list(self._items)

    def delete_memories(self, memory_ids):
        ids = set(memory_ids)
        before = len(self._items)
        self._items = [item for item in self._items if item.id not in ids]
        return before - len(self._items)


def _make_service(tmp_path, provider: BaseLongTermMemoryProvider | None = None):
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    return MemoryService(
        path_service=type(
            "PathServiceStub",
            (),
            {"get_memory_dir": lambda self: tmp_path / "memory"},
        )(),
        store=store,
        provider=provider,
    )


def test_mem0_refresh_turn_projects_profile_and_summary(tmp_path) -> None:
    provider = FakeMem0Provider()
    service = _make_service(tmp_path, provider=provider)

    import asyncio

    result = asyncio.run(
        service.refresh_from_turn(
            user_message="I'm studying linear algebra and I prefer concise answers.",
            assistant_message="Understood. I'll keep answers concise while we work on linear algebra.",
            session_id="s1",
            capability="chat",
            language="en",
        )
    )

    snapshot = service.read_snapshot()
    assert result.changed is True
    assert "concise answers" in snapshot.profile.lower()
    assert "linear algebra" in snapshot.summary.lower()


def test_mem0_manual_profile_edit_overrides_auto_projection(tmp_path) -> None:
    provider = FakeMem0Provider()
    provider.add_fact(
        text="Prefers detailed answers.",
        metadata={"scope": "profile", "category": "preference", "source": "auto"},
    )
    service = _make_service(tmp_path, provider=provider)

    snapshot = service.write_file("profile", "## Preferences\n- Prefer concise answers.")
    assert "concise answers" in snapshot.profile.lower()
    assert "detailed answers" not in snapshot.profile.lower()

    context = service.build_memory_context(query="How should you answer?", capability="chat")
    assert "concise answers" in context.lower()


def test_mem0_clear_profile_keeps_summary_memories(tmp_path) -> None:
    provider = FakeMem0Provider()
    provider.add_fact(
        text="Prefers concise answers.",
        metadata={"scope": "profile", "category": "preference", "source": "auto"},
    )
    provider.add_fact(
        text="Currently studying linear algebra.",
        metadata={"scope": "summary", "category": "focus", "source": "auto"},
    )
    service = _make_service(tmp_path, provider=provider)

    snapshot = service.clear_file("profile")
    assert snapshot.profile == ""
    assert "linear algebra" in snapshot.summary.lower()
    assert all(item.scope != "profile" for item in provider.list_memories())

