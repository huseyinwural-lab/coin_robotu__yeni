# ruff: noqa: E402
import json
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import deps
from core.security import hash_password
from db import SessionLocal
from models import User, UserExecutionIntent, UserRole
from server import fastapi_app
from services.execution_intent_service import approve_execution_intent, preview_execution_intent, submit_execution_intent
from services.idempotency_service import build_execution_idempotency_key


SAME_PAYLOAD_LOG = Path("/app/artifacts/faz2_same_payload_twice_test.log")
CONCURRENT_LOG = Path("/app/artifacts/faz2_concurrent_duplicate_test.log")
DUPLICATE_RESPONSE_ARTIFACT = Path("/app/artifacts/faz2_duplicate_reject_response.json")


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


def _base_payload(unique_ref: str) -> dict:
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
        "size": 0.001,
        "timestamp": "2026-03-19T12:45:10Z",
        "scanner_signal_snapshot": {
            "signal_id": unique_ref,
            "timestamp": "2026-03-19T12:45:10Z",
        },
    }


def test_faz2_same_payload_twice_and_api_duplicate_reject(monkeypatch):
    import services.execution_intent_service as execution_service

    monkeypatch.setattr(execution_service, "enforce_execution_guard_or_raise", lambda *args, **kwargs: {"mode": "MOCKED"})
    monkeypatch.setattr(
        execution_service,
        "validate_order_precheck",
        lambda *args, **kwargs: {"valid": True, "violations": [], "checks": {}},
    )

    db = SessionLocal()
    try:
        user = _create_user(db, role=UserRole.USER)
        admin = _create_user(db, role=UserRole.ADMIN)
        payload = _base_payload(unique_ref=f"evt-{uuid.uuid4().hex[:8]}")

        fastapi_app.dependency_overrides[deps.require_user] = lambda: user
        with TestClient(fastapi_app) as client:
            first = client.post("/api/user/execution/intent/preview", json=payload)
            assert first.status_code == 200, first.text
            first_payload = first.json()

            queued = submit_execution_intent(
                db,
                user_id=user.id,
                intent_token=first_payload["intent_token"],
                preview_hash=first_payload["preview_hash"],
            )
            released = approve_execution_intent(db, queued.id, admin.id, admin_note="faz2_same_payload_test")
            assert released.status == "RELEASED"

            second = client.post("/api/user/execution/intent/preview", json=payload)

        fastapi_app.dependency_overrides.clear()

        assert second.status_code == 409, second.text
        second_payload = second.json()
        assert second_payload.get("error") == "duplicate_intent"
        assert second_payload.get("intent_id") == first_payload.get("intent_id")
        assert second_payload.get("message") == "Duplicate execution intent rejected"

        idempotency_key = build_execution_idempotency_key(user_id=user.id, payload=payload)
        db_row_count = (
            db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.idempotency_key == idempotency_key)
            .count()
        )
        execution_count = (
            db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.idempotency_key == idempotency_key, UserExecutionIntent.status == "RELEASED")
            .count()
        )
        double_execution = 1 if execution_count > 1 else 0

        SAME_PAYLOAD_LOG.parent.mkdir(parents=True, exist_ok=True)
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

        DUPLICATE_RESPONSE_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        DUPLICATE_RESPONSE_ARTIFACT.write_text(json.dumps(second_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        assert db_row_count == 1
        assert execution_count == 1
        assert double_execution == 0
    finally:
        fastapi_app.dependency_overrides.clear()
        db.close()


def test_faz2_concurrent_duplicate_requests(monkeypatch):
    import services.execution_intent_service as execution_service

    monkeypatch.setattr(execution_service, "enforce_execution_guard_or_raise", lambda *args, **kwargs: {"mode": "MOCKED"})
    monkeypatch.setattr(
        execution_service,
        "validate_order_precheck",
        lambda *args, **kwargs: {"valid": True, "violations": [], "checks": {}},
    )

    setup_db = SessionLocal()
    try:
        user = _create_user(setup_db, role=UserRole.USER)
        admin = _create_user(setup_db, role=UserRole.ADMIN)
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
            return {"status": "success", "intent_id": intent.id, "intent_token": intent.intent_token, "preview_hash": intent.preview_hash}
        except Exception as exc:
            if exc.__class__.__name__ == "DuplicateExecutionIntentError":
                return {"status": "reject", "error": "duplicate_intent", "message": str(exc)}
            raise
        finally:
            worker_db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result() for future in [executor.submit(_worker), executor.submit(_worker)]]

    success_rows = [row for row in results if row.get("status") == "success"]
    reject_rows = [row for row in results if row.get("status") == "reject"]

    assert len(success_rows) == 1
    assert len(reject_rows) == 1

    verify_db = SessionLocal()
    try:
        queued = submit_execution_intent(
            verify_db,
            user_id=user.id,
            intent_token=success_rows[0]["intent_token"],
            preview_hash=success_rows[0]["preview_hash"],
        )
        released = approve_execution_intent(verify_db, queued.id, admin.id, admin_note="faz2_concurrent_test")
        assert released.status == "RELEASED"

        db_row_count = (
            verify_db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.idempotency_key == idempotency_key)
            .count()
        )
        execution_count = (
            verify_db.query(UserExecutionIntent)
            .filter(UserExecutionIntent.idempotency_key == idempotency_key, UserExecutionIntent.status == "RELEASED")
            .count()
        )
        double_execution = 1 if execution_count > 1 else 0

        CONCURRENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        CONCURRENT_LOG.write_text(
            "\n".join(
                [
                    "PARALLEL_REQUESTS_SENT=2",
                    f"SUCCESS_COUNT={len(success_rows)}",
                    f"REJECT_COUNT={len(reject_rows)}",
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
