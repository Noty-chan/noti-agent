from noty.tools.tool_executor import SafeToolExecutor


def test_confirmation_idempotency(tmp_path):
    calls = {"count": 0}

    def _dangerous(arg: str) -> str:
        calls["count"] += 1
        return f"done:{arg}"

    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path))
    executor.register_tool(
        "danger",
        _dangerous,
        requires_owner=True,
        requires_confirmation=True,
        risk_level="critical",
    )

    start = executor.execute({"name": "danger", "arguments": {"arg": "x"}}, user_id=1, chat_id=10, is_private=True)
    assert start["status"] == "awaiting_confirmation"

    first = executor.confirm_pending(start["confirmation_id"])
    second = executor.confirm_pending(start["confirmation_id"])

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert second["idempotent"] is True
    assert calls["count"] == 1


def test_standardized_statuses(tmp_path):
    executor = SafeToolExecutor(owner_id=10, actions_log_dir=str(tmp_path))
    executor.register_tool("tool", lambda: "ok", requires_owner=True)

    missing = executor.execute({"name": "nope", "arguments": {}}, user_id=10, chat_id=1, is_private=True)
    forbidden = executor.execute({"name": "tool", "arguments": {}}, user_id=11, chat_id=1, is_private=True)
    invalid_args = executor.execute({"name": "tool", "arguments": "bad"}, user_id=10, chat_id=1, is_private=True)

    assert missing["status"] == "validation_error"
    assert forbidden["status"] == "forbidden"
    assert invalid_args["status"] == "validation_error"
