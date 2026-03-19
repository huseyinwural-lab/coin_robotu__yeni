# ruff: noqa: E402
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import SessionLocal
from deps import require_admin
from models import ExecutionIntent, ExecutionIntentEvent, StrategyDefinition, StrategyVersion, User, UserRole
from server import fastapi_app
from services.execution_safety_service import (
    REASON_MAX_ACTIVE_POSITIONS_EXCEEDED,
    REASON_MAX_TOTAL_EXPOSURE_EXCEEDED,
    REASON_TRADING_DISABLED,
    update_execution_safety_state,
)
from services.runtime_event_bus_service import publish_runtime_event
from services.runtime_execution_service import dispatch_decision_result, process_submission_event_once


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_admin(db, email: str) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        return existing

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash="phase3-test",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _cleanup_runtime_intents(db, account_id: str) -> None:
    db.rollback()
    intent_ids = [row[0] for row in db.query(ExecutionIntent.intent_id).filter(ExecutionIntent.account_id == account_id).all()]
    if intent_ids:
        db.query(ExecutionIntentEvent).filter(ExecutionIntentEvent.intent_id.in_(intent_ids)).delete(synchronize_session=False)
    db.query(ExecutionIntent).filter(ExecutionIntent.account_id == account_id).delete(synchronize_session=False)
    db.commit()


def _ensure_strategy(db, *, created_by: str) -> tuple[str, str]:
    code = "phase3_safety_strategy"
    strategy = db.query(StrategyDefinition).filter(StrategyDefinition.code == code).first()
    if strategy is None:
        strategy = StrategyDefinition(
            strategy_id=str(uuid.uuid4()),
            name="Phase3 Safety Strategy",
            code=code,
            description="phase3 safety test strategy",
            owner_type="admin",
            created_by=created_by,
            status="active",
        )
        db.add(strategy)
        db.commit()
        db.refresh(strategy)

    version = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy.strategy_id)
        .order_by(StrategyVersion.created_at.desc())
        .first()
    )
    if version is None:
        version = StrategyVersion(
            version_id=str(uuid.uuid4()),
            strategy_id=strategy.strategy_id,
            version_number=1,
            config_json={"phase": 3},
            config_schema_version="1.0",
            created_by=created_by,
            version_hash=str(uuid.uuid4()).replace("-", ""),
        )
        db.add(version)
        strategy.active_version_id = version.version_id
        db.commit()
        db.refresh(version)

    return strategy.strategy_id, version.version_id


def _seed_pending_runtime_intent(
    db,
    *,
    account_id: str,
    strategy_id: str,
    strategy_version_id: str,
    quantity: float,
    symbol: str = "BTCUSDT",
) -> ExecutionIntent:
    intent_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    intent_hash = str(uuid.uuid4())
    row = ExecutionIntent(
        intent_id=intent_id,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        account_id=account_id,
        symbol=symbol,
        side="BUY",
        order_type="MARKET",
        quantity=quantity,
        price_reference={"mid_price": 100.0},
        decision_hash=str(uuid.uuid4()),
        context_hash=str(uuid.uuid4()),
        correlation_id=correlation_id,
        intent_hash=intent_hash,
        status="pending",
        created_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _dispatch_open_decision(
    db,
    *,
    account_id: str,
    strategy_id: str,
    strategy_version_id: str,
    size: float = 10.0,
    symbol: str = "BTCUSDT",
):
    correlation_id = str(uuid.uuid4())
    decision_result = {
        "action": "BUY",
        "size": size,
        "strategy_version_id": strategy_version_id,
        "decision_hash": str(uuid.uuid4()),
        "context_hash": str(uuid.uuid4()),
        "price_reference": {"mid_price": 100.0},
    }
    context_payload = {"account_id": account_id, "symbol": symbol}
    return dispatch_decision_result(
        db,
        strategy_id=strategy_id,
        correlation_id=correlation_id,
        decision_result=decision_result,
        context_payload=context_payload,
    )


def test_scenario_a_kill_switch_blocks_new_execution_intent():
    db = SessionLocal()
    account_id = "phase3-a-account"
    try:
        _cleanup_runtime_intents(db, account_id)
        admin = _ensure_admin(db, "phase3-admin-a@example.local")
        strategy_id, strategy_version_id = _ensure_strategy(db, created_by=admin.id)
        update_execution_safety_state(
            db,
            trading_enabled=False,
            reason="phase3_test_kill_switch",
            requested_by="pytest",
            effective_at=None,
            actor_user_id=admin.id,
            actor_role=admin.role.value,
            max_total_exposure=500,
            max_active_positions=10,
        )

        decision, intent, _events = _dispatch_open_decision(
            db,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            size=20,
        )
        assert intent is None
        assert decision.get("action") == "REJECT"
        assert REASON_TRADING_DISABLED in (decision.get("reason_codes") or [])
    finally:
        _cleanup_runtime_intents(db, account_id)
        db.close()


def test_scenario_b_exposure_limit_blocks_over_limit_execution():
    db = SessionLocal()
    account_id = "phase3-b-account"
    try:
        _cleanup_runtime_intents(db, account_id)
        admin = _ensure_admin(db, "phase3-admin-b@example.local")
        strategy_id, strategy_version_id = _ensure_strategy(db, created_by=admin.id)
        update_execution_safety_state(
            db,
            trading_enabled=True,
            reason="phase3_test_exposure",
            requested_by="pytest",
            effective_at=None,
            actor_user_id=admin.id,
            actor_role=admin.role.value,
            max_total_exposure=25,
            max_active_positions=10,
        )
        _seed_pending_runtime_intent(
            db,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            quantity=20,
        )

        decision, intent, _events = _dispatch_open_decision(
            db,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            size=10,
        )
        assert intent is None
        assert decision.get("action") == "REJECT"
        assert REASON_MAX_TOTAL_EXPOSURE_EXCEEDED in (decision.get("reason_codes") or [])
    finally:
        _cleanup_runtime_intents(db, account_id)
        db.close()


def test_scenario_c_active_position_limit_blocks_when_full():
    db = SessionLocal()
    account_id = "phase3-c-account"
    try:
        _cleanup_runtime_intents(db, account_id)
        admin = _ensure_admin(db, "phase3-admin-c@example.local")
        strategy_id, strategy_version_id = _ensure_strategy(db, created_by=admin.id)
        update_execution_safety_state(
            db,
            trading_enabled=True,
            reason="phase3_test_active_positions",
            requested_by="pytest",
            effective_at=None,
            actor_user_id=admin.id,
            actor_role=admin.role.value,
            max_total_exposure=10_000,
            max_active_positions=1,
        )
        _seed_pending_runtime_intent(
            db,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            quantity=1,
        )

        decision, intent, _events = _dispatch_open_decision(
            db,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            size=1,
        )
        assert intent is None
        assert decision.get("action") == "REJECT"
        assert REASON_MAX_ACTIVE_POSITIONS_EXCEEDED in (decision.get("reason_codes") or [])
    finally:
        _cleanup_runtime_intents(db, account_id)
        db.close()


def test_scenario_d_safe_limits_allow_normal_flow():
    db = SessionLocal()
    account_id = "phase3-d-account"
    try:
        _cleanup_runtime_intents(db, account_id)
        admin = _ensure_admin(db, "phase3-admin-d@example.local")
        strategy_id, strategy_version_id = _ensure_strategy(db, created_by=admin.id)
        update_execution_safety_state(
            db,
            trading_enabled=True,
            reason="phase3_test_safe_flow",
            requested_by="pytest",
            effective_at=None,
            actor_user_id=admin.id,
            actor_role=admin.role.value,
            max_total_exposure=10_000,
            max_active_positions=20,
        )

        decision, intent, _events = _dispatch_open_decision(
            db,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            size=10,
        )
        assert decision.get("action") == "BUY"
        assert intent is not None
        assert intent.get("status") == "pending"
    finally:
        _cleanup_runtime_intents(db, account_id)
        db.close()


def test_admin_kill_switch_endpoint_is_idempotent_and_returns_state():
    db = SessionLocal()
    admin = _ensure_admin(db, "phase3-admin-endpoint@example.local")

    fastapi_app.dependency_overrides[require_admin] = lambda: admin
    client = TestClient(fastapi_app)
    try:
        payload = {
            "trading_enabled": False,
            "reason": "maintenance",
            "requested_by": "phase3-test",
            "max_total_exposure": 120,
            "max_active_positions": 2,
        }
        first = client.post("/api/admin/kill-switch", json=payload)
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["reason_code"] == REASON_TRADING_DISABLED
        assert first_body["trading_enabled"] is False

        second = client.post("/api/admin/kill-switch", json=payload)
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["idempotent"] is True
        assert second_body["reason_code"] == REASON_TRADING_DISABLED
    finally:
        fastapi_app.dependency_overrides.pop(require_admin, None)
        db.close()


def test_worker_path_is_blocked_by_kill_switch_reason_code():
    db = SessionLocal()
    account_id = "phase3-worker-account"
    try:
        _cleanup_runtime_intents(db, account_id)
        admin = _ensure_admin(db, "phase3-admin-worker@example.local")
        strategy_id, strategy_version_id = _ensure_strategy(db, created_by=admin.id)
        update_execution_safety_state(
            db,
            trading_enabled=False,
            reason="phase3_test_worker_block",
            requested_by="pytest",
            effective_at=None,
            actor_user_id=admin.id,
            actor_role=admin.role.value,
            max_total_exposure=1000,
            max_active_positions=10,
        )
        row = _seed_pending_runtime_intent(
            db,
            account_id=account_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            quantity=3,
        )

        publish_runtime_event(
            event_type="execution.order.submission_requested",
            payload={"intent_id": row.intent_id},
            correlation_id=str(uuid.uuid4()),
            causation_id=row.intent_id,
            partition_key=f"{row.symbol}::phase3-worker",
        )
        result = process_submission_event_once(db, worker_name=f"phase3-worker-{uuid.uuid4()}")
        assert result is not None
        assert result.get("status") == "blocked"
        assert result.get("reason_code") == REASON_TRADING_DISABLED
    finally:
        _cleanup_runtime_intents(db, account_id)
        db.close()
