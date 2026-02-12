from datetime import datetime, timedelta

from noty.memory.session_state import SessionStateStore


def test_cleanup_expired_namespace_only_for_selected_namespace():
    store = SessionStateStore(ttl_seconds=60)
    scope = "vk:100:1"
    store.set("chat", scope, {"chat": "alive"})
    store.set("user", scope, {"user": "alive"})

    store._store["chat"][scope]["expires_at"] = datetime.now() - timedelta(seconds=1)

    removed = store.cleanup_expired_namespace("chat")

    assert removed == 1
    assert store.get("chat", scope) is None
    assert store.get("user", scope) == {"user": "alive"}
