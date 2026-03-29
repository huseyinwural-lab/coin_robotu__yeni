# ruff: noqa: E402
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import SessionLocal
from models import LearningDecisionEvent, User, UserRole
from core.security import hash_password
from services.learning_memory_service import _decay_and_drift, _rolling_window_summary, simulate_learning_recommendation_impact


def _seed_events(db, strategy_id: str, symbol: str, family: str = "trend"):
    now = datetime.now(timezone.utc)
    user = User(
        email=f"adaptive-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=UserRole.USER,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.flush()
    rows = []
    for idx in range(18):
        days_ago = 5 if idx < 6 else 20 if idx < 12 else 70
        pnl = -0.01 if idx < 4 else 0.02 if idx < 10 else 0.01
        outcome = "LOSS" if pnl < 0 else "WIN"
        rows.append(
            LearningDecisionEvent(
                id=str(uuid.uuid4()),
                user_id=user.id,
                symbol=symbol,
                scanner_result_id=None,
                decision="LONG",
                source_strategies=[{"strategy_id": strategy_id, "family": family}],
                family_scores={family: 0.8},
                regime_snapshot={"market_regime": "high_volatility" if idx < 6 else "bull"},
                risk_snapshot={},
                entry_price=100,
                exit_price=101,
                max_favorable_excursion=max(pnl, 0),
                max_adverse_excursion=min(pnl, 0),
                hold_duration_minutes=30,
                outcome_label=outcome,
                pnl_normalized=pnl,
                stop_hit=pnl < 0,
                tp_hit=pnl > 0,
                timed_exit=False,
                invalidated=False,
                strategy_id=strategy_id,
                strategy_family=family,
                pending_signal_id=None,
                position_id=None,
                created_at=now - timedelta(days=days_ago),
                closed_at=now - timedelta(days=days_ago - 1),
            )
        )
    db.add_all(rows)
    db.commit()
    return rows


def test_adaptive_decay_and_drift_outputs():
    db = SessionLocal()
    try:
        strategy_id = f"ADAPTIVE_{uuid.uuid4().hex[:8]}"
        rows = _seed_events(db, strategy_id, "BTCUSDT")
        rolling = _rolling_window_summary(rows)
        drift = _decay_and_drift(rows)
        assert set(rolling.keys()) == {"7d", "30d", "90d"}
        assert "window_comparison" in drift
        assert "decay_score" in drift
        assert "regime_drift_flag" in drift
        assert "stability_score" in drift
    finally:
        db.close()


def test_multi_strategy_portfolio_simulation_contract():
    db = SessionLocal()
    try:
        s1 = f"PORT_{uuid.uuid4().hex[:6]}"
        s2 = f"PORT_{uuid.uuid4().hex[:6]}"
        _seed_events(db, s1, "BTCUSDT")
        _seed_events(db, s2, "ETHUSDT")
        payload = simulate_learning_recommendation_impact(
            db,
            strategy_id=None,
            strategy_ids=[s1, s2],
            family=None,
            symbol_cluster=["BTCUSDT", "ETHUSDT"],
            scenario="stressed",
            recommendation_type="decrease_weight_recommendation",
            suggested_weight_multiplier=0.8,
        )
        assert payload["scope"] in {"portfolio", "symbol_cluster"}
        assert "baseline_metrics" in payload
        assert "projected_metrics" in payload
        assert "delta_metrics" in payload
        assert "sample_coverage" in payload
        assert "portfolio_impact" in payload
        assert "interaction_effects" in payload
        assert payload["sample_coverage"].get("reliability_score") is not None
    finally:
        db.close()
