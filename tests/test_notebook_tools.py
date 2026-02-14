from pathlib import Path

from noty.memory.notebook import NotiNotebookManager
from noty.memory.sqlite_db import SQLiteDBManager
from noty.tools.notebook_tools import NotebookToolService, register_notebook_tools
from noty.tools.tool_executor import SafeToolExecutor


def test_notebook_tools_registered_and_work(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    notebook = NotiNotebookManager(db_manager=db, logs_dir=str(tmp_path / "logs"))
    executor = SafeToolExecutor(owner_id=1)
    register_notebook_tools(executor, NotebookToolService(notebook=notebook))

    assert {"notebook_add", "notebook_update", "notebook_delete", "notebook_list"}.issubset(executor.tools_registry.keys())

    add_result = executor.execute(
        {"name": "notebook_add", "arguments": {"chat_id": 42, "note": "держать фокус"}},
        user_id=10,
        chat_id=42,
        is_private=False,
    )
    assert add_result["status"] == "success"

    list_result = executor.execute(
        {"name": "notebook_list", "arguments": {"chat_id": 42}},
        user_id=10,
        chat_id=42,
        is_private=False,
    )
    assert list_result["status"] == "success"
    assert list_result["result"]["notes"]
