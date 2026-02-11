from pathlib import Path

from noty.tools.tool_executor import SafeToolExecutor


def _dummy_tool(name: str) -> str:
    return f"ok:{name}"


def test_action_log_jsonl(tmp_path: Path):
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path))
    executor.register_tool("dummy", _dummy_tool)

    result = executor.execute({"name": "dummy", "arguments": {"name": "n"}}, user_id=1, chat_id=42, is_private=True)

    assert result["status"] == "success"
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert '"function_name": "dummy"' in content
