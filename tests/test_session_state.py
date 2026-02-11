import time

from noty.memory.session_state import SessionStateStore


def test_session_state_ttl_cleanup():
    store = SessionStateStore(ttl_seconds=1)
    store.set("chat:1", {"a": 1})
    assert store.get("chat:1") == {"a": 1}

    time.sleep(1.1)
    assert store.get("chat:1") is None
    assert store.size() == 0
