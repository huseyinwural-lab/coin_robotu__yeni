# ruff: noqa: E402
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.runtime_alert_thresholds import DEFAULTS, get_runtime_alert_thresholds


class TestGetRuntimeAlertThresholds:
    def test_returns_default_values(self):
        thresholds = get_runtime_alert_thresholds()
        assert thresholds["net_pnl_drop_pct"] == 5.0
        assert thresholds["failed_orders_window"] == 20
        assert thresholds["failed_orders_threshold"] == 4
        assert thresholds["queue_depth_threshold"] == 30
        assert thresholds["smoke_degraded_repeat_threshold"] == 2
        assert thresholds["execution_latency_ms_threshold"] == 1200

    def test_all_default_keys_present(self):
        thresholds = get_runtime_alert_thresholds()
        for key in DEFAULTS:
            assert key in thresholds

    def test_env_override_float_value(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_THRESHOLD_NET_PNL_DROP_PCT", "10.5")
        thresholds = get_runtime_alert_thresholds()
        assert thresholds["net_pnl_drop_pct"] == 10.5

    def test_env_override_int_value(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_THRESHOLD_QUEUE_DEPTH", "100")
        thresholds = get_runtime_alert_thresholds()
        assert thresholds["queue_depth_threshold"] == 100

    def test_env_override_empty_string_uses_default(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_THRESHOLD_QUEUE_DEPTH", "")
        thresholds = get_runtime_alert_thresholds()
        assert thresholds["queue_depth_threshold"] == DEFAULTS["queue_depth_threshold"]

    def test_return_type_consistency(self):
        thresholds = get_runtime_alert_thresholds()
        assert isinstance(thresholds["net_pnl_drop_pct"], float)
        assert isinstance(thresholds["failed_orders_window"], int)
        assert isinstance(thresholds["failed_orders_threshold"], int)
        assert isinstance(thresholds["queue_depth_threshold"], int)
