from noty.core.response_processor import ResponseProcessor


def test_low_confidence_profile_uses_conservative_postcheck():
    rp = ResponseProcessor()
    result = rp.process(
        {"content": "Ну конечно! Ага, супер идея!"},
        user_id=1,
        chat_id=1,
        is_private=False,
        persona_profile={
            "sarcasm_tolerance": 0.9,
            "response_depth_preference": "deep",
            "confidence": 0.1,
        },
    )

    assert "Ну конечно" not in result.text
    assert result.persona_confidence == 0.1
