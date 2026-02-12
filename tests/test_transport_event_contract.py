from noty.transport.telegram.mapper import map_telegram_update
from noty.transport.router import TransportRouter
from noty.transport.types import normalize_incoming_event
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


def test_routing_key_is_stable_and_contains_scope_fields():
    event = map_vk_event({
        "type": "message_new",
        "object": {"message": {"id": 1, "peer_id": 2000000005, "from_id": 42, "text": "hi"}},
    })

    key = TransportRouter.make_routing_key(event)

    assert key == "vk:2000000005:42"


def test_normalize_event_rejects_missing_required_fields():
    bad_payload = {"platform": "vk", "chat_id": 1}

    try:
        normalize_incoming_event(bad_payload)
    except ValueError as exc:
        assert "отсутствуют поля" in str(exc)
    else:
        raise AssertionError("normalize_incoming_event must reject incomplete payload")
