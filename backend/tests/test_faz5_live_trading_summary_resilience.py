# ruff: noqa: E402
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import live_trading_dashboard_service as svc


def _boom(_msg):
    raise RuntimeError("component unavailable")


def test_live_trading_summary_returns_fallback_when_components_fail(monkeypatch):
    monkeypatch.setattr(svc, "build_scanner_health", lambda *args, **kwargs: _boom("scanner"))
    monkeypatch.setattr(svc, "build_execution_quality_summary", lambda *args, **kwargs: _boom("quality"))
    monkeypatch.setattr(svc, "build_risk_summary", lambda *args, **kwargs: _boom("risk"))
    monkeypatch.setattr(svc, "build_trading_performance_today", lambda *args, **kwargs: _boom("perf"))
    monkeypatch.setattr(svc, "build_learning_summary", lambda *args, **kwargs: _boom("learning"))
    monkeypatch.setattr(svc, "_live_config", lambda *args, **kwargs: _boom("config"))
    monkeypatch.setattr(svc, "_derive_thresholds", lambda *args, **kwargs: _boom("threshold"))
    monkeypatch.setattr(svc, "_critical_alerts", lambda *args, **kwargs: _boom("alerts"))

    result = svc.build_live_trading_summary(db=object(), cache=None, window="1h")

    assert result["system_health"]["execution_mode"] == "MOCK"
    assert result["system_health"]["kill_switch_active"] is False
    assert result["critical_alerts"]["status"] == "normal"
    assert isinstance(result.get("component_errors"), list)
    assert len(result["component_errors"]) >= 5


def test_live_trading_summary_handles_non_dict_component_payload(monkeypatch):
    monkeypatch.setattr(svc, "build_scanner_health", lambda *args, **kwargs: [])
    monkeypatch.setattr(svc, "build_execution_quality_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(svc, "build_risk_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(svc, "build_trading_performance_today", lambda *args, **kwargs: {})
    monkeypatch.setattr(svc, "build_learning_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(svc, "_live_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(svc, "_derive_thresholds", lambda *args, **kwargs: {})
    monkeypatch.setattr(svc, "_critical_alerts", lambda *args, **kwargs: {"status": "normal", "items": []})

    result = svc.build_live_trading_summary(db=object(), cache=None, window="1h")
    assert result["system_health"]["fallback_active"] in {False, True}
    assert any(item.get("component") == "scanner_health" for item in (result.get("component_errors") or []))
