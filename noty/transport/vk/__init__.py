"""VK transport namespace."""

from .mapper import map_vk_event, map_vk_update_to_incoming_event

__all__ = ["map_vk_event", "map_vk_update_to_incoming_event"]
