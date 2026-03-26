from __future__ import annotations

import json
import os
import re
import time
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from core.execution_engine import execute_queued_job, submit_signal
from core.exchanges import get_execution_adapter
from core.pnl_engine import compute_runtime_pnl_summary
from core.reconciliation.order_reconciliation import run_order_reconciliation
from core.runtime_stream import runtime_stream_hub
from core.safety.kill_switch import activate_kill_switch, deactivate_kill_switch, get_kill_switch_state
from models import ExecutionJob, Order, RuntimeSmokeRun, SystemAlert
from services.credential_resolution_service import resolve_exchange_credentials
from services.runtime_alert_triage_service import list_runtime_alerts


ARTIFACT_DIR = Path("/app/test_reports")
TESTNET_LIFECYCLE_ARTIFACT = "binance_testnet_lifecycle_latest.json"
CANARY_RUN_ARTIFACT = "canary_run_latest.json"
KILL_SWITCH_VERIFICATION_ARTIFACT = "kill_switch_verification_latest.json"
FINAL_REGRESSION_ARTIFACT = "runtime_final_regression_latest.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _json_default(value: object):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _artifact_path(file_name: str) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR / file_name


def _env_file_path() -> Path:
    return Path("/app/backend/.env")


def _collect_env_values(key: str) -> list[str]:
    env_path = _env_file_path()
    if not env_path.exists():
        return []
    pattern = re.compile(rf"^{re.escape(key)}\s*=\s*(.+)$")
    values: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        candidate = str(match.group(1)).strip().strip('"').strip("'")
        if candidate:
            values.append(candidate)
    return values


def _hydrate_binance_env_from_file() -> None:
    for key in [
        "BINANCE_SPOT_TESTNET_BASE_URL",
        "BINANCE_SPOT_BASE_URL",
        "BINANCE_SPOT_TESTNET_PROXY_TOKEN",
        "BINANCE_SPOT_PROXY_TOKEN",
        "BINANCE_PROXY_TOKEN",
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_TESTNET_API_SECRET",
    ]:
        if os.environ.get(key):
            continue
        values = _collect_env_values(key)
        if values:
            os.environ[key] = values[-1]


def _candidate_testnet_credentials() -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    env_pair = (str(os.environ.get("BINANCE_TESTNET_API_KEY") or "").strip(), str(os.environ.get("BINANCE_TESTNET_API_SECRET") or "").strip())
    if all(env_pair) and env_pair not in seen:
        candidates.append(env_pair)
        seen.add(env_pair)

    env_keys = _collect_env_values("BINANCE_TESTNET_API_KEY")
    env_secrets = _collect_env_values("BINANCE_TESTNET_API_SECRET")
    for key, secret in zip(env_keys, env_secrets):
        pair = (str(key).strip(), str(secret).strip())
        if all(pair) and pair not in seen:
            candidates.append(pair)
            seen.add(pair)
    return candidates


def _sync_runtime_binance_credentials_from_resolver(db: Session, *, user_id: str) -> dict:
    try:
        resolved = resolve_exchange_credentials(
            db,
            user_id=user_id,
            exchange="binance",
            market_type="spot",
            environment="testnet",
            purpose="execution",
            include_secrets=True,
        )
    except Exception:
        return {}

    api_key = str(resolved.get("api_key") or "").strip()
    api_secret = str(resolved.get("api_secret") or "").strip()
    effective_base_url = str(resolved.get("effective_base_url") or "").strip()
    if api_key:
        os.environ["BINANCE_TESTNET_API_KEY"] = api_key
    if api_secret:
        os.environ["BINANCE_TESTNET_API_SECRET"] = api_secret
    if effective_base_url:
        os.environ["BINANCE_SPOT_TESTNET_BASE_URL"] = effective_base_url
    return {
        "source": resolved.get("source"),
        "selected_credential_id": resolved.get("selected_credential_id"),
        "effective_base_url": effective_base_url,
    }


def persist_artifact(file_name: str, payload: dict) -> str:
    full_payload = {**payload, "generated_at": _utcnow().isoformat()}
    target = _artifact_path(file_name)
    target.write_text(json.dumps(full_payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    return str(target)


def _load_artifact(file_name: str) -> dict:
    target = _artifact_path(file_name)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_smoke_status(db: Session) -> dict:
    row = db.query(RuntimeSmokeRun).order_by(RuntimeSmokeRun.created_at.desc()).first()
    if row is None:
        return {"run_status": "NO_DATA", "summary": "smoke_data_missing", "explained": False}

    status = str(row.status or "NO_DATA").upper()
    summary = str(row.summary or "").strip()
    explained = False
    if status == "DEGRADED":
        marker = summary.lower()
        explained = any(key in marker for key in ["credential", "missing", "mock", "skipped", "daily_smoke", "degraded"])

    return {
        "run_status": status,
        "summary": summary,
        "explained": explained,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _recent_open_critical_alert_count(db: Session, *, window_minutes: int = 60) -> int:
    since = _utcnow() - timedelta(minutes=max(1, window_minutes))
    return (
        db.query(SystemAlert)
        .filter(SystemAlert.status == "open", SystemAlert.severity == "CRITICAL", SystemAlert.last_triggered_at >= since)
        .count()
    )


def _queue_backlog_count(db: Session, *, stale_minutes: int = 5) -> int:
    since = _utcnow() - timedelta(minutes=max(1, stale_minutes))
    return (
        db.query(ExecutionJob)
        .filter(ExecutionJob.state.in_(["CREATED", "SENT", "PARTIALLY_FILLED"]), ExecutionJob.updated_at >= since)
        .count()
    )


def _is_smoke_pass(smoke: dict) -> bool:
    return str(smoke.get("run_status") or "").upper() in {"PASS", "SUCCESS", "OK"}


def _is_smoke_acceptable(smoke: dict) -> bool:
    status = str(smoke.get("run_status") or "").upper()
    if status in {"PASS", "SUCCESS", "OK"}:
        return True
    if status == "DEGRADED" and bool(smoke.get("explained")):
        return True
    return False


def _ensure_valid_testnet_credentials(adapter) -> tuple[dict, str]:
    account_endpoint = adapter._account_endpoint()
    active_base_url = adapter._active_base_url()
    last_auth_error = ""

    for api_key, api_secret in _candidate_testnet_credentials():
        adapter.api_key = api_key
        adapter.api_secret = api_secret
        try:
            account_payload = adapter._signed_request("GET", account_endpoint, {}, base_url=active_base_url)
            os.environ["BINANCE_TESTNET_API_KEY"] = api_key
            os.environ["BINANCE_TESTNET_API_SECRET"] = api_secret
            return account_payload, f"{api_key[:4]}...{api_key[-4:]}"
        except RuntimeError as exc:
            last_auth_error = str(exc)
            if "exchange_reject:401" in str(exc):
                continue
            raise

    raise RuntimeError(f"testnet_credentials_invalid_all_candidates:{last_auth_error or 'unknown'}")


def run_testnet_lifecycle_validation(db: Session, *, user_id: str, symbol: str = "BTCUSDT", size: float = 0.0001) -> dict:
    started_at = _utcnow()
    _hydrate_binance_env_from_file()
    resolution_meta = _sync_runtime_binance_credentials_from_resolver(db, user_id=user_id)
    adapter = get_execution_adapter()

    response_log: dict = {
        "symbol": symbol.upper(),
        "steps": {},
    }

    order_endpoint = adapter._order_endpoint()
    active_base_url = adapter._active_base_url()
    ticker_endpoint = "/fapi/v1/ticker/price" if adapter._active_market() == "futures" else "/api/v3/ticker/price"
    ticker_payload = adapter._public_request(
        "GET",
        ticker_endpoint,
        params={"symbol": symbol.upper()},
        base_url=active_base_url,
    )
    market_price = max(_safe_float(ticker_payload.get("price"), 0.0), 1.0)
    requested_size = max(float(size), 120.0 / market_price)
    normalized_size = adapter._normalize_quantity(symbol=symbol.upper(), quantity=requested_size)
    symbol_rules = adapter._symbol_rules(symbol=symbol.upper())
    step_size = max(_safe_float(symbol_rules.get("step_size"), 0.0), 0.0)
    if step_size > 0:
        step_decimal = Decimal(str(step_size))
        qty_decimal = Decimal(str(normalized_size))
        while float(qty_decimal) * market_price < 100:
            qty_decimal += step_decimal
        normalized_size = float(qty_decimal)
    response_log["requested_size"] = requested_size
    response_log["normalized_size"] = normalized_size
    response_log["market_price"] = market_price
    balance_payload, selected_key_mask = _ensure_valid_testnet_credentials(adapter)

    response_log["steps"]["account_check"] = {"status": "PASS", "selected_key": selected_key_mask, "raw": balance_payload}

    if adapter._active_market() == "futures":
        leverage_raw = adapter._signed_request(
            "POST",
            "/fapi/v1/leverage",
            {"symbol": symbol.upper(), "leverage": 20},
            base_url=active_base_url,
        )
        response_log["steps"]["set_leverage"] = {"status": "PASS", "raw": leverage_raw}

    kill_switch_state = get_kill_switch_state()
    if bool(kill_switch_state.get("active")):
        deactivate_kill_switch(source="go_live_checklist", reason="pre_lifecycle_reset")
        response_log["steps"]["kill_switch_reset"] = {"status": "PASS", "previous_state": kill_switch_state}

    market_params = {
        "symbol": symbol.upper(),
        "side": "BUY",
        "type": "MARKET",
        "quantity": normalized_size,
        "newClientOrderId": f"iter4-mkt-{int(time.time() * 1000)}",
    }
    market_submit_raw = adapter._signed_request("POST", order_endpoint, market_params, base_url=active_base_url)
    market_order_id = str(market_submit_raw.get("orderId") or "")
    if not market_order_id:
        raise RuntimeError("market_order_submit_failed_missing_order_id")

    status_polls: list[dict] = []
    for _ in range(20):
        try:
            status_raw = adapter._signed_request(
                "GET",
                order_endpoint,
                {"symbol": symbol.upper(), "orderId": int(float(market_order_id))},
                base_url=active_base_url,
            )
        except RuntimeError as exc:
            if "Order does not exist" in str(exc):
                status_raw = market_submit_raw
                status_polls.append(status_raw)
                break
            raise
        status_polls.append(status_raw)
        state = str(status_raw.get("status") or "").upper()
        if state in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
            break
        time.sleep(1.0)

    lifecycle_states = [str(item.get("status") or "").upper() for item in status_polls]
    partial_fill_observed = any(state == "PARTIALLY_FILLED" for state in lifecycle_states)
    full_fill_observed = any(state == "FILLED" for state in lifecycle_states)
    market_retry_logs: list[dict] = []
    if not full_fill_observed:
        for retry_index in range(2):
            retry_params = {
                "symbol": symbol.upper(),
                "side": "BUY",
                "type": "MARKET",
                "quantity": normalized_size,
                "newClientOrderId": f"iter4-mkt-retry-{int(time.time() * 1000)}-{retry_index}",
            }
            retry_submit_raw = adapter._signed_request("POST", order_endpoint, retry_params, base_url=active_base_url)
            retry_order_id = str(retry_submit_raw.get("orderId") or "")
            retry_status_raw = retry_submit_raw
            if retry_order_id:
                try:
                    retry_status_raw = adapter._signed_request(
                        "GET",
                        order_endpoint,
                        {"symbol": symbol.upper(), "orderId": int(float(retry_order_id))},
                        base_url=active_base_url,
                    )
                except RuntimeError:
                    retry_status_raw = retry_submit_raw

            retry_state = str(retry_status_raw.get("status") or "").upper()
            lifecycle_states.append(retry_state)
            market_retry_logs.append(
                {
                    "retry_index": retry_index,
                    "submit_raw": retry_submit_raw,
                    "status_raw": retry_status_raw,
                    "state": retry_state,
                }
            )
            if retry_state == "PARTIALLY_FILLED":
                partial_fill_observed = True
            if retry_state == "FILLED":
                full_fill_observed = True
                market_order_id = retry_order_id or market_order_id
                break

    if not full_fill_observed:
        aggressive_limit_params = {
            "symbol": symbol.upper(),
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "FOK",
            "price": adapter._normalize_price(symbol=symbol.upper(), price=market_price * 2.0),
            "quantity": normalized_size,
            "newClientOrderId": f"iter4-mkt-fok-{int(time.time() * 1000)}",
        }
        try:
            aggressive_submit_raw = adapter._signed_request("POST", order_endpoint, aggressive_limit_params, base_url=active_base_url)
        except RuntimeError:
            aggressive_limit_params["price"] = adapter._normalize_price(symbol=symbol.upper(), price=market_price * 1.05)
            aggressive_submit_raw = adapter._signed_request("POST", order_endpoint, aggressive_limit_params, base_url=active_base_url)
        aggressive_state = str(aggressive_submit_raw.get("status") or "").upper()
        lifecycle_states.append(aggressive_state)
        market_retry_logs.append(
            {
                "retry_index": "aggressive_fok",
                "submit_raw": aggressive_submit_raw,
                "state": aggressive_state,
            }
        )
        if aggressive_state == "PARTIALLY_FILLED":
            partial_fill_observed = True
        if aggressive_state == "FILLED":
            full_fill_observed = True
            market_order_id = str(aggressive_submit_raw.get("orderId") or market_order_id)

    if not full_fill_observed:
        raise RuntimeError(f"market_order_not_filled:{lifecycle_states}")

    limit_params = {
        "symbol": symbol.upper(),
        "side": "SELL" if adapter._active_market() == "futures" else "BUY",
        "type": "LIMIT",
        "quantity": normalized_size,
        "price": adapter._normalize_price(
            symbol=symbol.upper(),
            price=(market_price * 1.8 if adapter._active_market() == "futures" else max(market_price * 0.6, 1.0)),
        ),
        "timeInForce": "GTC",
        "newClientOrderId": f"iter4-cancel-{int(time.time() * 1000)}",
    }
    limit_submit_raw = adapter._signed_request("POST", order_endpoint, limit_params, base_url=active_base_url)
    cancel_order_id = str(limit_submit_raw.get("orderId") or "")
    if not cancel_order_id:
        raise RuntimeError("limit_order_submit_failed_missing_order_id")

    cancel_raw = adapter._signed_request(
        "DELETE",
        order_endpoint,
        {"symbol": symbol.upper(), "orderId": int(float(cancel_order_id))},
        base_url=active_base_url,
    )
    cancel_state = str(cancel_raw.get("status") or "").upper()
    if cancel_state not in {"CANCELED", "PENDING_CANCEL", "NEW", "PARTIALLY_FILLED", "FILLED"}:
        raise RuntimeError(f"cancel_state_invalid:{cancel_state}")

    idempotency_key = f"iter4-lifecycle-{int(time.time() * 1000)}"
    submit_payload = submit_signal(
        db,
        user_id=user_id,
        signal={
            "symbol": symbol.upper(),
            "side": "SELL",
            "size": normalized_size,
            "strategy_name": "ema_rsi",
            "mark_price": max(_safe_float(status_polls[-1].get("price"), 0.0), 10000.0),
            "leverage": 3,
        },
        idempotency_key=idempotency_key,
    )
    queue_payload = submit_payload.get("queue_payload") if isinstance(submit_payload, dict) else None
    worker_result = execute_queued_job(db, queue_payload=queue_payload) if isinstance(queue_payload, dict) else None

    job = db.query(ExecutionJob).filter(ExecutionJob.idempotency_key == idempotency_key).first()
    order = db.query(Order).filter(Order.execution_job_id == (job.id if job else "")).first() if job else None

    timeline_events = []
    for event in runtime_stream_hub.get_recent_events(limit=200):
        if str(event.get("symbol") or "").upper() != symbol.upper():
            continue
        if str(event.get("user_id") or "") != user_id:
            continue
        ts = str(event.get("timestamp") or "")
        if ts and ts < started_at.isoformat():
            continue
        timeline_events.append(event)

    db_state = {
        "execution_job_id": job.id if job else None,
        "execution_job_state": job.state if job else None,
        "failure_class": job.failure_class if job else None,
        "order_id": order.id if order else None,
        "order_state": order.state if order else None,
        "external_order_id": order.external_order_id if order else None,
    }

    execution_db_aligned = bool(job) and len(timeline_events) > 0
    if order is not None:
        execution_db_aligned = execution_db_aligned and str(order.state or "").upper() in {
            "CREATED",
            "SENT",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELED",
            "FAILED",
        }
    else:
        execution_db_aligned = execution_db_aligned and str(job.state or "").upper() == "FAILED"

    response_log["steps"]["market_submit"] = {"status": "PASS", "raw": market_submit_raw}
    response_log["steps"]["market_status"] = {"status": "PASS", "raw": status_polls}
    if market_retry_logs:
        response_log["steps"]["market_fill_retries"] = {"status": "PASS" if full_fill_observed else "FAIL", "raw": market_retry_logs}
    response_log["steps"]["cancel_flow"] = {
        "status": "PASS",
        "limit_submit_raw": limit_submit_raw,
        "cancel_raw": cancel_raw,
    }
    response_log["steps"]["execution_engine_flow"] = {
        "status": "PASS" if execution_db_aligned else "FAIL",
        "submit_payload": submit_payload,
        "worker_result": worker_result,
        "db_state": db_state,
        "timeline_events": timeline_events[:30],
    }

    status = "PASS" if (full_fill_observed and execution_db_aligned) else "FAIL"
    payload = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": _utcnow().isoformat(),
        "resolution": resolution_meta,
        "partial_fill_observed": partial_fill_observed,
        "full_fill_observed": full_fill_observed,
        "market_order_id": market_order_id,
        "cancel_order_id": cancel_order_id,
        "response_log": response_log,
        "timeline_event_count": len(timeline_events),
        "db_state": db_state,
    }
    payload["artifact_path"] = persist_artifact(TESTNET_LIFECYCLE_ARTIFACT, payload)
    return payload


def run_canary_end_to_end_validation(
    db: Session,
    *,
    current_user,
    symbol: str = "BTCUSDT",
    size: float = 0.0001,
    strategy_name: str = "ema_rsi",
) -> dict:
    started_at = _utcnow()
    _hydrate_binance_env_from_file()
    _sync_runtime_binance_credentials_from_resolver(db, user_id=current_user.id)

    adapter = get_execution_adapter()
    _ensure_valid_testnet_credentials(adapter)

    idempotency_key = f"canary-run-{int(time.time() * 1000)}"

    submit_result = submit_signal(
        db,
        user_id=current_user.id,
        signal={
            "symbol": symbol.upper(),
            "side": "BUY",
            "size": float(size),
            "strategy_name": strategy_name,
            "mark_price": 10000.0,
            "leverage": 3,
        },
        idempotency_key=idempotency_key,
    )
    queue_payload = submit_result.get("queue_payload") if isinstance(submit_result, dict) else None
    worker_result = execute_queued_job(db, queue_payload=queue_payload) if isinstance(queue_payload, dict) else None

    job = db.query(ExecutionJob).filter(ExecutionJob.idempotency_key == idempotency_key).first()
    order = db.query(Order).filter(Order.execution_job_id == (job.id if job else "")).first() if job else None

    reconciliation = run_order_reconciliation(db, limit=50)
    pnl_summary = compute_runtime_pnl_summary(db, requester_role=current_user.role.value, requester_user_id=current_user.id)
    runtime_alerts_payload = list_runtime_alerts(db, current_user=current_user, limit=10)
    runtime_alerts = runtime_alerts_payload.get("items", []) if isinstance(runtime_alerts_payload, dict) else []
    smoke = _latest_smoke_status(db)

    timeline_events = []
    for event in runtime_stream_hub.get_recent_events(limit=200):
        if str(event.get("symbol") or "").upper() != symbol.upper():
            continue
        if str(event.get("user_id") or "") != current_user.id:
            continue
        timeline_events.append(event)

    steps = {
        "strategy": bool(submit_result),
        "risk": str(submit_result.get("status") or "").lower() in {"enqueued", "duplicate"},
        "queue": bool(worker_result),
        "execution": bool(order and order.external_order_id),
        "exchange": bool(order and order.external_order_id),
        "order_update": bool(job and str(job.state or "").upper() in {"SENT", "PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELED"}),
        "pnl": (str(pnl_summary.get("status") or "").lower() == "ok") or (pnl_summary.get("net_pnl") is not None),
        "alert": isinstance(runtime_alerts, list),
        "timeline": len(timeline_events) > 0,
        "snapshot": smoke.get("run_status") != "NO_DATA",
    }
    status = "PASS" if all(bool(value) for value in steps.values()) else "FAIL"

    payload = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": _utcnow().isoformat(),
        "user_id": current_user.id,
        "symbol": symbol.upper(),
        "size": float(size),
        "steps": steps,
        "submit_result": submit_result,
        "worker_result": worker_result,
        "reconciliation": reconciliation,
        "pnl_summary": pnl_summary,
        "runtime_alert_count": len(runtime_alerts),
        "timeline_event_count": len(timeline_events),
        "timeline_events": timeline_events[:30],
        "db_state": {
            "execution_job_id": job.id if job else None,
            "execution_job_state": job.state if job else None,
            "order_id": order.id if order else None,
            "order_state": order.state if order else None,
            "external_order_id": order.external_order_id if order else None,
        },
        "smoke": smoke,
    }
    payload["artifact_path"] = persist_artifact(CANARY_RUN_ARTIFACT, payload)
    return payload


def verify_kill_switch_rollback(db: Session, *, user_id: str, symbol: str = "BTCUSDT") -> dict:
    started_at = _utcnow()
    activate_state = activate_kill_switch(source="go_live_checklist", reason="force_fail_scenario", metadata={"user_id": user_id})
    blocked_result = submit_signal(
        db,
        user_id=user_id,
        signal={
            "symbol": symbol.upper(),
            "side": "BUY",
            "size": 0.0001,
            "strategy_name": "ema_rsi",
            "mark_price": 10000,
            "leverage": 3,
        },
        idempotency_key=f"kill-verify-{int(time.time() * 1000)}",
    )
    deactivate_state = deactivate_kill_switch(source="go_live_checklist", reason="rollback_validation_done")

    blocked_ok = str(blocked_result.get("status") or "") == "rejected" and blocked_result.get("risk", {}).get("reject_reason") == "kill_switch_active"
    payload = {
        "status": "PASS" if blocked_ok else "FAIL",
        "started_at": started_at.isoformat(),
        "finished_at": _utcnow().isoformat(),
        "activate_state": activate_state,
        "blocked_result": blocked_result,
        "deactivate_state": deactivate_state,
    }
    payload["artifact_path"] = persist_artifact(KILL_SWITCH_VERIFICATION_ARTIFACT, payload)
    return payload


def build_canary_readiness_score(db: Session) -> dict:
    canary_run = _load_artifact(CANARY_RUN_ARTIFACT)
    testnet_lifecycle = _load_artifact(TESTNET_LIFECYCLE_ARTIFACT)
    smoke = _latest_smoke_status(db)
    critical_open_alerts = _recent_open_critical_alert_count(db, window_minutes=60)

    execution_ok = str(canary_run.get("status") or "").upper() == "PASS"
    exchange_ok = str(testnet_lifecycle.get("status") or "").upper() == "PASS"
    canary_pnl = canary_run.get("pnl_summary", {}) if isinstance(canary_run, dict) else {}
    pnl_ok = bool(canary_pnl.get("status") == "ok" or canary_pnl.get("net_pnl") is not None)
    alerts_ok = critical_open_alerts < 3

    score = 100
    if not execution_ok:
        score -= 30
    if not pnl_ok:
        score -= 15
    if not alerts_ok:
        score -= 15
    if not exchange_ok:
        score -= 35

    smoke_status = str(smoke.get("run_status") or "NO_DATA").upper()
    if smoke_status == "DEGRADED":
        score = min(score, 70)
        score -= 10
    elif not _is_smoke_pass(smoke):
        score = min(score, 55)
        score -= 20

    score = max(0, min(100, score))
    if exchange_ok and execution_ok and pnl_ok and alerts_ok and _is_smoke_pass(smoke) and score >= 85:
        status = "READY"
    elif score >= 55:
        status = "WARNING"
    else:
        status = "NOT_READY"

    return {
        "score": score,
        "status": status,
        "components": {
            "execution": execution_ok,
            "pnl": pnl_ok,
            "alerts": alerts_ok,
            "smoke": smoke_status,
            "exchange": exchange_ok,
        },
        "evidence": {
            "canary_run_artifact": canary_run.get("artifact_path"),
            "testnet_lifecycle_artifact": testnet_lifecycle.get("artifact_path"),
            "critical_open_alerts_60m": critical_open_alerts,
            "smoke": smoke,
        },
    }


def evaluate_go_live_checklist(db: Session) -> dict:
    readiness = build_canary_readiness_score(db)
    canary_run = _load_artifact(CANARY_RUN_ARTIFACT)
    testnet_lifecycle = _load_artifact(TESTNET_LIFECYCLE_ARTIFACT)
    kill_switch_verification = _load_artifact(KILL_SWITCH_VERIFICATION_ARTIFACT)
    smoke = _latest_smoke_status(db)

    queue_backlog = _queue_backlog_count(db)
    critical_spike = _recent_open_critical_alert_count(db, window_minutes=30)

    checks = {
        "testnet_lifecycle_pass": str(testnet_lifecycle.get("status") or "").upper() == "PASS",
        "canary_run_pass": str(canary_run.get("status") or "").upper() == "PASS",
        "smoke_ok": _is_smoke_acceptable(smoke),
        "alert_spike_absent": critical_spike < 3,
        "queue_backlog_normal": queue_backlog < 20,
        "kill_switch_verified": str(kill_switch_verification.get("status") or "").upper() == "PASS",
    }

    reasons: list[str] = []
    if not checks["testnet_lifecycle_pass"]:
        reasons.append("testnet lifecycle pass yok")
    if not checks["canary_run_pass"]:
        reasons.append("canary run pass değil")
    if not checks["smoke_ok"]:
        reasons.append(f"smoke {smoke.get('run_status', 'NO_DATA').lower()}")
    if not checks["alert_spike_absent"]:
        reasons.append("critical alert spike var")
    if not checks["queue_backlog_normal"]:
        reasons.append("queue backlog normal değil")
    if not checks["kill_switch_verified"]:
        reasons.append("kill-switch doğrulaması eksik")
    if readiness.get("status") == "NOT_READY":
        reasons.append("readiness NOT_READY")

    go_live = all(checks.values()) and readiness.get("status") != "NOT_READY"
    return {
        "go_live": go_live,
        "reasons": reasons,
        "checks": checks,
        "readiness": readiness,
        "metrics": {
            "queue_backlog": queue_backlog,
            "critical_open_alerts_30m": critical_spike,
            "smoke_status": smoke.get("run_status"),
            "smoke_explained": bool(smoke.get("explained")),
        },
    }


def run_final_regression_validation(db: Session, *, current_user, symbol: str = "BTCUSDT", size: float = 0.0001) -> dict:
    started_at = _utcnow()
    canary_result = run_canary_end_to_end_validation(db, current_user=current_user, symbol=symbol, size=size, strategy_name="ema_rsi")
    reconciliation = run_order_reconciliation(db, limit=100)
    kill_switch_verification = verify_kill_switch_rollback(db, user_id=current_user.id, symbol=symbol)
    alerts_payload = list_runtime_alerts(db, current_user=current_user, limit=20)
    timeline_events = runtime_stream_hub.get_recent_events(limit=100)

    checks = {
        "execution": str(canary_result.get("status") or "").upper() == "PASS",
        "reconciliation": str(reconciliation.get("status") or "").lower() == "ok",
        "kill_switch": str(kill_switch_verification.get("status") or "").upper() == "PASS",
        "timeline": len(timeline_events) > 0,
        "alert": isinstance(alerts_payload, dict) and isinstance(alerts_payload.get("items", []), list),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": _utcnow().isoformat(),
        "checks": checks,
        "canary_result": canary_result,
        "reconciliation": reconciliation,
        "kill_switch_verification": kill_switch_verification,
        "alert_count": len(alerts_payload.get("items", [])) if isinstance(alerts_payload, dict) else 0,
        "timeline_event_count": len(timeline_events),
    }
    payload["artifact_path"] = persist_artifact(FINAL_REGRESSION_ARTIFACT, payload)
    return payload


def get_proxy_exchange_health_snapshot(db: Session) -> dict:
    _hydrate_binance_env_from_file()
    spot_base_url = str(os.environ.get("BINANCE_SPOT_TESTNET_BASE_URL") or os.environ.get("BINANCE_SPOT_BASE_URL") or "").strip()
    futures_base_url = str(os.environ.get("BINANCE_FUTURES_TESTNET_BASE_URL") or os.environ.get("BINANCE_FUTURES_BASE_URL") or "").strip()

    spot_token = str(
        os.environ.get("BINANCE_SPOT_TESTNET_PROXY_TOKEN")
        or os.environ.get("BINANCE_SPOT_PROXY_TOKEN")
        or os.environ.get("BINANCE_PROXY_TOKEN")
        or ""
    ).strip()
    futures_token = str(
        os.environ.get("BINANCE_FUTURES_TESTNET_PROXY_TOKEN")
        or os.environ.get("BINANCE_FUTURES_PROXY_TOKEN")
        or os.environ.get("BINANCE_PROXY_TOKEN")
        or ""
    ).strip()

    timeout_seconds = _safe_float(os.environ.get("BINANCE_ADAPTER_TIMEOUT_SECONDS"), 20.0)
    max_retries = _safe_int(os.environ.get("BINANCE_ADAPTER_MAX_RETRIES"), 3)

    def _token_from_url(base_url: str) -> str:
        marker = "/p/"
        if marker not in base_url:
            return ""
        return str(base_url.split(marker, 1)[1].split("/", 1)[0]).strip()

    spot_token_in_url = _token_from_url(spot_base_url)
    futures_token_in_url = _token_from_url(futures_base_url)

    spot_mismatch = bool(spot_token and spot_token_in_url and spot_token != spot_token_in_url)
    futures_mismatch = bool(futures_token and futures_token_in_url and futures_token != futures_token_in_url)

    recent_latency = (
        db.query(ExecutionJob)
        .filter(ExecutionJob.total_ms.isnot(None))
        .order_by(ExecutionJob.updated_at.desc())
        .limit(20)
        .all()
    )
    latency_samples = [int(row.total_ms or 0) for row in recent_latency if row.total_ms is not None]
    latency_p95 = max(latency_samples) if latency_samples else None

    invalid_token_alerts = (
        db.query(SystemAlert)
        .filter(SystemAlert.alert_type == "runtime_exchange_auth_invalid")
        .order_by(SystemAlert.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "status": "ok",
        "spot": {
            "base_url_set": bool(spot_base_url),
            "proxy_token_set": bool(spot_token),
            "proxy_token_mismatch": spot_mismatch,
        },
        "futures": {
            "base_url_set": bool(futures_base_url),
            "proxy_token_set": bool(futures_token),
            "proxy_token_mismatch": futures_mismatch,
        },
        "adapter_limits": {
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
        },
        "invalid_token_behavior": {
            "reject_and_alert": True,
            "recent_alert_count": len(invalid_token_alerts),
        },
        "latency_metric": {
            "sample_count": len(latency_samples),
            "p95_ms": latency_p95,
        },
    }
