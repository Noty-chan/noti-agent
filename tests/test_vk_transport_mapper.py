from noty.core.events import IncomingEvent
from noty.transport.vk.mapper import map_vk_update_to_incoming_event


def test_map_message_new_update_to_incoming_event():
    update = {
        "type": "message_new",
        "event_id": "evt-123",
        "object": {
            "message": {
                "id": 55,
                "conversation_message_id": 101,
                "peer_id": 2000000010,
                "from_id": 777,
                "text": "Привет, Ноти!",
            }
        },
    }

    event = map_vk_update_to_incoming_event(update)

    assert isinstance(event, IncomingEvent)
    assert event.platform == "vk"
    assert event.chat_id == 2000000010
    assert event.user_id == 777
    assert event.text == "Привет, Ноти!"
    assert event.update_id == "evt-123"


def test_map_ignores_non_message_and_empty_text():
    assert map_vk_update_to_incoming_event({"type": "message_edit"}) is None

    empty_msg_update = {
        "type": "message_new",
        "object": {"message": {"peer_id": 1, "from_id": 2, "text": "  "}},
    }
    assert map_vk_update_to_incoming_event(empty_msg_update) is None
