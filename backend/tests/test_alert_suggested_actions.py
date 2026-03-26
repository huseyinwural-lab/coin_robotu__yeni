from core.alerts.suggested_actions import get_suggested_action


def test_suggested_actions_for_top_runtime_alert_types():
    alert_types = [
        "runtime_pnl_drop",
        "runtime_daily_smoke_degraded",
        "runtime_queue_depth_high",
        "runtime_failed_orders_high",
        "runtime_daily_loss_limit",
    ]
    for alert_type in alert_types:
        payload = get_suggested_action(alert_type)
        assert payload.get("suggested_action")
        assert payload.get("runbook_hint")
