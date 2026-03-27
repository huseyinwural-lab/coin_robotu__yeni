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
            "balances": {"available": True, "fallback_used": False, "data_source": "cache"},
            "positions": {"available": True, "fallback_used": False, "data_source": "cache"},
            "open_orders": {"available": True, "fallback_used": False, "data_source": "cache"},
            "market_data": {"available": True, "fallback_used": False, "data_source": "cache"},
        },
    }


def test_go_live_validator_ready_when_all_blocking_pass():
    context = _base_context()
    result = run_go_live_validator(context)
    assert result["readiness_state"] == "READY"
    assert result["go_live_allowed"] is True
    assert result["execution_allowed"] is True


def test_go_live_validator_blocks_when_data_missing():
    context = _base_context()
    context["data_sources"]["balances"] = {"available": False, "fallback_used": False, "data_source": "cache"}
    result = run_go_live_validator(context)
    assert result["readiness_state"] in {"BLOCKED", "UNKNOWN"}
    assert result["go_live_allowed"] is False
    assert "BALANCE_DATA_MISSING" in result["reason_codes"]


def test_go_live_validator_blocks_when_mode_mismatch():
    context = _base_context()
    context["execution_mode"] = "TESTNET"
    result = run_go_live_validator(context)
    assert result["readiness_state"] == "BLOCKED"
    assert "MODE_MISMATCH" in result["reason_codes"]
