from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services.admin_commercial_service import (
    _build_data_quality_block,
    _build_financial_accuracy_block,
    _build_revenue_model_block,
    _build_risk_summary_block,
    _build_usage_analytics_block,
)


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def test_financial_accuracy_gross_net_and_realized_unrealized_totals():
    pnl_records = [
        _ns(
            realized_gross_usd=120.0,
            unrealized_gross_usd=15.0,
            realized_net_usd=110.0,
            unrealized_net_usd=10.0,
            trading_fee_usd=6.0,
            commission_usd=5.0,
            funding_usd=1.0,
        ),
        _ns(
            realized_gross_usd=30.0,
            unrealized_gross_usd=5.0,
            realized_net_usd=25.0,
            unrealized_net_usd=3.0,
            trading_fee_usd=2.0,
            commission_usd=1.5,
            funding_usd=0.5,
        ),
    ]

    payload = _build_financial_accuracy_block([], pnl_records)

    assert payload["realized_gross_usd"] == 150.0
    assert payload["unrealized_gross_usd"] == 20.0
    assert payload["gross_total_usd"] == 170.0
    assert payload["realized_net_usd"] == 135.0
    assert payload["unrealized_net_usd"] == 13.0
    assert payload["net_total_usd"] == 148.0
    assert payload["net_vs_gross_delta_usd"] == 22.0


def test_financial_accuracy_fee_funding_commission_totals_from_trade_fallback():
    trade_rows = [
        _ns(realized_pnl_usd=60.0, commission_usd=2.0, funding_fee_usd=0.5),
        _ns(realized_pnl_usd=25.0, commission_usd=1.0, funding_fee_usd=1.0),
    ]

    payload = _build_financial_accuracy_block(trade_rows, [])

    assert payload["trading_fee_total_usd"] == 3.0
    assert payload["commission_total_usd"] == 3.0
    assert payload["funding_total_usd"] == 1.5
    assert payload["realized_gross_usd"] == 85.0
    assert payload["realized_net_usd"] == 80.5


def test_revenue_model_aggregate_consistency_and_determinism():
    revenue_rows = [
        _ns(component_type="fee", revenue_amount_usd=10.0, source_amount_usd=10.0, share_rate=1.0, symbol="BTCUSDT"),
        _ns(component_type="pnl_share", revenue_amount_usd=4.0, source_amount_usd=20.0, share_rate=0.2, symbol="BTCUSDT"),
        _ns(
            component_type="subscription_fee",
            revenue_amount_usd=6.0,
            source_amount_usd=6.0,
            share_rate=1.0,
            symbol="ETHUSDT",
        ),
    ]

    payload1 = _build_revenue_model_block(revenue_rows)
    payload2 = _build_revenue_model_block(revenue_rows)

    sum_of_components = sum(item["revenue_usd"] for item in payload1["component_breakdown"])
    assert payload1["total_revenue_usd"] == sum_of_components
    assert payload1 == payload2


def test_risk_summary_empty_data_scenario_returns_safe_defaults():
    payload = _build_risk_summary_block(
        [],
        [],
        open_position_count=0,
        risk_policy=None,
        live_config=None,
    )

    assert payload["open_position_count"] == 0
    assert payload["risk_exposure_usd"] == 0.0
    assert payload["high_drift_reconciliation_count"] == 0
    assert payload["top_exposure_symbols"] == []
    assert payload["trading_enabled"] is False
    assert payload["kill_switch_enabled"] is False


def test_data_quality_empty_data_scenario():
    now = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
    payload = _build_data_quality_block(
        now=now,
        total_trade_count=0,
        total_pnl_records=0,
        latest_trade_at=None,
        latest_pnl_at=None,
        latest_reconciliation_at=None,
        missing_data_alert=False,
        stale_threshold_seconds=3600,
    )

    assert payload["status"] == "empty"
    assert payload["empty_data"] is True
    assert payload["stale_sources"] == []


def test_data_quality_stale_data_scenario():
    now = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
    payload = _build_data_quality_block(
        now=now,
        total_trade_count=12,
        total_pnl_records=4,
        latest_trade_at=now - timedelta(hours=9),
        latest_pnl_at=now - timedelta(hours=8),
        latest_reconciliation_at=now - timedelta(minutes=20),
        missing_data_alert=False,
        stale_threshold_seconds=3600,
    )

    assert payload["status"] == "stale"
    assert "trades" in payload["stale_sources"]
    assert "pnl_records" in payload["stale_sources"]
    assert payload["empty_data"] is False


def test_financial_accuracy_realized_only_scenario():
    pnl_records = [
        _ns(
            realized_gross_usd=40.0,
            unrealized_gross_usd=0.0,
            realized_net_usd=37.5,
            unrealized_net_usd=0.0,
            trading_fee_usd=1.5,
            commission_usd=1.2,
            funding_usd=0.3,
        )
    ]

    payload = _build_financial_accuracy_block([], pnl_records)
    assert payload["realized_gross_usd"] == 40.0
    assert payload["unrealized_gross_usd"] == 0.0
    assert payload["gross_total_usd"] == 40.0
    assert payload["net_total_usd"] == 37.5


def test_financial_accuracy_unrealized_only_scenario():
    pnl_records = [
        _ns(
            realized_gross_usd=0.0,
            unrealized_gross_usd=18.0,
            realized_net_usd=0.0,
            unrealized_net_usd=16.5,
            trading_fee_usd=0.8,
            commission_usd=0.5,
            funding_usd=0.3,
        )
    ]

    payload = _build_financial_accuracy_block([], pnl_records)
    assert payload["realized_gross_usd"] == 0.0
    assert payload["unrealized_gross_usd"] == 18.0
    assert payload["gross_total_usd"] == 18.0
    assert payload["unrealized_net_usd"] == 16.5
    assert payload["net_total_usd"] == 16.5


def test_financial_accuracy_gross_net_difference_matches_fee_components():
    pnl_records = [
        _ns(
            realized_gross_usd=100.0,
            unrealized_gross_usd=20.0,
            realized_net_usd=92.0,
            unrealized_net_usd=17.0,
            trading_fee_usd=6.0,
            commission_usd=5.0,
            funding_usd=1.0,
        )
    ]

    payload = _build_financial_accuracy_block([], pnl_records)
    assert payload["gross_total_usd"] == 120.0
    assert payload["net_total_usd"] == 109.0
    assert payload["net_vs_gross_delta_usd"] == 11.0


def test_financial_accuracy_fee_funding_commission_from_pnl_records():
    pnl_records = [
        _ns(
            realized_gross_usd=0.0,
            unrealized_gross_usd=0.0,
            realized_net_usd=0.0,
            unrealized_net_usd=0.0,
            trading_fee_usd=2.5,
            commission_usd=1.75,
            funding_usd=0.75,
        ),
        _ns(
            realized_gross_usd=0.0,
            unrealized_gross_usd=0.0,
            realized_net_usd=0.0,
            unrealized_net_usd=0.0,
            trading_fee_usd=1.5,
            commission_usd=1.0,
            funding_usd=0.5,
        ),
    ]

    payload = _build_financial_accuracy_block([], pnl_records)
    assert payload["trading_fee_total_usd"] == 4.0
    assert payload["commission_total_usd"] == 2.75
    assert payload["funding_total_usd"] == 1.25


def test_usage_analytics_duplicate_trade_effect_is_consistent():
    base_time = datetime(2026, 3, 26, 9, 0, 0, tzinfo=timezone.utc)
    trade_a = _ns(
        trade_time=base_time,
        market_type="spot",
        exchange="binance",
        symbol="BTCUSDT",
        quote_qty=100.0,
        executed_qty=0.0,
        executed_price=0.0,
        user_id="u1",
    )
    trade_b = _ns(
        trade_time=base_time,
        market_type="spot",
        exchange="binance",
        symbol="BTCUSDT",
        quote_qty=100.0,
        executed_qty=0.0,
        executed_price=0.0,
        user_id="u1",
    )

    payload = _build_usage_analytics_block([trade_a, trade_b])
    assert payload["total_trades"] == 2
    assert payload["total_notional_usd"] == 200.0
    assert payload["top_symbols"][0]["trade_count"] == 2


def test_risk_summary_reconciliation_drift_scenario_counted():
    trades = [
        _ns(symbol="BTCUSDT", quote_qty=200.0, executed_qty=0.0, executed_price=0.0),
        _ns(symbol="ETHUSDT", quote_qty=150.0, executed_qty=0.0, executed_price=0.0),
    ]
    logs = [
        _ns(drift_within_tolerance=True),
        _ns(drift_within_tolerance=False),
        _ns(drift_within_tolerance=False),
    ]

    payload = _build_risk_summary_block(
        trades,
        logs,
        open_position_count=3,
        risk_policy=_ns(daily_loss_limit_pct=4.2),
        live_config=_ns(trading_enabled=True, kill_switch_enabled=False),
    )

    assert payload["open_position_count"] == 3
    assert payload["high_drift_reconciliation_count"] == 2
    assert payload["risk_exposure_usd"] == 350.0
    assert payload["latest_daily_loss_limit_pct"] == 4.2
    assert payload["trading_enabled"] is True


def test_risk_summary_full_scenario_with_top_exposure_symbols():
    trades = [
        _ns(symbol="BTCUSDT", quote_qty=500.0, executed_qty=0.0, executed_price=0.0),
        _ns(symbol="BTCUSDT", quote_qty=200.0, executed_qty=0.0, executed_price=0.0),
        _ns(symbol="ETHUSDT", quote_qty=250.0, executed_qty=0.0, executed_price=0.0),
    ]

    payload = _build_risk_summary_block(
        trades,
        [],
        open_position_count=2,
        risk_policy=_ns(daily_loss_limit_pct=5.0),
        live_config=_ns(trading_enabled=True, kill_switch_enabled=True),
    )

    assert payload["top_exposure_symbols"][0]["symbol"] == "BTCUSDT"
    assert payload["top_exposure_symbols"][0]["exposure_usd"] == 700.0
    assert payload["top_exposure_symbols"][1]["symbol"] == "ETHUSDT"
    assert payload["kill_switch_enabled"] is True


def test_revenue_component_aggregation_with_multiple_component_types():
    rows = [
        _ns(component_type="platform_fee", revenue_amount_usd=3.0, source_amount_usd=3.0, share_rate=1.0, symbol="BTCUSDT"),
        _ns(component_type="subscription_fee", revenue_amount_usd=7.0, source_amount_usd=7.0, share_rate=1.0, symbol="ETHUSDT"),
        _ns(component_type="profit_split", revenue_amount_usd=4.0, source_amount_usd=20.0, share_rate=0.2, symbol="BTCUSDT"),
    ]

    payload = _build_revenue_model_block(rows)
    by_component = {item["component_type"]: item for item in payload["component_breakdown"]}

    assert by_component["platform_fee"]["revenue_usd"] == 3.0
    assert by_component["subscription_fee"]["revenue_usd"] == 7.0
    assert by_component["profit_split"]["revenue_usd"] == 4.0
    assert payload["total_revenue_usd"] == 14.0
