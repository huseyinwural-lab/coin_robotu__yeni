import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.go_live_checklist import (
    build_canary_readiness_score,
    evaluate_go_live_checklist,
    get_go_live_wizard_state,
    get_proxy_exchange_health_snapshot,
    run_canary_end_to_end_validation,
    run_final_regression_validation,
    run_single_flow_dry_run,
    run_testnet_lifecycle_validation,
    verify_kill_switch_rollback,
    wizard_arm_live,
    wizard_confirm_live,
    wizard_rollback_live,
    wizard_run_canary_check,
    wizard_run_readiness_check,
)
from core.pnl_engine import compute_runtime_pnl_positions, compute_runtime_pnl_summary
from core.reconciliation.order_reconciliation import run_order_reconciliation
from core.runtime_stream import runtime_stream_hub
from core.safety.kill_switch import activate_kill_switch, deactivate_kill_switch, get_kill_switch_state
from core.exchanges import get_execution_adapter
from core.execution_engine import consume_execution_queue_once, submit_signal
from core.strategy_engine import generate_strategy_signal
from db import get_db
from deps import get_current_user, require_admin
from models import ExecutionJob, Order, RuntimeSmokeRun, User
from services.runtime_alert_triage_service import apply_alert_action, list_runtime_alerts


router = APIRouter(prefix="/runtime", tags=["runtime_execution"])


class StrategySignalRequest(BaseModel):
    symbol: str
    closes: list[float] = Field(min_length=30)
    strategy_name: str = "ema_rsi"


class ExecutionSubmitRequest(BaseModel):
    symbol: str
    side: str
    size: float = Field(gt=0)
    confidence: float = 0.0
    strategy_name: str = "ema_rsi"
    timestamp: str | None = None
    mark_price: float = Field(default=1.0, gt=0)
    leverage: int = Field(default=1, ge=1)
    idempotency_key: str | None = None


class AlertMuteRequest(BaseModel):
    minutes: int = Field(default=15, ge=1, le=24 * 60)
    note: str | None = None


class AlertNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class KillSwitchActionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CancelOrderRequest(BaseModel):
    symbol: str
    order_id: str


class CanaryRunRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=24)
    size: float = Field(default=0.0001, gt=0)
    strategy_name: str = Field(default="ema_rsi", min_length=1, max_length=80)


class TestnetLifecycleRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=24)
    size: float = Field(default=0.0001, gt=0)


class KillSwitchVerifyRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=24)


class DryRunRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=3, max_length=24)
    size: float = Field(default=0.0001, gt=0)


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if str(current_user.role.value) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_required")
    return current_user


@router.post("/strategy/signal")
def produce_strategy_signal(payload: StrategySignalRequest, _: User = Depends(require_admin)):
    signal = generate_strategy_signal(
        symbol=payload.symbol,
        closes=payload.closes,
        strategy_name=payload.strategy_name,
    )
    if signal is None:
        return {"status": "no_signal", "signal": None}
    return {"status": "ok", "signal": signal}


@router.post("/execution/submit")
def submit_execution(payload: ExecutionSubmitRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = submit_signal(
            db,
            user_id=current_user.id,
            signal={
                "symbol": payload.symbol,
                "side": payload.side,
                "size": payload.size,
                "confidence": payload.confidence,
                "strategy_name": payload.strategy_name,
                "timestamp": payload.timestamp,
                "mark_price": payload.mark_price,
                "leverage": payload.leverage,
            },
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


@router.post("/execution/worker/process-once")
def process_execution_queue_once(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = consume_execution_queue_once(db)
    return result or {"status": "queue_empty"}


@router.get("/execution/jobs/{execution_job_id}")
def get_execution_job(execution_job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(ExecutionJob).filter(ExecutionJob.id == execution_job_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="execution_job_not_found")
    if current_user.role.value == "user" and row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return {
        "id": row.id,
        "idempotency_key": row.idempotency_key,
        "state": row.state,
        "symbol": row.symbol,
        "side": row.side,
        "size": row.size,
        "strategy_name": row.strategy_name,
        "reject_reason": row.reject_reason,
        "fail_reason": row.fail_reason,
        "queue_wait_ms": row.queue_wait_ms,
        "execution_ms": row.execution_ms,
        "total_ms": row.total_ms,
        "failure_class": row.failure_class,
        "retry_count": row.retry_count,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_state_transition_at": row.last_state_transition_at.isoformat() if row.last_state_transition_at else None,
    }


@router.get("/execution/orders/{order_id}")
def get_order(order_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(Order).filter(Order.id == order_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order_not_found")
    if current_user.role.value == "user" and row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return {
        "id": row.id,
        "execution_job_id": row.execution_job_id,
        "symbol": row.symbol,
        "side": row.side,
        "size": row.size,
        "state": row.state,
        "external_order_id": row.external_order_id,
        "filled_size": row.filled_size,
        "avg_fill_price": row.avg_fill_price,
        "reject_reason": row.reject_reason,
        "fail_reason": row.fail_reason,
        "last_state_transition_at": row.last_state_transition_at.isoformat() if row.last_state_transition_at else None,
    }


@router.get("/pnl/positions")
def get_runtime_pnl_positions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    is_admin = current_user.role.value in {"super_admin", "admin", "ops"}
    rows = compute_runtime_pnl_positions(db, user_id=None if is_admin else current_user.id)
    return {
        "status": "ok",
        "scope": "admin_all" if is_admin else "user_self",
        "rows": rows,
    }


@router.get("/pnl/summary")
def get_runtime_pnl_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_runtime_pnl_summary(
        db,
        requester_role=current_user.role.value,
        requester_user_id=current_user.id,
    )


@router.get("/alerts")
def get_runtime_alerts(
    limit: int = 20,
    severity: str | None = None,
    state: str | None = None,
    symbol: str | None = None,
    user_id: str | None = None,
    window_minutes: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_runtime_alerts(
        db,
        current_user=current_user,
        limit=limit,
        severity=severity,
        state=state,
        symbol=symbol,
        user_id=user_id,
        window_minutes=window_minutes,
    )


@router.post("/alerts/{alert_id}/ack")
def ack_runtime_alert(alert_id: str, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return apply_alert_action(db, current_user=current_user, alert_id=alert_id, action_type="acknowledge")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/alerts/{alert_id}/mute")
def mute_runtime_alert(
    alert_id: str,
    payload: AlertMuteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return apply_alert_action(
            db,
            current_user=current_user,
            alert_id=alert_id,
            action_type="mute_temporarily",
            note=payload.note,
            mute_minutes=payload.minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/alerts/{alert_id}/resolve")
def resolve_runtime_alert(
    alert_id: str,
    payload: AlertNoteRequest | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return apply_alert_action(
            db,
            current_user=current_user,
            alert_id=alert_id,
            action_type="resolve",
            note=payload.note if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/alerts/{alert_id}/escalate")
def escalate_runtime_alert(
    alert_id: str,
    payload: AlertNoteRequest | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return apply_alert_action(
            db,
            current_user=current_user,
            alert_id=alert_id,
            action_type="escalate",
            note=payload.note if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/alerts/{alert_id}/note")
def note_runtime_alert(
    alert_id: str,
    payload: AlertNoteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return apply_alert_action(
            db,
            current_user=current_user,
            alert_id=alert_id,
            action_type="attach_note",
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/health/smoke")
def get_runtime_smoke_health(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role.value not in {"super_admin", "admin", "ops"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    row = db.query(RuntimeSmokeRun).order_by(RuntimeSmokeRun.created_at.desc()).first()
    if row is None:
        return {"status": "no_data"}

    return {
        "status": "ok",
        "smoke": {
            "id": row.id,
            "run_status": row.status,
            "summary": row.summary,
            "steps": row.steps,
            "trigger_source": row.trigger_source,
            "report_path": row.report_path,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        },
    }


@router.get("/timeline/events")
def get_runtime_timeline_events(limit: int = 50, current_user: User = Depends(require_admin)):
    return {
        "status": "ok",
        "items": runtime_stream_hub.get_recent_events(limit=max(1, min(limit, 200))),
        "requested_by": current_user.id,
    }


@router.get("/safety/kill-switch")
def get_kill_switch(current_user: User = Depends(require_admin)):
    return {"status": "ok", "kill_switch": get_kill_switch_state(), "requested_by": current_user.id}


@router.post("/safety/kill-switch/activate")
def activate_kill_switch_endpoint(
    payload: KillSwitchActionRequest,
    current_user: User = Depends(require_admin),
):
    state = activate_kill_switch(
        source="manual",
        reason=payload.reason,
        metadata={"actor_user_id": current_user.id},
    )
    return {"status": "ok", "kill_switch": state}


@router.post("/safety/kill-switch/deactivate")
def deactivate_kill_switch_endpoint(
    payload: KillSwitchActionRequest,
    current_user: User = Depends(require_admin),
):
    state = deactivate_kill_switch(source="manual", reason=payload.reason)
    return {"status": "ok", "kill_switch": state}


@router.post("/reconciliation/orders/run")
def run_order_reconciliation_endpoint(
    limit: int = 100,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = run_order_reconciliation(db, limit=limit)
    return {"status": "ok", "requested_by": current_user.id, "result": result}


@router.get("/exchange/order-status")
def get_exchange_order_status(
    symbol: str,
    order_id: str,
    current_user: User = Depends(require_admin),
):
    adapter = get_execution_adapter()
    return {
        "status": "ok",
        "requested_by": current_user.id,
        "result": adapter.get_order_status(symbol=symbol, order_id=order_id),
    }


@router.post("/exchange/cancel-order")
def cancel_exchange_order(
    payload: CancelOrderRequest,
    current_user: User = Depends(require_admin),
):
    adapter = get_execution_adapter()
    return {
        "status": "ok",
        "requested_by": current_user.id,
        "result": adapter.cancel_order(symbol=payload.symbol, order_id=payload.order_id),
    }


@router.post("/exchange/testnet-lifecycle/run")
def run_testnet_lifecycle_endpoint(
    payload: TestnetLifecycleRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        result = run_testnet_lifecycle_validation(
            db,
            user_id=current_user.id,
            symbol=payload.symbol,
            size=payload.size,
        )
        if str(result.get("status") or "").upper() != "PASS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
        return {"status": "ok", "requested_by": current_user.id, "result": result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/canary/run")
def run_canary_endpoint(
    payload: CanaryRunRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        result = run_canary_end_to_end_validation(
            db,
            current_user=current_user,
            symbol=payload.symbol,
            size=payload.size,
            strategy_name=payload.strategy_name,
        )
        if str(result.get("status") or "").upper() != "PASS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
        return {"status": "ok", "requested_by": current_user.id, "result": result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/regression/final-run")
def run_final_regression_endpoint(
    payload: CanaryRunRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        result = run_final_regression_validation(
            db,
            current_user=current_user,
            symbol=payload.symbol,
            size=payload.size,
        )
        if str(result.get("status") or "").upper() != "PASS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
        return {"status": "ok", "requested_by": current_user.id, "result": result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/go-live/dry-run/run")
def run_go_live_dry_run_endpoint(
    payload: DryRunRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        result = run_single_flow_dry_run(db, current_user=current_user, symbol=payload.symbol, size=payload.size)
        if str(result.get("status") or "").upper() != "PASS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
        return {"status": "ok", "requested_by": current_user.id, "result": result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/canary/readiness-score")
def get_canary_readiness_score(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {
        "status": "ok",
        "requested_by": current_user.id,
        "result": build_canary_readiness_score(db),
    }


@router.get("/go-live/checklist")
def get_go_live_checklist(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {
        "status": "ok",
        "requested_by": current_user.id,
        "result": evaluate_go_live_checklist(db),
    }


@router.get("/exchange/proxy-health")
def get_exchange_proxy_health(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {
        "status": "ok",
        "requested_by": current_user.id,
        "result": get_proxy_exchange_health_snapshot(db),
    }


@router.get("/go-live/wizard/state")
def get_go_live_wizard_state_endpoint(current_user: User = Depends(require_admin)):
    return {"status": "ok", "requested_by": current_user.id, "result": get_go_live_wizard_state()}


@router.post("/go-live/wizard/readiness-check")
def run_go_live_wizard_readiness_step(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return {"status": "ok", "requested_by": current_user.id, "result": wizard_run_readiness_check(db)}


@router.post("/go-live/wizard/canary-check")
def run_go_live_wizard_canary_step(
    payload: DryRunRequest,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return {
        "status": "ok",
        "requested_by": current_user.id,
        "result": wizard_run_canary_check(db, current_user=current_user, symbol=payload.symbol, size=payload.size),
    }


@router.post("/go-live/wizard/arm")
def run_go_live_wizard_arm(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return {"status": "ok", "requested_by": current_user.id, "result": wizard_arm_live(db)}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/go-live/wizard/confirm")
def run_go_live_wizard_confirm(current_user: User = Depends(require_super_admin)):
    try:
        return {"status": "ok", "requested_by": current_user.id, "result": wizard_confirm_live()}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/go-live/wizard/rollback")
def run_go_live_wizard_rollback(current_user: User = Depends(require_super_admin)):
    return {"status": "ok", "requested_by": current_user.id, "result": wizard_rollback_live()}


@router.post("/safety/kill-switch/verify-rollback")
def verify_kill_switch_rollback_endpoint(
    payload: KillSwitchVerifyRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        result = verify_kill_switch_rollback(db, user_id=current_user.id, symbol=payload.symbol)
        if str(result.get("status") or "").upper() != "PASS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
        return {"status": "ok", "requested_by": current_user.id, "result": result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/execution/mode")
def get_execution_mode(current_user: User = Depends(require_admin)):
    alias_to_mode = {
        "mock": "sim",
        "paper": "testnet",
        "live": "live",
        "sim": "sim",
        "testnet": "testnet",
    }
    compatibility_alias = {
        "sim": "MOCK",
        "testnet": "PAPER",
        "live": "LIVE",
    }
    raw_mode = str(os.environ.get("EXECUTION_MODE") or "sim").strip().lower()
    mode = alias_to_mode.get(raw_mode, raw_mode)
    return {
        "status": "ok",
        "requested_by": current_user.id,
        "mode": mode,
        "compatibility_alias": compatibility_alias.get(mode, "MOCK"),
        "compatibility_notice": "legacy PAPER/MOCK aliases will be removed after one sprint",
        "flags": {
            "LIVE_TRADING_ENABLED": str(os.environ.get("LIVE_TRADING_ENABLED") or "false"),
            "TESTNET_TRADING_ENABLED": str(os.environ.get("TESTNET_TRADING_ENABLED") or "false"),
            "LIVE_ROUTE_APPROVED": str(os.environ.get("LIVE_ROUTE_APPROVED") or "false"),
            "CANARY_MODE": str(os.environ.get("CANARY_MODE") or "false"),
            "CANARY_MAX_NOTIONAL": str(os.environ.get("CANARY_MAX_NOTIONAL") or "100"),
            "CANARY_ALLOWED_STRATEGIES": str(os.environ.get("CANARY_ALLOWED_STRATEGIES") or "ema_rsi"),
            "CANARY_ALLOWED_USER_IDS": str(os.environ.get("CANARY_ALLOWED_USER_IDS") or ""),
        },
    }
