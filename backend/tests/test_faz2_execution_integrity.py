# ruff: noqa: E402
import json
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import deps
from core.security import hash_password
from db import SessionLocal
from models import AuditLog, User, UserExecutionIntent, UserRole
from server import fastapi_app
from services.execution_intent_service import DuplicateExecutionIntentError, preview_execution_intent
from services.idempotency_service import build_execution_idempotency_key


ARTIFACT_DIR = REPO_ROOT / "artifacts"
SAME_PAYLOAD_LOG = ARTIFACT_DIR / "faz2_same_payload_twice_test.log"
CONCURRENT_LOG = ARTIFACT_DIR / "faz2_concurrent_duplicate_test.log"
DIFFERENT_PAYLOAD_LOG = ARTIFACT_DIR / "faz2_different_payload_no_false_duplicate.log"
DUPLICATE_RESPONSE_ARTIFACT = ARTIFACT_DIR / "faz2_duplicate_reject_response.json"
DUPLICATE_AUDIT_ARTIFACT = ARTIFACT_DIR / "faz2_duplicate_reject_audit.json"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(fastapi_app) as test_client:
        yield test_client


def _create_user(db, *, role: UserRole) -> User:
    user = User(
        email=f"faz2-{role.value}-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("Faz2StrongPass123!"),
        role=role,
        is_active=True,
        approval_status="approved",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _base_payload(unique_ref: str, *, size: float = 0.001) -> dict:
    return {
        "source_type": "manual",
        "source_ref_id": unique_ref,
        "intent_type": "OPEN_POSITION",
        "market_type": "futures",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 40,
        "margin_mode": "isolated",
        "leverage": 3,
        "execution_mode": "manual",
        "strategy_binding": "faz2_integrity_strategy",
        "size": size,
        "timestamp": "2026-03-19T12:45:10Z",
        "scanner_signal_snapshot": {
            "signal_id": unique_ref,
            "timestamp": "2026-03-19T12:45:10Z",
        },
    }


def test_faz2_same_payload_twice_and_api_duplicate_reject(client: TestClient):
    db = SessionLocal()
    try:
        user = _create_user(db, role=UserRole.USER)
        payload = _base_payload(unique_ref=f"evt-{uuid.uuid4().hex[:8]}")

        fastapi_app.dependency_overrides[deps.require_user] = lambda: user
        first = client.post("/api/user/execution/intent/preview", json=payload)
        assert first.status_code == 200, first.text
        first_payload = first.json()

        second = client.post("/api/user/execution/intent/preview", json=payload)
        fastapi_app.dependency_overrides.clear()

        assert second.status_code == 409, second.text
        second_payload = second.json()
        assert second_payload.get("error") == "duplicate_intent"
        assert second_payload.get("reason_code") == "DUPLICATE_INTENT"
        assert second_payload.get("intent_id") == first_payload.get("intent_id")
        assert second_payload.get("message") == "Duplicate execution intent rejected"

        idempotency_key = build_execution_idempotency_key(user_id=user.id, payload=payload)
        db_row_count = (
            db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.user_id == user.id, UserExecutionIntent.idempotency_key == idempotency_key)
            .count()
        )
        execution_count = db_row_count
        double_execution = 1 if execution_count > 1 else 0

        duplicate_audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "EXECUTION_INTENT_DUPLICATE_REJECTED",
                AuditLog.entity_id == first_payload.get("intent_id"),
            )
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert duplicate_audit is not None
        assert (duplicate_audit.details or {}).get("reason_code") == "DUPLICATE_INTENT"

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        SAME_PAYLOAD_LOG.write_text(
            "\n".join(
                [
                    f"REQUEST_PAYLOAD={json.dumps(payload, ensure_ascii=False)}",
                    f"FIRST_RESPONSE={json.dumps(first_payload, ensure_ascii=False)}",
                    f"SECOND_RESPONSE={json.dumps(second_payload, ensure_ascii=False)}",
                    "FIRST_REQUEST_OK",
                    "SECOND_REQUEST_REJECTED",
                    f"DB_ROW_COUNT={db_row_count}",
                    f"EXECUTION_COUNT={execution_count}",
                    f"DOUBLE_EXECUTION={double_execution}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        DUPLICATE_RESPONSE_ARTIFACT.write_text(json.dumps(second_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        DUPLICATE_AUDIT_ARTIFACT.write_text(
            json.dumps(
                {
                    "action": duplicate_audit.action,
                    "entity_id": duplicate_audit.entity_id,
                    "details": duplicate_audit.details,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        assert db_row_count == 1
        assert execution_count == 1
        assert double_execution == 0
    finally:
        fastapi_app.dependency_overrides.clear()
        db.close()


def test_faz2_concurrent_duplicate_requests():
    setup_db = SessionLocal()
    try:
        user = _create_user(setup_db, role=UserRole.USER)
        payload = _base_payload(unique_ref=f"evt-concurrent-{uuid.uuid4().hex[:8]}")
        idempotency_key = build_execution_idempotency_key(user_id=user.id, payload=payload)
    finally:
        setup_db.close()

    barrier = threading.Barrier(2)

    def _worker() -> dict:
        worker_db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            intent, _validation = preview_execution_intent(worker_db, user.id, payload)
            return {"status": "success", "intent_id": intent.intent_id}
        except DuplicateExecutionIntentError as exc:
            return {
                "status": "reject",
                "error": "duplicate_intent",
                "reason_code": exc.reason_code,
                "intent_id": exc.intent_id,
            }
        finally:
            worker_db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in [executor.submit(_worker), executor.submit(_worker)]]

    success_rows = [row for row in results if row.get("status") == "success"]
    reject_rows = [row for row in results if row.get("status") == "reject"]

    assert len(success_rows) == 1
    assert len(reject_rows) == 1
    assert reject_rows[0].get("reason_code") == "DUPLICATE_INTENT"

    verify_db = SessionLocal()
    try:
        db_row_count = (
            verify_db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.user_id == user.id, UserExecutionIntent.idempotency_key == idempotency_key)
            .count()
        )
        execution_count = db_row_count
        double_execution = 1 if execution_count > 1 else 0

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        CONCURRENT_LOG.write_text(
            "\n".join(
                [
                    "PARALLEL_REQUESTS_SENT=2",
                    f"SUCCESS_COUNT={len(success_rows)}",
                    f"REJECT_COUNT={len(reject_rows)}",
                    f"REJECT_REASON_CODE={reject_rows[0].get('reason_code')}",
                    f"DB_ROW_COUNT={db_row_count}",
                    f"EXECUTION_COUNT={execution_count}",
                    f"DOUBLE_EXECUTION={double_execution}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        assert db_row_count == 1
        assert execution_count == 1
        assert double_execution == 0
    finally:
        verify_db.close()


def test_faz2_different_payload_no_false_duplicate(client: TestClient):
    db = SessionLocal()
    try:
        user = _create_user(db, role=UserRole.USER)
        payload_a = _base_payload(unique_ref=f"evt-a-{uuid.uuid4().hex[:8]}", size=0.001)
        payload_b = _base_payload(unique_ref=f"evt-b-{uuid.uuid4().hex[:8]}", size=0.002)

        fastapi_app.dependency_overrides[deps.require_user] = lambda: user
        first = client.post("/api/user/execution/intent/preview", json=payload_a)
        second = client.post("/api/user/execution/intent/preview", json=payload_b)
        fastapi_app.dependency_overrides.clear()

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        first_payload = first.json()
        second_payload = second.json()
        assert first_payload.get("intent_id") != second_payload.get("intent_id")

        key_a = build_execution_idempotency_key(user_id=user.id, payload=payload_a)
        key_b = build_execution_idempotency_key(user_id=user.id, payload=payload_b)
        assert key_a != key_b

        row_count_a = (
            db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.user_id == user.id, UserExecutionIntent.idempotency_key == key_a)
            .count()
        )
        row_count_b = (
            db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.user_id == user.id, UserExecutionIntent.idempotency_key == key_b)
            .count()
        )

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        DIFFERENT_PAYLOAD_LOG.write_text(
            "\n".join(
                [
                    f"PAYLOAD_A={json.dumps(payload_a, ensure_ascii=False)}",
                    f"PAYLOAD_B={json.dumps(payload_b, ensure_ascii=False)}",
                    f"INTENT_A={first_payload.get('intent_id')}",
                    f"INTENT_B={second_payload.get('intent_id')}",
                    f"KEY_A={key_a}",
                    f"KEY_B={key_b}",
                    f"ROW_COUNT_A={row_count_a}",
                    f"ROW_COUNT_B={row_count_b}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        assert row_count_a == 1
        assert row_count_b == 1
    finally:
        fastapi_app.dependency_overrides.clear()
        db.close()