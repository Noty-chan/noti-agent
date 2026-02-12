"""VK transport (longpoll/webhook)."""

from .client import VKAPIClient
from .polling import VKLongPollTransport
from .state_store import VKStateStore
from .webhook import VKWebhookHandler

__all__ = ["VKAPIClient", "VKLongPollTransport", "VKStateStore", "VKWebhookHandler"]
