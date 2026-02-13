from noty.core.response_processor import ResponseProcessor


def test_response_postcheck_respects_taboo_and_depth():
    rp = ResponseProcessor()
    result = rp.process(
        {"content": "Ну конечно, давай обсудим политику. Это первый факт. Это второй факт. Это третий факт."},
        user_id=1,
        chat_id=1,
        is_private=False,
        persona_profile={
            "taboo_topics": ["политику"],
            "response_depth_preference": "short",
            "sarcasm_tolerance": 0.1,
            "confidence": 0.7,
        },
    )

    assert "Сменю тему" in result.text
    assert result.style_match_score <= 0.7
    assert result.persona_confidence == 0.7
