from services import risk_engine_service


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def test_risk_engine_blocks_when_total_exposure_limit_exceeded(monkeypatch):
    cache = FakeCache()

    monkeypatch.setattr(
        risk_engine_service,
        "load_risk_config",
        lambda _cache: {
            **risk_engine_service.DEFAULT_RISK_CONFIG,
            "max_total_exposure_pct": 60.0,
            "max_symbol_exposure_pct": 40.0,
            "max_cluster_exposure_pct": 50.0,
        },
    )
    monkeypatch.setattr(
        risk_engine_service,
        "build_exposure_snapshot",
        lambda db, user_id, symbol, proposed_notional_usdt: {
            "wallet_usdt_balance": 10_000.0,
            "open_exposure_usdt": 4_000.0,
            "pending_exposure_usdt": 500.0,
            "symbol_exposure_usdt": 2_000.0,
            "cluster_exposure_usdt": 2_500.0,
            "cluster_id": "majors",
            "projected_total_exposure_usdt": 7_000.0,
            "projected_symbol_exposure_usdt": 3_000.0,
            "projected_cluster_exposure_usdt": 4_000.0,
        },
    )
    monkeypatch.setattr(risk_engine_service, "_daily_loss_stats", lambda db, user_id, wallet_usdt_balance: {"daily_loss_pct": 0.0})
    monkeypatch.setattr(risk_engine_service, "_consecutive_losses", lambda db, user_id: 0)
    monkeypatch.setattr(risk_engine_service, "kill_switch_state", lambda _cache: {"active": False, "reasons": []})

    result = risk_engine_service.evaluate_risk_decision(
        db=object(),
        cache=cache,
        user_id="u1",
        symbol="BTCUSDT",
        strategy_decision="LONG",
        market_type="spot",
        proposed_notional_usdt=2_500.0,
    )

    assert result["risk_decision"] == "BLOCK"
    assert "max_total_exposure_pct_exceeded" in result["reason_codes"]
