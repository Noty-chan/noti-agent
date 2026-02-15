import sqlite3

from noty.core.bot import NotyBot
from noty.core.response_processor import ResponseProcessor
from noty.memory.sqlite_db import SQLiteDBManager
from noty.mood.mood_manager import MoodManager
from noty.tools.tool_executor import SafeToolExecutor


class _Decision:
    should_respond = True
    reason = "interesting"
    score = 1.0
    threshold = 0.5


class _MessageHandlerStub:
    prompt_builder = type("PB", (), {"current_personality_version": 1})()

    def decide_reaction(self, text: str):
        return _Decision()

    def prepare_prompt(self, **kwargs):
        return "prompt"

    def get_filter_stats(self):
        return {"respond_rate": 1.0}


class _MonologueStub:
    def generate_thoughts(self, context, cheap_model=True):
        return {"strategy": "balanced", "quality_score": 0.8}


class _RotatorStub:
    def call(self, messages):
        return {
            "content": "Запускаю инструмент.",
            "tool_calls": [{"name": "echo", "arguments": {"value": "ok"}}],
            "finish_reason": "stop",
            "usage": {"total_tokens": 5},
        }


class _RelationshipStub:
    def __init__(self):
        self.updated_outcomes = []

    def get_relationship(self, user_id):
        return {"score": 0}

    def get_relationship_trend(self, user_id):
        return {"score": 0, "positive_ratio": 0.5, "negative_streak": 0, "recent_outcomes": []}

    def update_relationship(self, **kwargs):
        self.updated_outcomes.append(kwargs["interaction_outcome"])


def _echo(value: str) -> str:
    return f"echo:{value}"


def test_response_processor_executes_tool_calls_and_merges_text(tmp_path):
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path))
    executor.register_tool("echo", _echo)
    processor = ResponseProcessor(tool_executor=executor)

    llm_response = {
        "content": "Сделала, как просил.",
        "tool_calls": [{"name": "echo", "arguments": {"value": "ok"}}],
    }

    result = processor.process(llm_response, user_id=1, chat_id=100, is_private=True)

    assert result.status == "success"
    assert result.tools_used == ["echo"]
    assert result.tool_results[0]["status"] == "success"
    assert "Сделала, как просил." in result.text
    assert "✅ Выполнено: echo" in result.text




def test_response_processor_denied_by_role_before_executor(tmp_path):
    calls = {"count": 0}

    def _owner_tool() -> str:
        calls["count"] += 1
        return "ok"

    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path))
    executor.register_tool("owner_tool", _owner_tool, allowed_roles=["owner", "moderator"])
    processor = ResponseProcessor(tool_executor=executor)

    llm_response = {"content": "Пробую.", "tool_calls": [{"name": "owner_tool", "arguments": {}}]}
    result = processor.process(llm_response, user_id=2, chat_id=10, is_private=False, user_role="user")

    assert result.status == "denied"
    assert result.tool_results[0]["status"] == "denied"
    assert calls["count"] == 0

def test_response_processor_returns_awaiting_confirmation_status(tmp_path):
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path))
    executor.register_tool("echo", _echo, requires_confirmation=True, risk_level="high")
    processor = ResponseProcessor(tool_executor=executor)

    llm_response = {
        "content": "Нужно подтверждение.",
        "tool_calls": [{"name": "echo", "arguments": {"value": "danger"}}],
    }

    result = processor.process(llm_response, user_id=1, chat_id=100, is_private=True)

    assert result.status == "awaiting_confirmation"
    assert result.outcome == "success"
    assert result.tool_results[0]["status"] == "awaiting_confirmation"
    assert "Подтверди" in result.text


def test_bot_post_processing_writes_tools_and_updates_relationship(tmp_path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path / "actions"))
    executor.register_tool("echo", _echo)
    relationship = _RelationshipStub()
    mood = MoodManager()

    bot = NotyBot(
        api_rotator=_RotatorStub(),
        message_handler=_MessageHandlerStub(),
        mood_manager=mood,
        tool_executor=executor,
        monologue=_MonologueStub(),
        db_manager=db,
        relationship_manager=relationship,
    )

    result = bot.handle_message({"chat_id": 1, "user_id": 1, "text": "сделай", "username": "u1"})

    assert result["status"] == "responded"
    assert result["tool_results"][0]["status"] == "success"
    assert relationship.updated_outcomes[-1] == "positive"

    conn = sqlite3.connect(str(tmp_path / "noty.db"))
    row = conn.execute("SELECT tools_used FROM interactions ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row[0] == "echo"


def test_bot_post_processing_skips_mood_and_relationship_on_tool_denied(tmp_path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path / "actions"))
    executor.register_tool("echo", _echo, allowed_roles=["moderator"])
    relationship = _RelationshipStub()
    mood = MoodManager()

    bot = NotyBot(
        api_rotator=_RotatorStub(),
        message_handler=_MessageHandlerStub(),
        mood_manager=mood,
        tool_executor=executor,
        monologue=_MonologueStub(),
        db_manager=db,
        relationship_manager=relationship,
    )

    result = bot.handle_message({"chat_id": 1, "user_id": 1, "text": "сделай", "username": "u1", "user_role": "user"})
    assert result["status"] == "denied"
    assert result["tool_results"][0]["status"] == "denied"
    assert relationship.updated_outcomes == []



def test_bot_builds_thoughts_before_prompt_and_passes_strategy_context(tmp_path):
    class _OrderMessageHandler(_MessageHandlerStub):
        def __init__(self):
            self.prompt_kwargs = None

        def prepare_prompt(self, **kwargs):
            self.prompt_kwargs = kwargs
            return "prompt"

    class _OrderMonologue:
        def __init__(self):
            self.generated = False

        def generate_thoughts(self, context, cheap_model=True):
            self.generated = True
            return {"strategy": "dry_brief", "quality_score": 0.77, "decision": "respond"}

    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path / "actions"))
    executor.register_tool("echo", _echo, description="echo-tool")
    mood = MoodManager()
    handler = _OrderMessageHandler()
    monologue = _OrderMonologue()

    bot = NotyBot(
        api_rotator=_RotatorStub(),
        message_handler=handler,
        mood_manager=mood,
        tool_executor=executor,
        monologue=monologue,
        db_manager=db,
        relationship_manager=_RelationshipStub(),
    )

    result = bot.handle_message({"chat_id": 1, "user_id": 1, "text": "сделай", "username": "u1"})

    assert result["status"] == "responded"
    assert monologue.generated is True
    assert handler.prompt_kwargs is not None
    assert handler.prompt_kwargs["thought_context"]["strategy"] == "dry_brief"
    env_context = handler.prompt_kwargs["environment_context"]
    assert env_context["agent_runtime"]["can_list_tools"] is True
    assert env_context["tools"][0]["name"] == "echo"


class _NeverRespondMessageHandler(_MessageHandlerStub):
    class _NeverDecision:
        should_respond = False
        reason = "randomized_drop"
        score = 0.1
        threshold = 0.5

    def decide_reaction(self, text: str):
        return self._NeverDecision()


def test_bot_force_respond_skips_interest_filter(tmp_path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    executor = SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path / "actions"))
    executor.register_tool("echo", _echo)
    mood = MoodManager()

    bot = NotyBot(
        api_rotator=_RotatorStub(),
        message_handler=_NeverRespondMessageHandler(),
        mood_manager=mood,
        tool_executor=executor,
        monologue=_MonologueStub(),
        db_manager=db,
        relationship_manager=_RelationshipStub(),
    )

    result = bot.handle_message(
        {"chat_id": 1, "user_id": 1, "text": "сделай", "username": "u1", "force_respond": True}
    )

    assert result["status"] == "responded"
    assert result["text"]
