from noty.utils.metrics import MetricsCollector


def test_metrics_snapshot_contains_stage_platform_percentiles_and_token_cost() -> None:
    metrics = MetricsCollector()

    with metrics.time_block("message_total_seconds", stage="e2e", platform="vk"):
        pass
    with metrics.time_block("message_total_seconds", stage="e2e", platform="vk"):
        pass
    with metrics.time_block("llm_call_seconds", stage="llm_call", platform="vk"):
        pass

    metrics.record_token_cost(0.0123, stage="e2e", platform="vk")
    metrics.record_token_cost("0.0077", stage="llm_call", platform="vk")
    metrics.record_token_cost("bad-value", stage="llm_call", platform="vk")

    snapshot = metrics.snapshot()
    stage_series = snapshot["series"]["stage_platform"]

    assert "e2e" in stage_series
    assert "llm_call" in stage_series

    e2e_vk = stage_series["e2e"]["vk"]
    assert e2e_vk["count"] == 2
    assert "p50_seconds" in e2e_vk
    assert "p95_seconds" in e2e_vk
    assert e2e_vk["token_cost_usd"] == 0.0123

    llm_vk = stage_series["llm_call"]["vk"]
    assert llm_vk["count"] == 1
    assert llm_vk["token_cost_usd"] == 0.0077
