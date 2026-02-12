from noty.transport.telegram.mapper import map_telegram_update
from noty.transport.vk.mapper import map_vk_event


REQUIRED_FIELDS = {
    "chat_id",
    "user_id",
    "text",
    "username",
    "chat_name",
    "is_private",
    "platform",
    "raw_event_id",
}


def test_vk_mapping_contract_fields():
    vk_event = {
        "type": "message_new",
        "object": {
            "message": {
                "id": 77,
                "conversation_message_id": 15,
                "peer_id": 2000000001,
                "from_id": 12345,
                "text": "привет",
            }
        },
    }

    event = map_vk_event(vk_event)
    payload = event.to_dict()
    assert REQUIRED_FIELDS.issubset(payload.keys())
    assert payload["platform"] == "vk"
    assert payload["chat_id"] == 2000000001
    assert payload["user_id"] == 12345


def test_telegram_mapping_contract_fields():
    tg_update = {
        "update_id": 10001,
        "message": {
            "message_id": 11,
            "text": "hello",
            "from": {"id": 555, "username": "alice"},
            "chat": {"id": -999, "type": "group", "title": "team chat"},
        },
    }

    event = map_telegram_update(tg_update)
    payload = event.to_dict()
    assert REQUIRED_FIELDS.issubset(payload.keys())
    assert payload["platform"] == "telegram"
    assert payload["chat_id"] == -999
    assert payload["user_id"] == 555
    assert payload["is_private"] is False
