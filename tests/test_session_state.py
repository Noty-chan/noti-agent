import time

from noty.memory.session_state import SessionStateStore


def test_session_state_ttl_cleanup():
    store = SessionStateStore(ttl_seconds=1)
    store.set("chat", "vk:1", {"a": 1})
    assert store.get("chat", "vk:1") == {"a": 1}

    time.sleep(1.1)
    assert store.get("chat", "vk:1") is None
    assert store.size() == 0


def test_session_state_clear_scope_all_namespaces():
    store = SessionStateStore(ttl_seconds=60)
    scope = "vk:123:9"
    store.set("chat", scope, {"chat": 1})
    store.set("user", scope, {"user": 1})
    store.set("flow", scope, {"flow": 1})

    removed = store.clear_scope(scope)

    assert removed == 3
    assert store.get("chat", scope) is None
    assert store.get("user", scope) is None
    assert store.get("flow", scope) is None
