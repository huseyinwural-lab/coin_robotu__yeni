from services import risk_engine_service


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def test_risk_kill_switch_blocks_new_decisions(monkeypatch):
    cache = FakeCache()

    monkeypatch.setattr(
        risk_engine_service,
        "load_risk_config",
        lambda _cache: {**risk_engine_service.DEFAULT_RISK_CONFIG, "kill_switch_enabled": True},
    )
    monkeypatch.setattr(
        risk_engine_service,
        "build_exposure_snapshot",
        lambda db, user_id, symbol, proposed_notional_usdt: {
            "wallet_usdt_balance": 10_000.0,
            "open_exposure_usdt": 100.0,
            "pending_exposure_usdt": 0.0,
            "symbol_exposure_usdt": 50.0,
            "cluster_exposure_usdt": 50.0,
            "cluster_id": "majors",
            "projected_total_exposure_usdt": 200.0,
            "projected_symbol_exposure_usdt": 100.0,
            "projected_cluster_exposure_usdt": 100.0,
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
        proposed_notional_usdt=100.0,
    )

    assert result["risk_decision"] == "BLOCK"
    assert "risk_kill_switch_enabled" in result["reason_codes"]
    assert risk_engine_service.is_risk_kill_switch_active(cache) is True


def test_runtime_kill_switch_blocks_execution_submit_signal():
    from core.execution_engine import submit_signal
    from core.safety.kill_switch import activate_kill_switch, deactivate_kill_switch
    from db import SessionLocal
    from models import User

    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.created_at.asc()).first()
        assert user is not None
        activate_kill_switch(source="test", reason="runtime_kill_switch_test")

        result = submit_signal(
            db,
            user_id=user.id,
            signal={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 0.1,
                "strategy_name": "ema_rsi",
                "mark_price": 100,
                "leverage": 1,
            },
            idempotency_key="iter4-kill-switch-runtime",
        )
        assert result.get("status") == "rejected"
        assert result.get("risk", {}).get("reject_reason") == "kill_switch_active"
    finally:
        deactivate_kill_switch(source="test", reason="runtime_kill_switch_reset")
        db.close()
