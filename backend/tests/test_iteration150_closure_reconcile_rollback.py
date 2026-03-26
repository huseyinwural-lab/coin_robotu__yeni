import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from db import SessionLocal
from model_domains.auth_users import User, UserRole
from models import UserOnboardingDecisionLog
from services.onboarding_approval_service import execute_onboarding_decision
from services.onboarding_observability_service import build_onboarding_observability_summary


def _new_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def test_reconcile_status_degraded_when_audit_decision_mismatch():
    db = SessionLocal()
    created_actor_id = None
    created_user_id = None
    created_decision_id = None
    try:
        actor = User(
            email=_new_email("obs-actor"),
            password_hash="x",
            role=UserRole.SUPER_ADMIN,
            approval_status="approved",
            is_active=True,
        )
        user = User(
            email=_new_email("obs-user"),
            password_hash="x",
            role=UserRole.USER,
            approval_status="pending",
            is_active=False,
        )
        db.add(actor)
        db.add(user)
        db.commit()
        db.refresh(actor)
        db.refresh(user)
        created_actor_id = actor.id
        created_user_id = user.id

        log = UserOnboardingDecisionLog(
            user_id=user.id,
            decision="rejected",
            decision_source="manual",
            actor_user_id=actor.id,
            actor_role="super_admin",
            reason="manual_reject_without_audit",
            explanation="reconcile mismatch simulation",
            context_snapshot={"simulated": True},
            created_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        created_decision_id = log.id

        summary = build_onboarding_observability_summary(db, days=1)
        assert summary.get("status") == "degraded"
        mismatch = summary.get("reconcile", {}).get("mismatch_reasons") or []
        assert "decision_audit_count_mismatch" in mismatch
    finally:
        db.rollback()
        if created_decision_id:
            db.query(UserOnboardingDecisionLog).filter(UserOnboardingDecisionLog.id == created_decision_id).delete()
            db.commit()
        if created_user_id:
            db.query(User).filter(User.id == created_user_id).delete()
            db.commit()
        if created_actor_id:
            db.query(User).filter(User.id == created_actor_id).delete()
            db.commit()
        db.close()


def test_decision_rollback_when_audit_write_fails(monkeypatch):
    db = SessionLocal()
    admin_id = None
    target_user_id = None

    try:
        admin_user = User(
            email=_new_email("rollback-admin"),
            password_hash="x",
            role=UserRole.SUPER_ADMIN,
            approval_status="approved",
            is_active=True,
        )
        target_user = User(
            email=_new_email("rollback-user"),
            password_hash="x",
            role=UserRole.USER,
            approval_status="pending",
            is_active=False,
        )
        db.add(admin_user)
        db.add(target_user)
        db.commit()
        db.refresh(admin_user)
        db.refresh(target_user)
        admin_id = admin_user.id
        target_user_id = target_user.id

        import services.onboarding_approval_service as onboarding_service

        monkeypatch.setattr(
            onboarding_service,
            "build_onboarding_context",
            lambda _db, _uid: {
                "approval_disabled": False,
                "approval_disable_reasons": [],
                "missing_data_fields": [],
                "risk_score": 10,
                "aml_flag": "clear",
                "decision_engine": {"recommended_action": "auto_approve", "why_approving": "safe"},
                "decision_support": {},
            },
        )
        monkeypatch.setattr(
            onboarding_service,
            "run_post_approval_activation",
            lambda *args, **kwargs: {"events": 0},
        )

        def _raise_audit_failure(*args, **kwargs):
            raise RuntimeError("simulated_audit_write_failure")

        monkeypatch.setattr(onboarding_service, "create_audit_log", _raise_audit_failure)

        with pytest.raises(HTTPException) as exc:
            execute_onboarding_decision(
                db,
                user_id=target_user.id,
                actor=admin_user,
                decision="approve",
                reason="rollback test reason",
                explanation="this explanation is intentionally long enough",
                confirm_token="CONFIRM",
                decision_source="manual",
            )

        assert exc.value.status_code == 500
        assert str(exc.value.detail) == "decision_transaction_failed"

        db.expire_all()
        persisted_user = db.query(User).filter(User.id == target_user.id).first()
        assert persisted_user is not None
        assert persisted_user.approval_status == "pending"
        assert persisted_user.is_active is False

        decision_logs_count = db.query(UserOnboardingDecisionLog).filter(UserOnboardingDecisionLog.user_id == target_user.id).count()
        assert decision_logs_count == 0
    finally:
        if target_user_id:
            db.query(UserOnboardingDecisionLog).filter(UserOnboardingDecisionLog.user_id == target_user_id).delete()
            db.commit()
            db.query(User).filter(User.id == target_user_id).delete()
            db.commit()
        if admin_id:
            db.query(User).filter(User.id == admin_id).delete()
            db.commit()
        db.close()
