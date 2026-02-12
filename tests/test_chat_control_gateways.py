import json
from pathlib import Path

from noty.tools.chat_control import ChatControlService, register_chat_control_tools
from noty.tools.gateways.tg_moderation import TGModerationGateway
from noty.tools.gateways.vk_moderation import VKModerationGateway
from noty.tools.tool_executor import SafeToolExecutor


class VKSDKMock:
    def __init__(self):
        self.calls = []

    def warn_user(self, **kwargs):
        self.calls.append(("warn_user", kwargs))
        return "vk_warn_1"

    def mute_user(self, **kwargs):
        self.calls.append(("mute_user", kwargs))
        return "vk_mute_1"

    def ban_user(self, **kwargs):
        self.calls.append(("ban_user", kwargs))
        return "vk_ban_1"

    def delete_message(self, **kwargs):
        self.calls.append(("delete_message", kwargs))
        return True

    def bulk_delete_messages(self, **kwargs):
        self.calls.append(("bulk_delete_messages", kwargs))
        return kwargs["message_ids"]


class TGSDKMock:
    def __init__(self):
        self.calls = []

    def send_warning(self, **kwargs):
        self.calls.append(("send_warning", kwargs))
        return 991

    def restrict_user(self, **kwargs):
        self.calls.append(("restrict_user", kwargs))
        return 171717

    def ban_user(self, **kwargs):
        self.calls.append(("ban_user", kwargs))
        return True

    def delete_message(self, **kwargs):
        self.calls.append(("delete_message", kwargs))
        return True

    def bulk_delete_messages(self, **kwargs):
        self.calls.append(("bulk_delete_messages", kwargs))
        return len(kwargs["message_ids"])


def test_vk_gateway_and_action_log_contract(tmp_path: Path):
    vk_sdk = VKSDKMock()
    gateway = VKModerationGateway(vk_sdk)
    service = ChatControlService(gateway, actions_log_dir=str(tmp_path))

    result = service.mute_user(chat_id=10, user_id=20, minutes=15, reason="spam")

    assert result["platform"] == "vk"
    assert vk_sdk.calls == [
        (
            "mute_user",
            {"chat_id": 10, "user_id": 20, "minutes": 15, "reason": "spam"},
        )
    ]

    log_files = sorted(tmp_path.glob("*.jsonl"))
    assert len(log_files) == 1
    entry = json.loads(log_files[0].read_text(encoding="utf-8").strip())
    assert entry["platform"] == "vk"
    assert entry["action"] == "mute"
    assert entry["metadata"]["chat_id"] == 10
    assert entry["metadata"]["user_id"] == 20


def test_tg_gateway_contract():
    tg_sdk = TGSDKMock()
    gateway = TGModerationGateway(tg_sdk)

    result = gateway.warn_user(chat_id=77, user_id=88, reason="caps")

    assert result["platform"] == "tg"
    assert result["warning_note_id"] == 991
    assert tg_sdk.calls == [
        (
            "send_warning",
            {"chat_id": 77, "user_id": 88, "reason": "caps"},
        )
    ]


def test_chat_control_tools_registration_security_flags(tmp_path: Path):
    gateway = VKModerationGateway(VKSDKMock())
    service = ChatControlService(gateway, actions_log_dir=str(tmp_path))
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path))

    register_chat_control_tools(executor, service)

    assert executor.tools_registry["ban_user"]["requires_owner"] is True
    assert executor.tools_registry["ban_user"]["requires_confirmation"] is True
    assert executor.tools_registry["mute_user_long"]["requires_owner"] is True
    assert executor.tools_registry["mute_user_long"]["requires_confirmation"] is True
    assert executor.tools_registry["bulk_delete_messages"]["requires_owner"] is True
    assert executor.tools_registry["bulk_delete_messages"]["requires_confirmation"] is True

    resp = executor.execute(
        {
            "name": "ban_user",
            "arguments": {"chat_id": 100, "user_id": 222, "reason": "raid"},
        },
        user_id=1,
        chat_id=100,
        is_private=True,
    )
    assert resp["status"] == "awaiting_confirmation"
