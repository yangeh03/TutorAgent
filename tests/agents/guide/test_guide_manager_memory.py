from __future__ import annotations

import asyncio

from deeptutor.agents.guide.guide_manager import GuideManager


class _FakeDesignAgent:
    def __init__(self, *_args, **_kwargs) -> None:
        self.last_input = ""

    async def process(self, user_input: str):
        self.last_input = user_input
        return {
            "success": True,
            "knowledge_points": [
                {"knowledge_title": "Derivatives", "knowledge_summary": "", "user_difficulty": ""},
            ],
        }


class _FakeInteractiveAgent:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


class _FakeChatAgent:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


class _FakeSummaryAgent:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def process(self, **_kwargs):
        return {"summary": "## Follow-up Learning Suggestions\n- Review implicit differentiation."}


class _FakeMemoryService:
    def __init__(self) -> None:
        self.guide_completion_calls: list[dict] = []

    def build_memory_context(self, **_kwargs) -> str:
        return "## Learning Progress\n## Active Topics\n- Calculus / Limits"

    async def refresh_from_guide_completion(self, **kwargs):
        self.guide_completion_calls.append(kwargs)
        return type("Result", (), {"changed": True, "content": "", "updated_at": None})()


def test_guide_manager_reads_shared_memory_for_design(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.DesignAgent", _FakeDesignAgent)
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.InteractiveAgent", _FakeInteractiveAgent)
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.ChatAgent", _FakeChatAgent)
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.SummaryAgent", _FakeSummaryAgent)

    memory_service = _FakeMemoryService()
    manager = GuideManager(
        api_key="test",
        base_url="http://example.com",
        output_dir=str(tmp_path),
        language="en",
        memory_service=memory_service,
    )

    result = asyncio.run(manager.create_session(user_input="Teach me derivatives"))

    assert result["success"] is True
    assert "[Shared Memory]" in manager.design_agent.last_input
    assert "Calculus / Limits" in manager.design_agent.last_input


def test_guide_manager_syncs_completion_to_shared_memory(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.DesignAgent", _FakeDesignAgent)
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.InteractiveAgent", _FakeInteractiveAgent)
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.ChatAgent", _FakeChatAgent)
    monkeypatch.setattr("deeptutor.agents.guide.guide_manager.SummaryAgent", _FakeSummaryAgent)

    memory_service = _FakeMemoryService()
    manager = GuideManager(
        api_key="test",
        base_url="http://example.com",
        output_dir=str(tmp_path),
        language="en",
        memory_service=memory_service,
    )
    create_result = asyncio.run(manager.create_session(user_input="Teach me derivatives"))

    completion = asyncio.run(manager.complete_learning(create_result["session_id"]))

    assert completion["success"] is True
    assert len(memory_service.guide_completion_calls) == 1
    payload = memory_service.guide_completion_calls[0]
    assert payload["notebook_name"] == "Teach me derivatives"
    assert payload["session_id"] == create_result["session_id"]
    assert payload["knowledge_points"][0]["knowledge_title"] == "Derivatives"
