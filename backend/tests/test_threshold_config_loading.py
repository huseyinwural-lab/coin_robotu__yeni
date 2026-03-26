import os

from core.runtime_alert_thresholds import get_runtime_alert_thresholds


def test_threshold_env_override_precedence():
    os.environ["RUNTIME_THRESHOLD_NET_PNL_DROP_PCT"] = "7"
    os.environ["RUNTIME_THRESHOLD_QUEUE_DEPTH"] = "55"

    cfg = get_runtime_alert_thresholds()
    assert float(cfg["net_pnl_drop_pct"]) == 7.0
    assert int(cfg["queue_depth_threshold"]) == 55
