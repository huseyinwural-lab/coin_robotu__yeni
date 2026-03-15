from services import risk_engine_service


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def _common(monkeypatch):
    monkeypatch.setattr(
        risk_engine_service,
        "build_exposure_snapshot",
        lambda db, user_id, symbol, proposed_notional_usdt: {
            "wallet_usdt_balance": 10_000.0,
            "open_exposure_usdt": 200.0,
            "pending_exposure_usdt": 50.0,
            "symbol_exposure_usdt": 80.0,
            "cluster_exposure_usdt": 100.0,
            "cluster_id": "majors",
            "projected_total_exposure_usdt": 400.0,
            "projected_symbol_exposure_usdt": 180.0,
            "projected_cluster_exposure_usdt": 200.0,
        },
    )
    monkeypatch.setattr(risk_engine_service, "kill_switch_state", lambda _cache: {"active": False, "reasons": []})


def test_daily_loss_triggers_block_and_global_cooldown(monkeypatch):
    cache = FakeCache()
    _common(monkeypatch)
    monkeypatch.setattr(
        risk_engine_service,
        "load_risk_config",
        lambda _cache: {
            **risk_engine_service.DEFAULT_RISK_CONFIG,
            "max_daily_loss_pct": 3.0,
            "global_cooldown_minutes": 15,
            "max_consecutive_losses": 10,
        },
    )
    monkeypatch.setattr(risk_engine_service, "_daily_loss_stats", lambda db, user_id, wallet_usdt_balance: {"daily_loss_pct": 4.2})
    monkeypatch.setattr(risk_engine_service, "_consecutive_losses", lambda db, user_id: 0)

    result = risk_engine_service.evaluate_risk_decision(
        db=object(),
        cache=cache,
        user_id="u1",
        symbol="BTCUSDT",
        strategy_decision="LONG",
        market_type="spot",
        proposed_notional_usdt=100.0,
    )

    assert result["risk_decision"] == "BLOCK"
    assert "max_daily_loss_pct_exceeded" in result["reason_codes"]
    assert result["cooldown_state"]["global"]["active"] is True


def test_consecutive_loss_triggers_strategy_cooldown_pass(monkeypatch):
    cache = FakeCache()
    _common(monkeypatch)
    monkeypatch.setattr(
        risk_engine_service,
        "load_risk_config",
        lambda _cache: {
            **risk_engine_service.DEFAULT_RISK_CONFIG,
            "max_daily_loss_pct": 8.0,
            "max_consecutive_losses": 2,
            "strategy_cooldown_minutes": 12,
        },
    )
    monkeypatch.setattr(risk_engine_service, "_daily_loss_stats", lambda db, user_id, wallet_usdt_balance: {"daily_loss_pct": 0.4})
    monkeypatch.setattr(risk_engine_service, "_consecutive_losses", lambda db, user_id: 3)

    result = risk_engine_service.evaluate_risk_decision(
        db=object(),
        cache=cache,
        user_id="u1",
        symbol="ETHUSDT",
        strategy_decision="LONG",
        market_type="spot",
        proposed_notional_usdt=100.0,
        strategy_code="trend_v1",
    )

    assert result["risk_decision"] == "PASS"
    assert "max_consecutive_losses_exceeded" in result["reason_codes"]
    assert result["cooldown_state"]["strategy"]["active"] is True
