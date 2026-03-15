from types import SimpleNamespace

from routers import admin_risk_router, admin_universe_router, user_scanner_router


class DummyDb:
    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None

    def all(self):
        return []


def _admin_user():
    return SimpleNamespace(id="admin-1", role=SimpleNamespace(value="SUPER_ADMIN"))


def _user():
    return SimpleNamespace(id="user-1")


def test_admin_risk_config_contract(monkeypatch):
    monkeypatch.setattr(admin_risk_router, "load_risk_config", lambda _cache: {"max_risk_per_trade_pct": 2.0, "config_version": 3})

    payload = admin_risk_router.get_risk_config(current_admin=_admin_user())
    assert "max_risk_per_trade_pct" in payload
    assert "config_version" in payload


def test_admin_risk_patch_contract(monkeypatch):
    monkeypatch.setattr(admin_risk_router, "load_risk_config", lambda _cache: {"max_risk_per_trade_pct": 2.0, "config_version": 3})
    monkeypatch.setattr(
        admin_risk_router,
        "patch_risk_config",
        lambda _cache, patch, changed_by: {
            "max_risk_per_trade_pct": patch.get("max_risk_per_trade_pct", 2.0),
            "config_version": 4,
            "changed_by": changed_by,
            "changed_at": "2026-03-15T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(admin_risk_router, "create_audit_log", lambda *args, **kwargs: None)

    payload = admin_risk_router.update_risk_config(
        payload={"max_risk_per_trade_pct": 1.5},
        current_admin=_admin_user(),
        db=DummyDb(),
    )
    assert payload["max_risk_per_trade_pct"] == 1.5
    assert payload["config_version"] == 4


def test_admin_risk_status_contract(monkeypatch):
    monkeypatch.setattr(
        admin_risk_router,
        "build_admin_risk_status",
        lambda db, cache: {
            "portfolio_exposure": 123.0,
            "symbol_exposure": [],
            "cluster_exposure": [],
            "daily_loss": {},
            "execution_quality_score": 72.0,
            "fallback_state": {},
            "queue_depth": 2,
            "stale_reject_count": 0,
            "spread_reject_count": 0,
            "cooldown_state": {},
            "kill_switch_state": {},
        },
    )
    payload = admin_risk_router.risk_status(current_admin=_admin_user(), db=DummyDb())
    assert "portfolio_exposure" in payload
    assert "execution_quality_score" in payload


def test_admin_runtime_summary_contract(monkeypatch):
    monkeypatch.setattr(admin_universe_router, "evaluate_top_volume_fallback", lambda cache: {"active": False, "reason_code": "none"})
    monkeypatch.setattr(
        admin_universe_router,
        "get_full_market_universe",
        lambda db, cache, scanner_mode, selected_symbols, top_n: {
            "combined_universe_size": 3,
            "combined_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "spot_symbols": ["BTCUSDT"],
            "futures_symbols": ["ETHUSDT", "SOLUSDT"],
        },
    )
    monkeypatch.setattr(
        admin_universe_router,
        "get_exchange_universe_snapshot",
        lambda *args, **kwargs: {"exchanges": ["binance", "bybit", "okx"]},
    )
    monkeypatch.setattr(
        admin_universe_router,
        "get_latest_global_runtime_snapshot",
        lambda cache: {
            "effective_mode": "all_market_symbols",
            "backpressure": {"active": False},
            "event_priority": {"distribution": {"high": 0, "medium": 0, "low": 0}},
            "tiered_scan": {"enabled": True},
            "explainability_summary": {},
        },
    )
    monkeypatch.setattr(admin_universe_router, "build_admin_risk_status", lambda db, cache: {"portfolio_exposure": 0.0})
    monkeypatch.setattr(admin_universe_router, "get_admin_observability_trends", lambda cache: {"execution_latency_trend": []})

    payload = admin_universe_router.admin_runtime_universe_summary(
        scanner_mode="all_market_symbols",
        top_n=50,
        current_admin=_admin_user(),
        db=DummyDb(),
    )
    assert "risk_overview" in payload
    assert "tiered_scan" in payload
    assert "observability_trends" in payload


def test_user_runtime_run_contract(monkeypatch):
    monkeypatch.setattr(
        user_scanner_router,
        "run_scanner_runtime",
        lambda *args, **kwargs: {
            "run_id": "r1",
            "decision_count": 1,
            "tiered_scan": {"enabled": True},
            "risk_engine": {"decision_distribution": {"ALLOW": 1}},
        },
    )

    payload = user_scanner_router.run_runtime_scan(
        symbol_selection_mode="all_market_symbols",
        max_results=120,
        selected_symbols="",
        current_user=_user(),
        db=DummyDb(),
    )
    assert "tiered_scan" in payload
    assert "risk_engine" in payload
