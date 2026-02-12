from pathlib import Path

from noty.transport.vk.state_store import VKStateStore


def test_offset_persists_between_instances(tmp_path: Path):
    state_file = tmp_path / "vk_state.json"
    store = VKStateStore(state_path=str(state_file))

    store.set_longpoll_ts("12345")

    restored = VKStateStore(state_path=str(state_file))
    assert restored.get_longpoll_ts() == "12345"


def test_dedup_uses_bounded_cache(tmp_path: Path):
    state_file = tmp_path / "vk_state.json"
    store = VKStateStore(state_path=str(state_file), dedup_cache_size=3)

    for update_id in [1, 2, 3, 4]:
        store.mark_processed(update_id)

    assert store.is_processed(1) is False
    assert store.is_processed(2) is True
    assert store.is_processed(4) is True
