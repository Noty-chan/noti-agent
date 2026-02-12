from noty.utils.metrics import MetricsCollector


def test_respond_rate_alert_below_target_has_reason_overfiltering():
    metrics = MetricsCollector()
    alert = metrics.respond_rate_alert(responded=10, total=100)

    assert alert is not None
    assert alert["reason"] == "перефильтрация"


def test_respond_rate_alert_above_target_has_reason_underfiltering():
    metrics = MetricsCollector()
    alert = metrics.respond_rate_alert(responded=40, total=100)

    assert alert is not None
    assert alert["reason"] == "недофильтрация"


def test_respond_rate_alert_none_within_corridor():
    metrics = MetricsCollector()
    alert = metrics.respond_rate_alert(responded=21, total=100)

    assert alert is None
