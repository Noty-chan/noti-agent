"""Tool-call интерфейс для блокнота Ноти."""

from __future__ import annotations

from typing import Any, Dict

from noty.memory.notebook import NotiNotebookManager
from noty.tools.tool_executor import SafeToolExecutor


class NotebookToolService:
    def __init__(self, notebook: NotiNotebookManager):
        self.notebook = notebook

    def notebook_add(self, chat_id: int, note: str) -> Dict[str, Any]:
        return self.notebook.add_note(chat_id=chat_id, note=note)

    def notebook_update(self, chat_id: int, note_id: int, note: str) -> Dict[str, Any]:
        return self.notebook.update_note(chat_id=chat_id, note_id=note_id, note=note)

    def notebook_delete(self, chat_id: int, note_id: int) -> Dict[str, Any]:
        return self.notebook.delete_note(chat_id=chat_id, note_id=note_id)

    def notebook_list(self, chat_id: int, limit: int = 20) -> Dict[str, Any]:
        return self.notebook.list_notes_tool(chat_id=chat_id, limit=limit)


def register_notebook_tools(executor: SafeToolExecutor, service: NotebookToolService) -> None:
    executor.register_tool(
        "notebook_add",
        service.notebook_add,
        description="Добавить короткую важную заметку в блокнот Ноти",
        risk_level="low",
    )
    executor.register_tool(
        "notebook_update",
        service.notebook_update,
        description="Обновить заметку в блокноте Ноти",
        risk_level="low",
    )
    executor.register_tool(
        "notebook_delete",
        service.notebook_delete,
        description="Удалить заметку из блокнота Ноти",
        risk_level="low",
    )
    executor.register_tool(
        "notebook_list",
        service.notebook_list,
        description="Посмотреть текущие заметки блокнота Ноти",
        risk_level="low",
    )
