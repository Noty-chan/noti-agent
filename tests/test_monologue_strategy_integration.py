from pathlib import Path

from noty.core.context_manager import DynamicContextBuilder
from noty.core.response_processor import ResponseProcessor
from noty.thought.monologue import InternalMonologue, ThoughtLogger


class DummyAPI:
    def __init__(self, content: str):
        self.content = content

    def call(self, **_kwargs):
        return {"content": self.content}


class DummyEncoder:
    @staticmethod
    def encode(_text: str):
        return [1.0, 0.0]


class DummyEmbedder:
    encoder = DummyEncoder()


class DummyDB:
    def get_recent_messages(self, _chat_id: int, limit: int = 5):
        return [
            {"user_id": 1, "text": "Давай снова спорить о политике", "timestamp": "2026-01-01T10:00:00"},
            {"user_id": "noty", "text": "Окей, сменим тему", "timestamp": "2026-01-01T10:00:02"},
        ][:limit]

    def get_messages_range(self, _chat_id: int, days_ago: int = 7, exclude_recent: int = 5):
        return []

    def get_important_messages(self, _chat_id: int, days_ago: int = 7):
        return []


class DummyToolExecutor:
    tools_registry = {
        "safe_tool": {"risk_level": "low"},
        "danger_tool": {"risk_level": "critical"},
    }


def test_quality_gate_falls_back_to_conservative_and_logs_strategy(tmp_path: Path):
    logger = ThoughtLogger(str(tmp_path / "thoughts"))
    monologue = InternalMonologue(api_rotator=DummyAPI(content="кратко"), thought_logger=logger)

    thought_entry = monologue.generate_thoughts(
        {
            "chat_id": 1,
            "chat_name": "test",
            "user_id": 42,
            "username": "alice",
            "message": "привет",
            "mood": "neutral",
            "interaction_id": "itx-123",
        }
    )

    assert thought_entry["quality_score"] < InternalMonologue.QUALITY_GATE_THRESHOLD
    assert thought_entry["strategy"] == "conservative"
    assert thought_entry["interaction_id"] == "itx-123"
    assert thought_entry["applied_strategy"]["require_confirmation_escalation"] is True

    entries = logger.read_today_thoughts()
    assert entries[-1]["interaction_id"] == "itx-123"
    assert entries[-1]["strategy"] == "conservative"


def test_response_processor_applies_strategy_to_tools_and_text():
    processor = ResponseProcessor()
    strategy = {
        "name": "conservative",
        "sarcasm_level": 0.1,
        "response_style": "formal_brief",
        "max_sentences": 1,
        "allowed_tool_risk": ["low"],
        "require_confirmation_escalation": True,
    }

    processed = processor.process(
        llm_response={
            "content": "Первое предложение. Второе предложение.",
            "tool_calls": [{"name": "safe_tool"}, {"name": "danger_tool"}],
        },
        strategy=strategy,
        tools_registry=DummyToolExecutor.tools_registry,
    )

    assert processed["text"] == "Первое предложение."
    assert processed["selected_tools"] == [{"name": "safe_tool"}]
    assert processed["confirmation_escalation"] is True


def test_dynamic_context_builder_adds_and_applies_strategy_hints():
    builder = DynamicContextBuilder(db_manager=DummyDB(), embedding_filter=DummyEmbedder(), max_tokens=600)

    context = builder.build_context(
        chat_id=1,
        current_message="давай без конфликтов",
        user_id=42,
        strategy_hints={"avoid_topics": ["политике"]},
    )

    assert "избегать тем политике" in context["summary"]
    assert context["metadata"]["strategy_hints"]["avoid_topics"] == ["политике"]
    assert all("политике" not in m["content"].lower() for m in context["messages"])


def test_prompt_builder_exposes_environment_and_thought_guidance(tmp_path: Path):
    from noty.prompts.prompt_builder import ModularPromptBuilder

    builder = ModularPromptBuilder(str(tmp_path / "prompts"))
    prompt = builder.build_full_prompt(
        context={"messages": [{"role": "user", "content": "привет"}], "summary": ""},
        thought_context={"strategy": "dry_brief", "quality_score": 0.91, "decision": "respond"},
        environment_context={
            "platform": "vk",
            "agent_runtime": {"can_call_tools": True, "can_list_tools": True},
            "tools": [
                {
                    "name": "notebook_list",
                    "description": "Показать заметки",
                    "risk_level": "low",
                    "requires_confirmation": False,
                    "requires_owner": False,
                    "requires_private": False,
                    "allowed_roles": ["user"],
                }
            ],
        },
    )

    assert "СРЕДА И ВОЗМОЖНОСТИ АГЕНТА" in prompt
    assert "can_list_tools: True" in prompt
    assert "notebook_list" in prompt
    assert "THOUGHT GUIDANCE (internal)" in prompt
    assert "strategy_from_thoughts: dry_brief" in prompt
