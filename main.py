"""Точка входа проекта Noty с запуском VK transport."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from noty.core.api_rotator import APIRotator
from noty.core.bot import NotyBot
from noty.core.context_manager import DynamicContextBuilder
from noty.core.events import InteractionJSONLLogger
from noty.core.message_handler import MessageHandler
from noty.filters.embedding_filter import EmbeddingFilter
from noty.filters.heuristic_filter import HeuristicFilter
from noty.memory.semantic_retriever import LlamaSemanticRetriever
from noty.memory.notebook import NotiNotebookManager
from noty.memory.sqlite_db import SQLiteDBManager
from noty.memory.recent_days_memory import RecentDaysMemory
from noty.mood.mood_manager import MoodManager
from noty.prompts.prompt_builder import ModularPromptBuilder
from noty.thought.monologue import InternalMonologue, ThoughtLogger
from noty.tools.notebook_tools import NotebookToolService, register_notebook_tools
from noty.tools.tool_executor import SafeToolExecutor
from noty.transport.vk.client import VKAPIClient
from noty.transport.vk.polling import VKLongPollTransport
from noty.transport.vk.state_store import VKStateStore
from noty.transport.vk.webhook import VKWebhookHandler
from noty.utils.logger import configure_logging
from noty.utils.metrics import MetricsCollector


def load_yaml(path: str) -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_api_keys(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("openrouter_keys", [])


def build_bot(config: Dict[str, Any]) -> NotyBot:
    db_manager = SQLiteDBManager()
    embedding_filter = EmbeddingFilter()
    semantic_retriever = LlamaSemanticRetriever()
    metrics = MetricsCollector()
    recent_days_memory = RecentDaysMemory(db_manager=db_manager)
    context_builder = DynamicContextBuilder(
        db_manager=db_manager,
        embedding_filter=embedding_filter,
        max_tokens=config["bot"].get("max_context_tokens", 3000),
        semantic_retriever=semantic_retriever,
        recent_days_memory=recent_days_memory,
        metrics=metrics,
    )
    prompt_builder = ModularPromptBuilder()
    message_handler = MessageHandler(
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        heuristic_filter=HeuristicFilter(pass_probability=config["bot"].get("react_target_rate", 0.2)),
        embedding_filter=embedding_filter,
        metrics=metrics,
    )
    mood_manager = MoodManager()
    tool_executor = SafeToolExecutor(owner_id=config["transport"].get("owner_id", 0))
    notebook_manager = NotiNotebookManager(db_manager=db_manager)
    register_notebook_tools(tool_executor, NotebookToolService(notebook=notebook_manager))
    api_rotator = APIRotator(
        api_keys=load_api_keys("./noty/config/api_keys.json"),
        backend=config.get("llm", {}).get("backend", "openai"),
    )
    monologue = InternalMonologue(api_rotator=api_rotator, thought_logger=ThoughtLogger())

    return NotyBot(
        api_rotator=api_rotator,
        message_handler=message_handler,
        mood_manager=mood_manager,
        tool_executor=tool_executor,
        monologue=monologue,
        db_manager=db_manager,
        interaction_logger=InteractionJSONLLogger(),
        metrics=metrics,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Noty bot runner")
    parser.add_argument("--mode", choices=["vk_longpoll", "vk_webhook", "dry_run"], default=None)
    args = parser.parse_args()

    configure_logging()
    config = load_yaml("./noty/config/bot_config.yaml")
    mode = args.mode or config.get("transport", {}).get("mode", "dry_run")

    if mode == "dry_run":
        print("Noty dry_run: transport не запускается")
        return

    bot = build_bot(config)
    transport_cfg = config.get("transport", {})
    client = VKAPIClient(
        token=transport_cfg["vk_token"],
        group_id=transport_cfg["vk_group_id"],
        api_version=transport_cfg.get("vk_api_version", "5.199"),
        timeout_seconds=transport_cfg.get("timeout_seconds", 25),
    )
    state_store = VKStateStore(
        state_path=transport_cfg.get("state_path", "./noty/data/vk_state.json"),
        dedup_cache_size=transport_cfg.get("dedup_cache_size", 5000),
    )

    if mode == "vk_longpoll":
        VKLongPollTransport(client=client, bot=bot, state_store=state_store).run_forever()
        return

    webhook = VKWebhookHandler(
        client=client,
        bot=bot,
        state_store=state_store,
        confirmation_token=transport_cfg.get("vk_confirmation_token"),
    )
    print("VK webhook mode инициализирован. Используй VKWebhookHandler.handle_update(payload).")
    _ = webhook


if __name__ == "__main__":
    main()
