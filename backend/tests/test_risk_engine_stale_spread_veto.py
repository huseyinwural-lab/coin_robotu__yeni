from services import risk_engine_service


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def _base_monkeypatch(monkeypatch):
    monkeypatch.setattr(
        risk_engine_service,
        "load_risk_config",
        lambda _cache: {
            **risk_engine_service.DEFAULT_RISK_CONFIG,
            "stale_data_threshold_ms": 1_000,
            "spread_threshold_bps": 20.0,
        },
    )
    monkeypatch.setattr(
        risk_engine_service,
        "build_exposure_snapshot",
        lambda db, user_id, symbol, proposed_notional_usdt: {
            "wallet_usdt_balance": 10_000.0,
            "open_exposure_usdt": 500.0,
            "pending_exposure_usdt": 200.0,
            "symbol_exposure_usdt": 100.0,
            "cluster_exposure_usdt": 150.0,
            "cluster_id": "majors",
            "projected_total_exposure_usdt": 1_200.0,
            "projected_symbol_exposure_usdt": 700.0,
            "projected_cluster_exposure_usdt": 800.0,
        },
    )
    monkeypatch.setattr(risk_engine_service, "_daily_loss_stats", lambda db, user_id, wallet_usdt_balance: {"daily_loss_pct": 0.0})
    monkeypatch.setattr(risk_engine_service, "_consecutive_losses", lambda db, user_id: 0)
    monkeypatch.setattr(risk_engine_service, "kill_switch_state", lambda _cache: {"active": False, "reasons": []})


def test_risk_engine_blocks_on_stale_data_severe(monkeypatch):
    cache = FakeCache()
    _base_monkeypatch(monkeypatch)
    monkeypatch.setattr(
        risk_engine_service,
        "evaluate_execution_quality",
        lambda **kwargs: {"score": 90.0, "severity": "normal", "recommendation": "ALLOW", "metrics": kwargs},
    )

    result = risk_engine_service.evaluate_risk_decision(
        db=object(),
        cache=cache,
        user_id="u1",
        symbol="BTCUSDT",
        strategy_decision="LONG",
        market_type="spot",
        proposed_notional_usdt=100.0,
        snapshot_age_ms=2_500,
        spread_bps=10.0,
    )

    assert result["risk_decision"] == "BLOCK"
    assert "stale_data_block" in result["reason_codes"]


def test_risk_engine_passes_on_medium_spread_veto(monkeypatch):
    cache = FakeCache()
    _base_monkeypatch(monkeypatch)
    monkeypatch.setattr(
        risk_engine_service,
        "evaluate_execution_quality",
        lambda **kwargs: {"score": 90.0, "severity": "normal", "recommendation": "ALLOW", "metrics": kwargs},
    )

    result = risk_engine_service.evaluate_risk_decision(
        db=object(),
        cache=cache,
        user_id="u1",
        symbol="ETHUSDT",
        strategy_decision="LONG",
        market_type="spot",
        proposed_notional_usdt=100.0,
        snapshot_age_ms=500,
        spread_bps=25.0,
    )

    assert result["risk_decision"] == "PASS"
    assert "spread_pass" in result["reason_codes"]
