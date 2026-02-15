from types import SimpleNamespace

from noty.core.api_rotator import APIRotator


def _response(content: str = "ok"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=[]), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def test_api_rotator_switches_on_error_and_recovers():
    rotator = APIRotator(api_keys=["k1", "k2"])
    calls = []

    def fake_call(api_key: str, call_params):
        calls.append(api_key)
        if api_key == "k1" and len(calls) == 1:
            raise RuntimeError("temporary backend error")
        return _response(content=api_key)

    rotator._call_backend = fake_call  # type: ignore[method-assign]

    out1 = rotator.call(messages=[{"role": "user", "content": "hi"}])
    assert out1["content"] == "k2"
    assert calls[:2] == ["k1", "k2"]

    rotator.degraded_keys["k1"] = 0
    out2 = rotator.call(messages=[{"role": "user", "content": "again"}])
    assert out2["content"] in {"k1", "k2"}
    assert rotator.get_stats()["key_stats"]["k1"]["errors"] >= 1


def test_api_rotator_builds_openrouter_identification_headers():
    rotator = APIRotator(api_keys=["k1"], app_referer="https://noty.local", app_title="Noty Dev")

    assert rotator._build_default_headers() == {
        "HTTP-Referer": "https://noty.local",
        "X-Title": "Noty Dev",
    }


def test_api_rotator_skips_referer_when_not_provided():
    rotator = APIRotator(api_keys=["k1"], app_referer=None, app_title="Noty")

    assert rotator._build_default_headers() == {"X-Title": "Noty"}
