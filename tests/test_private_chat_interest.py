from noty.core.bot import NotyBot
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
            "content": "Ответ",
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"total_tokens": 5},
        }


class _RelationshipStub:
    def __init__(self, score: int):
        self.score = score

    def get_relationship(self, user_id):
        return {"relationship_score": self.score}

    def get_relationship_trend(self, user_id):
        return {"score": self.score, "positive_ratio": 0.2, "negative_streak": 3, "recent_outcomes": ["negative"]}

    def update_relationship(self, **kwargs):
        return None


def test_private_chat_can_be_ignored_for_uninteresting_user(tmp_path):
    bot = NotyBot(
        api_rotator=_RotatorStub(),
        message_handler=_MessageHandlerStub(),
        mood_manager=MoodManager(),
        tool_executor=SafeToolExecutor(owner_id=1, actions_log_dir=str(tmp_path / "actions")),
        monologue=_MonologueStub(),
        relationship_manager=_RelationshipStub(score=-5),
    )

    result = bot.handle_message({"chat_id": 1, "user_id": 42, "text": "привет", "is_private": True})

    assert result["status"] == "ignored"
    assert result["reason"] == "private_chat_uninteresting"
