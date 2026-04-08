"""Notebook service regression tests."""

from __future__ import annotations

from deeptutor.services.notebook.service import NotebookManager, RecordType


def test_add_record_accepts_enum_record_type(tmp_path) -> None:
    manager = NotebookManager(base_dir=str(tmp_path))
    notebook = manager.create_notebook("Notebook test notebook")

    result = manager.add_record(
        notebook_ids=[notebook["id"]],
        record_type=RecordType.CHAT,
        title="Sample",
        user_query="Sample",
        output="# Sample",
    )

    assert result["record"]["type"] == RecordType.CHAT

    stored = manager.get_notebook(notebook["id"])
    assert stored is not None
    assert stored["records"][0]["type"] == "chat"


def test_legacy_co_writer_records_are_filtered(tmp_path) -> None:
    manager = NotebookManager(base_dir=str(tmp_path))
    notebook = manager.create_notebook("Legacy notebook")
    notebook_path = tmp_path / f"{notebook['id']}.json"
    notebook_path.write_text(
        """
        {
          "id": "%s",
          "name": "Legacy notebook",
          "description": "",
          "created_at": 1,
          "updated_at": 1,
          "records": [
            {"id": "r1", "type": "co_writer", "title": "Old", "summary": "", "user_query": "Old", "output": "Old", "metadata": {}, "created_at": 1},
            {"id": "r2", "type": "chat", "title": "Keep", "summary": "", "user_query": "Keep", "output": "Keep", "metadata": {}, "created_at": 1}
          ],
          "color": "#3B82F6",
          "icon": "book"
        }
        """
        % notebook["id"],
        encoding="utf-8",
    )

    loaded = manager.get_notebook(notebook["id"])
    assert loaded is not None
    assert [record["id"] for record in loaded["records"]] == ["r2"]
