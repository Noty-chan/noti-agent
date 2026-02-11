import json
from pathlib import Path

from noty.tools.tool_executor import SafeToolExecutor


def _danger(arg: str) -> str:
    return f"done:{arg}"


def test_dangerous_actions_audited(tmp_path: Path):
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path))
    executor.register_tool(
        "danger",
        _danger,
        requires_owner=True,
        requires_confirmation=True,
        risk_level="critical",
    )

    r = executor.execute({"name": "danger", "arguments": {"arg": "x"}}, user_id=1, chat_id=99, is_private=True)
    assert r["status"] == "awaiting_confirmation"
    c = executor.confirm_pending(r["confirmation_id"])
    assert c["status"] == "success"

    audit = tmp_path / "dangerous_audit.jsonl"
    lines = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    stages = {item["stage"] for item in lines}
    assert "confirmation_requested" in stages
    assert "confirmed_and_executed" in stages
