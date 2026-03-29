# ruff: noqa: E402
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.security import hash_password
from db import SessionLocal
from models import CanonicalStrategyRegistry, LearningRecommendation, User, UserRole
from services.learning_memory_service import _ensure_recommendation_defaults


def _create_admin_and_recommendation():
    db = SessionLocal()
    admin = User(
        email=f"learning-admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Pass1234!Aa"),
        role=UserRole.ADMIN,
        is_active=True,
        approval_status="approved",
    )
    db.add(admin)
    strategy_id = f"TEST_LEARN_{uuid.uuid4().hex[:8]}"
    db.add(
        CanonicalStrategyRegistry(
            strategy_id=strategy_id,
            strategy_family="trend",
            direction="both",
            market_regime="any",
            is_enabled=True,
            weight=1.0,
            entry_long={},
            entry_short={},
        )
    )
    recommendation = LearningRecommendation(
        id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        family=None,
        recommendation_type="strategy_weight_down",
        recommendation_value={"suggested_weight_multiplier": 0.7, "reason": "test reason", "confidence": 0.8, "scope": "strategy", "evidence_summary": {"sample": 10}},
        note="test lifecycle recommendation",
        severity="medium",
        is_applied=False,
    )
    _ensure_recommendation_defaults(recommendation)
    db.add(recommendation)
    db.commit()
    db.refresh(admin)
    db.refresh(recommendation)
    return db, admin, recommendation


def test_learning_lifecycle_service_end_to_end():
    from services.learning_memory_service import (
        apply_learning_recommendation,
        approve_learning_recommendation,
        get_learning_post_change_monitoring,
        get_learning_version_history,
        mark_learning_recommendation_simulated,
        reject_learning_recommendation,
        rollback_learning_recommendation,
    )

    db, admin, recommendation = _create_admin_and_recommendation()
    try:
        simulated = mark_learning_recommendation_simulated(
            db,
            recommendation_id=recommendation.id,
            actor=admin.id,
            reason="simulate",
            simulation_payload={"scope": "strategy", "baseline": {}, "counterfactual_replay": {}},
        )
        assert simulated["lifecycle"] == "simulated"

        approved = approve_learning_recommendation(db, recommendation_id=recommendation.id, actor=admin.id, reason="approve")
        assert approved["lifecycle"] == "approved"

        applied = apply_learning_recommendation(db, recommendation_id=recommendation.id, actor=admin.id, reason="apply")
        assert applied["is_applied"] is True
        assert applied["lifecycle"] == "applied"

        monitoring = get_learning_post_change_monitoring(db, recommendation_id=recommendation.id)
        assert "windows" in monitoring
        assert set(monitoring["windows"].keys()) == {"1h", "24h", "7d"}

        version_history = get_learning_version_history(db, recommendation_id=recommendation.id)
        assert version_history["items"]

        rolled_back = rollback_learning_recommendation(db, recommendation_id=recommendation.id, actor=admin.id, reason="rollback")
        assert rolled_back["lifecycle"] == "rolled_back"

        rejected = reject_learning_recommendation(db, recommendation_id=recommendation.id, actor=admin.id, reason="reject-final")
        assert rejected["lifecycle"] == "rejected"
    finally:
        db.close()
