# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.readiness.go_live_validator import run_go_live_validator


def _base_context():
    return {
        "generated_at": "2026-03-27T00:00:00+00:00",
        "execution_mode": "LIVE",
        "env_mode": "LIVE",
        "config": type("Cfg", (), {"live_mode_enabled": True, "safe_mode_enabled": False, "kill_switch_enabled": False})(),
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
            "max_drawdown_pct": 20,
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
            "funding_count": 2,
            "funding_error": None,
        },
        "execution_tests": {
            "precision": {"status": "PASS"},
            "submit": {"status": "SUBMITTED", "mocked": False},
            "cancel": {"status": "CANCELLED", "mocked": False},
        },
        "exchange_metrics": {"websocket": {"age_sec": 5}, "rate_limit_status": "ok"},
        "latency_metrics": {"round_trip_ms": 120, "order_execution_ms": 180, "tick_to_trade_ms": 90},
        "pnl_snapshot": {"net_total_usd": -100, "as_of": "2099-01-01T00:00:00+00:00"},
        "dry_run_count": 2,
        "infra": {
            "db_ok": True,
            "redis_ok": True,
            "queue_sizes": {"runtime:execution:queue": 0},
            "worker_events": 2,
            "worker_lag_sec": 5,
            "strategy_engine_status": "unknown",
        },
    }


def test_go_live_validator_never_ready_without_strategy_heartbeat():
    context = _base_context()
    result = run_go_live_validator(context)
    assert result["readiness_state"] in {"UNKNOWN", "BLOCKED"}
    assert result["go_live_allowed"] is False
    assert result["execution_allowed"] is False
    assert "STRATEGY_ENGINE_UNKNOWN" in result["reason_codes"]
    assert isinstance(result.get("by_layer"), dict)
    assert isinstance(result.get("scores"), dict)


def test_go_live_validator_blocks_when_data_missing():
    context = _base_context()
    context["data_sources"]["balances"] = {"available": False, "fallback_used": False, "data_source": "cache"}
    result = run_go_live_validator(context)
    assert result["readiness_state"] in {"BLOCKED", "UNKNOWN", "WARNING"}
    assert result["go_live_allowed"] is False
    assert result["execution_allowed"] is False
    assert "BALANCE_DATA_MISSING" in result["reason_codes"]


def test_go_live_validator_blocks_when_mode_mismatch():
    context = _base_context()
    context["execution_mode"] = "TESTNET"
    result = run_go_live_validator(context)
    assert result["readiness_state"] in {"BLOCKED", "UNKNOWN"}
    assert result["execution_allowed"] is False
    assert "MODE_MISMATCH" in result["reason_codes"]
