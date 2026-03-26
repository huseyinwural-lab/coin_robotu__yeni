from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services import admin_commercial_service as service


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def test_pnl_analytics_strategy_symbol_and_drawdown_deterministic():
    now = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
    trades = [
        _ns(raw_payload={"strategy_code": "trend"}, symbol="BTCUSDT", realized_pnl_usd=40.0),
        _ns(raw_payload={"strategy_code": "trend"}, symbol="BTCUSDT", realized_pnl_usd=-10.0),
        _ns(raw_payload={"strategy_code": "meanrev"}, symbol="ETHUSDT", realized_pnl_usd=20.0),
    ]
    pnl_records = [
        _ns(as_of=now - timedelta(days=2), realized_net_usd=30.0, unrealized_net_usd=5.0),
        _ns(as_of=now - timedelta(days=1), realized_net_usd=-10.0, unrealized_net_usd=2.0),
        _ns(as_of=now, realized_net_usd=25.0, unrealized_net_usd=3.0),
    ]

    payload = service._build_pnl_analytics_block(trades, pnl_records)
    assert payload["strategy_pnl_breakdown"][0]["key"] == "trend"
    assert payload["symbol_pnl_breakdown"][0]["key"] == "BTCUSDT"
    assert len(payload["daily_pnl_trend"]) == 3
    assert payload["max_drawdown_usd"] >= 0
    assert payload["max_drawdown_pct"] >= 0


def test_financial_accuracy_reconciliation_fields_mapped():
    reconciliation_logs = [
        _ns(
            created_at=datetime(2026, 3, 26, 9, 0, 0, tzinfo=timezone.utc),
            exchange_trade_count=120,
            internal_trade_count=118,
            missing_trade_count=2,
            duplicate_trade_count=1,
            balance_drift_usd=4.5,
            position_drift_usd=2.1,
            pnl_drift_usd=1.8,
            drift_within_tolerance=False,
            status="warning",
        )
    ]
    payload = service._build_financial_accuracy_block([], [], reconciliation_logs)
    assert payload["exchange_trade_count"] == 120
    assert payload["missing_trade_count"] == 2
    assert payload["duplicate_trade_count"] == 1
    assert payload["drift_within_tolerance"] is False
    assert payload["reconciliation_status"] == "warning"


def test_revenue_model_includes_plan_and_user_breakdown():
    rows = [
        _ns(user_id="u1", component_type="subscription_fee", revenue_amount_usd=10.0, source_amount_usd=10.0, share_rate=1.0, symbol="BTCUSDT"),
        _ns(user_id="u1", component_type="fee", revenue_amount_usd=5.0, source_amount_usd=5.0, share_rate=1.0, symbol="BTCUSDT"),
        _ns(user_id="u2", component_type="profit_split", revenue_amount_usd=8.0, source_amount_usd=16.0, share_rate=0.5, symbol="ETHUSDT"),
    ]
    profiles = [
        _ns(user_id="u1", environment="live", tier_code="pro", subscription_status="active", billing_cycle="monthly"),
        _ns(user_id="u2", environment="live", tier_code="enterprise", subscription_status="active", billing_cycle="monthly"),
    ]
    payload = service._build_revenue_model_block(rows, subscription_profiles=profiles, user_email_map={"u1": "u1@test", "u2": "u2@test"})
    assert payload["subscription_revenue_usd"] == 10.0
    assert payload["platform_fee_revenue_usd"] == 5.0
    assert payload["profit_split_revenue_usd"] == 8.0
    assert len(payload["revenue_by_user"]) == 2
    assert len(payload["revenue_by_plan"]) >= 1


def test_user_economics_arpu_arppu_and_churn_rate():
    users = [
        _ns(user_id="u1", user_email="a@test", ltv_usd=100, revenue_contribution_usd=40, realized_pnl_usd=30, inactive_days=5, churned=False, details={}, cohort_month="2026-03", first_activity_at=None, last_activity_at=None),
        _ns(user_id="u2", user_email="b@test", ltv_usd=80, revenue_contribution_usd=0, realized_pnl_usd=-5, inactive_days=35, churned=True, details={}, cohort_month="2026-03", first_activity_at=None, last_activity_at=None),
    ]
    payload = service._build_user_economics_block(users)
    assert payload["arpu_usd"] == 20.0
    assert payload["arppu_usd"] == 40.0
    assert payload["churn_rate_pct"] == 50.0
    assert payload["inactive_user_count"] == 1


def test_usage_analytics_telemetry_metrics_from_events():
    now = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
    trades = [_ns(user_id="u1", market_type="spot", exchange="binance", symbol="BTCUSDT", quote_qty=20, executed_qty=0, executed_price=0, trade_time=now)]
    events = [
        _ns(success=True, latency_ms=100, endpoint="/api/a", event_type="api_call", created_at=now - timedelta(minutes=2)),
        _ns(success=False, latency_ms=300, endpoint="/api/a", event_type="error", created_at=now - timedelta(minutes=1)),
    ]
    payload = service._build_usage_analytics_block(trades, events)
    assert payload["request_count"] == 2
    assert payload["success_count"] == 1
    assert payload["failure_count"] == 1
    assert payload["error_rate_pct"] == 50.0
    assert payload["p95_latency_ms"] >= 100


def test_data_quality_extended_fields_present():
    now = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
    logs = [
        _ns(
            created_at=now - timedelta(minutes=10),
            status="completed",
            duplicate_trade_count=2,
            missing_symbols=["DOGEUSDT"],
        )
    ]
    payload = service._build_data_quality_block(
        now=now,
        total_trade_count=10,
        total_pnl_records=4,
        latest_trade_at=now - timedelta(minutes=8),
        latest_pnl_at=now - timedelta(minutes=7),
        latest_reconciliation_at=now - timedelta(minutes=10),
        missing_data_alert=False,
        reconciliation_logs=logs,
    )
    assert payload["duplicate_trade_count"] == 2
    assert payload["duplicate_trade_status"] == "warning"
    assert payload["cross_source_validation_state"] in {"ok", "warning", "degraded"}
    assert payload["reconciliation_coverage_pct"] > 0


def test_operational_controls_reason_note_required():
    actor = _ns(id="admin", email="admin@test", role="super_admin")
    with pytest.raises(ValueError, match="reason_note_required"):
        service.update_user_operational_controls(
            None,
            actor_user=actor,
            target_user_id="u1",
            trading_enabled=True,
            capital_frozen=False,
            withdraw_locked=False,
            emergency_stop=False,
            reason_note="",
        )


def test_operational_controls_non_admin_rejected():
    actor = _ns(id="u1", email="u1@test", role="user")
    with pytest.raises(ValueError, match="admin_required"):
        service.update_user_operational_controls(
            None,
            actor_user=actor,
            target_user_id="u2",
            trading_enabled=True,
            capital_frozen=False,
            withdraw_locked=False,
            emergency_stop=False,
            reason_note="valid reason",
        )


def test_export_ops_summary_health_and_recent_jobs():
    manifests = [
        _ns(status="queued"),
        _ns(status="delivered"),
    ]
    schedules = [
        _ns(id="s1", export_type="pnl", schedule_period="daily", is_active=True, output_format="csv", last_status="ok", last_run_at=None, updated_at=datetime.now(timezone.utc)),
        _ns(id="s2", export_type="revenue", schedule_period="weekly", is_active=True, output_format="csv", last_status="failed", last_run_at=None, updated_at=datetime.now(timezone.utc)),
    ]
    payload = service._build_export_ops_block(manifests, schedules)
    assert payload["pending_exports"] == 1
    assert payload["delivered_exports"] == 1
    assert payload["scheduler_health"] == "degraded"
