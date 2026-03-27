# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.readiness.go_live_validator import run_go_live_validator


class DummyConfig:
    live_mode_enabled = True
    safe_mode_enabled = False
    kill_switch_enabled = False


def _base_context():
    return {
        "generated_at": "2026-03-27T00:00:00+00:00",
        "execution_mode": "LIVE",
        "env_mode": "LIVE",
        "config": DummyConfig(),
        "kill_switch_active": False,
        "release_gate": {"status": "PASS", "reason_codes": []},
        "connection": {
            "exists": True,
            "connection_health": "online",
            "can_trade": True,
            "validation_success": True,
            "environment": "live",
            "source": "exchange_connection_snapshot",
        },
        "data_sources": {
            "balances": {
                "available": True,
                "fallback_used": False,
                "data_source": "cache",
                "payload": {
                    "available_balance": 10000,
                    "wallet_balance": 12000,
                    "timestamp": "2099-01-01T00:00:00+00:00",
                },
            },
            "positions": {"available": True, "fallback_used": False, "data_source": "cache", "payload": []},
            "open_orders": {"available": True, "fallback_used": False, "data_source": "cache", "payload": []},
            "market_data": {
                "available": True,
                "fallback_used": False,
                "data_source": "cache",
                "payload": {"bid": 50000, "ask": 50010},
            },
        },
        "risk_config": {
            "config_version": "p1",
            "max_leverage": 5,
            "max_total_exposure_pct": 300,
            "max_margin_usage_pct": 75,
            "stale_data_threshold_ms": 120000,
        },
        "risk_orchestrator_enabled": True,
        "trading_state": {
            "engine_positions": [],
            "engine_orders": [],
            "position_count": 0,
            "order_count": 0,
            "total_exposure": 0,
            "partial_fill_count": 1,
            "funding_available": True,
            "funding_count": 3,
            "funding_error": None,
        },
        "execution_tests": {
            "precision": {"status": "PASS"},
            "submit": {"status": "SUBMITTED", "mocked": False},
            "cancel": {"status": "CANCELLED", "mocked": False},
        },
        "exchange_metrics": {"websocket": {"age_sec": 5}, "rate_limit_status": "ok"},
        "infra": {
            "db_ok": True,
            "redis_ok": True,
            "queue_sizes": {"runtime:execution:queue": 0},
            "worker_events": 3,
            "worker_lag_sec": 5,
            "strategy_engine_status": "ok",
        },
    }


def test_validator_output_has_layers():
    result = run_go_live_validator(_base_context())
    assert "scores" in result
    assert "by_layer" in result
    assert "blocking_failures" in result
    assert "warnings" in result
    assert "unknowns" in result
    for key in ["core", "trading_state", "exchange", "execution", "risk", "infra"]:
        assert key in result["scores"]
        assert key in result["by_layer"]


def test_validator_blocks_when_execution_mocked():
    context = _base_context()
    context["execution_tests"]["submit"] = {"status": "MOCKED", "mocked": True}
    result = run_go_live_validator(context)
    assert result["readiness_state"] != "READY"
    reasons = [item["reason_code"] for item in result.get("blocking_failures", [])]
    assert "EXECUTION_TEST_MOCKED" in reasons


def test_validator_ready_with_funding_unknown():
    context = _base_context()
    context["trading_state"]["funding_available"] = False
    context["trading_state"]["funding_count"] = 0
    result = run_go_live_validator(context)
    assert result["readiness_state"] == "READY"
