import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin, require_super_admin
from models import AuditLog, StrategyObservabilityEvent, User
from services.audit_service import create_audit_log
from services.strategy_observability_service import (
    get_rejection_analytics,
    get_score_metrics,
    get_strategy_observability_report,
    get_top_signals,
    parse_window_to_since,
)

router = APIRouter(prefix="/admin/strategy", tags=["admin_strategy_observability"])

PREVIEW_TOKEN_TTL_SECONDS = 600
PREVIEW_TOKEN_KEY_PREFIX = "strategy:signal_preview"
SCORE_CONFIG_KEY = "strategy:score_config:v1"
SCORE_OVERRIDE_LOG_KEY = "strategy:score_override_logs:v1"


class TopSignalsSimulateRequest(BaseModel):
    signal_ids: list[str] = Field(..., min_length=1, max_length=50)


class TopSignalsExecuteRequest(BaseModel):
    signal_ids: list[str] = Field(..., min_length=1, max_length=50)
    preview_token: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


class TopSignalsBulkSimulateRequest(BaseModel):
    window: str = "24h"
    top_n: int = Field(default=10, ge=1, le=50)


class TopSignalsBulkExecuteRequest(BaseModel):
    mode: Literal["preview", "confirm"] = "preview"
    window: str = "24h"
    top_n: int = Field(default=10, ge=1, le=50)
    preview_token: str | None = None
    confirm: bool = False
    reason: str | None = None


class ScoreConfigUpdateRequest(BaseModel):
    threshold: float = Field(..., ge=0, le=1)
    factor_weights: dict[str, float] = Field(default_factory=dict)
    per_strategy: dict[str, dict] = Field(default_factory=dict)
    reason: str = Field(..., min_length=3)


class ScoreOverrideRequest(BaseModel):
    signal_id: str
    override_delta: float = Field(..., ge=-1.0, le=1.0)
    reason: str = Field(..., min_length=3)


class ScorePreviewRequest(BaseModel):
    threshold: float = Field(..., ge=0, le=1)
    factor_weights: dict[str, float] = Field(default_factory=dict)
    strategy_id: str | None = None
    top_n: int = Field(default=20, ge=1, le=50)


class ScoreAutoTuningToggleRequest(BaseModel):
    enabled: bool
    reason: str = Field(..., min_length=3)


def _role_value(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


def _signal_to_dict(row: StrategyObservabilityEvent) -> dict:
    return {
        "signal_id": row.id,
        "symbol": row.symbol,
        "strategy_id": row.strategy_id,
        "market_regime": row.market_regime,
        "event_type": row.event_type,
        "base_score": row.base_score,
        "adjusted_score": row.adjusted_score,
        "score_delta": row.score_delta,
        "selection_rank": row.selection_rank,
        "trend_strength": row.trend_strength,
        "relative_volume": row.relative_volume,
        "hard_gate_pass": row.hard_gate_pass,
        "rejection_reason": row.rejection_reason,
        "reject_reasons": row.reject_reasons or [],
        "decision_path": row.decision_path or [],
        "event_metadata": row.event_metadata or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _default_score_config() -> dict:
    return {
        "threshold": 0.65,
        "factor_weights": {
            "base_score": 0.55,
            "trend_strength": 0.25,
            "relative_volume": 0.20,
        },
        "per_strategy": {},
        "auto_tuning_enabled": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_score_config() -> dict:
    raw = redis_client.get(SCORE_CONFIG_KEY)
    if not raw:
        return _default_score_config()
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return _default_score_config()
        return parsed
    except Exception:
        return _default_score_config()


def _save_score_config(config: dict) -> None:
    redis_client.set(SCORE_CONFIG_KEY, json.dumps(config, ensure_ascii=False))


def _save_preview_token(payload: dict) -> str:
    token = str(uuid.uuid4())
    key = f"{PREVIEW_TOKEN_KEY_PREFIX}:{token}"
    redis_client.set(key, json.dumps(payload, ensure_ascii=False))
    redis_client.expire(key, PREVIEW_TOKEN_TTL_SECONDS)
    return token


def _read_preview_token(token: str) -> dict | None:
    key = f"{PREVIEW_TOKEN_KEY_PREFIX}:{token}"
    raw = redis_client.get(key)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return None


def _fetch_signals_by_ids(db: Session, signal_ids: list[str]) -> list[StrategyObservabilityEvent]:
    return db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id.in_(signal_ids)).all()


def _build_simulation_items(rows: list[StrategyObservabilityEvent], score_config: dict) -> list[dict]:
    threshold = float(score_config.get("threshold", 0.65))
    items = []
    for row in rows:
        adjusted = float(row.adjusted_score or 0)
        items.append(
            {
                "signal_id": row.id,
                "symbol": row.symbol,
                "strategy_id": row.strategy_id,
                "adjusted_score": adjusted,
                "threshold": threshold,
                "simulation_result": "PASS" if adjusted >= threshold else "REJECT",
                "risk_note": "threshold_check",
            }
        )
    return items


@router.get("/top-signals")
def top_signals(
    window: str = Query(default="24h"),
    top_n: int = Query(default=10, ge=1, le=50),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_top_signals(db, window=window, top_n=top_n)


@router.post("/top-signals/simulate")
def simulate_top_signals(
    payload: TopSignalsSimulateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = _fetch_signals_by_ids(db, payload.signal_ids)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signals_not_found")

    simulation_items = _build_simulation_items(rows, _load_score_config())
    preview_payload = {
        "type": "selected_simulation",
        "signal_ids": sorted([row.id for row in rows]),
        "actor_id": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = _save_preview_token(preview_payload)
    create_audit_log(
        db,
        action="strategy_top_signals_simulate",
        entity_type="strategy_signal",
        entity_id=preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "signal_ids": preview_payload["signal_ids"],
            "preview_token": preview_token,
        },
    )
    db.commit()
    return {
        "status": "success",
        "message": "simulation_completed",
        "preview_token": preview_token,
        "items": simulation_items,
    }


@router.post("/top-signals/execute")
def execute_top_signals(
    payload: TopSignalsExecuteRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    preview = _read_preview_token(payload.preview_token)
    if not preview:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_invalid_or_expired")
    if sorted(payload.signal_ids) != sorted(preview.get("signal_ids", [])):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_signal_mismatch")

    rows = _fetch_signals_by_ids(db, payload.signal_ids)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signals_not_found")

    executed_items = []
    for row in rows:
        metadata = dict(row.event_metadata or {})
        metadata["last_execution_action"] = "executed"
        metadata["last_execution_reason"] = payload.reason
        row.event_metadata = metadata
        executed_items.append({"signal_id": row.id, "symbol": row.symbol, "status": "EXECUTED"})

    create_audit_log(
        db,
        action="strategy_top_signals_execute",
        entity_type="strategy_signal",
        entity_id=payload.preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        reason=payload.reason,
        details={
            "signal_ids": sorted(payload.signal_ids),
            "preview_token": payload.preview_token,
            "simulation_before_execution": True,
        },
    )
    db.commit()
    return {
        "status": "success",
        "message": "execute_completed",
        "executed_count": len(executed_items),
        "items": executed_items,
    }


@router.post("/top-signals/bulk-simulate")
def bulk_simulate_top_signals(
    payload: TopSignalsBulkSimulateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    top_payload = get_top_signals(db, window=payload.window, top_n=payload.top_n)
    signal_ids = [item["signal_id"] for item in top_payload.get("items", []) if item.get("signal_id")]
    if not signal_ids:
        return {"status": "success", "message": "no_signals", "preview_token": None, "items": []}

    rows = _fetch_signals_by_ids(db, signal_ids)
    simulation_items = _build_simulation_items(rows, _load_score_config())
    preview_payload = {
        "type": "bulk_simulation",
        "signal_ids": sorted(signal_ids),
        "actor_id": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = _save_preview_token(preview_payload)
    create_audit_log(
        db,
        action="strategy_top_signals_bulk_simulate",
        entity_type="strategy_signal",
        entity_id=preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={"window": payload.window, "top_n": payload.top_n, "signal_ids": preview_payload["signal_ids"]},
    )
    db.commit()
    return {
        "status": "success",
        "message": "bulk_simulation_completed",
        "preview_token": preview_token,
        "items": simulation_items,
    }


@router.post("/top-signals/bulk-execute")
def bulk_execute_top_signals(
    payload: TopSignalsBulkExecuteRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if payload.mode == "preview":
        top_payload = get_top_signals(db, window=payload.window, top_n=payload.top_n)
        signal_ids = [item["signal_id"] for item in top_payload.get("items", []) if item.get("signal_id")]
        rows = _fetch_signals_by_ids(db, signal_ids)
        simulation_items = _build_simulation_items(rows, _load_score_config()) if rows else []
        preview_payload = {
            "type": "bulk_execute_preview",
            "signal_ids": sorted(signal_ids),
            "actor_id": current_admin.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        preview_token = _save_preview_token(preview_payload)
        create_audit_log(
            db,
            action="strategy_top_signals_bulk_execute_preview",
            entity_type="strategy_signal",
            entity_id=preview_token,
            actor_user_id=current_admin.id,
            actor_role=_role_value(current_admin),
            details={"window": payload.window, "top_n": payload.top_n, "signal_ids": preview_payload["signal_ids"]},
        )
        db.commit()
        return {
            "status": "success",
            "message": "bulk_execute_preview_ready",
            "preview_token": preview_token,
            "items": simulation_items,
        }

    if payload.mode != "confirm":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_mode")
    if not payload.preview_token:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_required")
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    if not (payload.reason and payload.reason.strip()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="reason_required")

    preview = _read_preview_token(payload.preview_token)
    if not preview:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_invalid_or_expired")
    signal_ids = sorted(preview.get("signal_ids", []))
    rows = _fetch_signals_by_ids(db, signal_ids)
    for row in rows:
        metadata = dict(row.event_metadata or {})
        metadata["last_execution_action"] = "bulk_executed"
        metadata["last_execution_reason"] = payload.reason
        row.event_metadata = metadata

    create_audit_log(
        db,
        action="strategy_top_signals_bulk_execute_confirm",
        entity_type="strategy_signal",
        entity_id=payload.preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        reason=payload.reason,
        details={"signal_ids": signal_ids, "simulation_before_execution": True},
    )
    db.commit()
    return {
        "status": "success",
        "message": "bulk_execute_completed",
        "executed_count": len(rows),
        "items": [{"signal_id": row.id, "symbol": row.symbol, "status": "EXECUTED"} for row in rows],
    }


@router.get("/score-config")
def get_score_config_endpoint(_: User = Depends(require_admin)):
    return {
        "status": "success",
        "config": _load_score_config(),
    }


@router.put("/score-config")
def update_score_config(
    payload: ScoreConfigUpdateRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    previous = _load_score_config()
    updated = {
        "threshold": payload.threshold,
        "factor_weights": payload.factor_weights,
        "per_strategy": payload.per_strategy,
        "auto_tuning_enabled": bool(previous.get("auto_tuning_enabled", False)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_score_config(updated)
    create_audit_log(
        db,
        action="strategy_score_config_apply",
        entity_type="strategy_score_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        reason=payload.reason,
        before_payload=previous,
        after_payload=updated,
        details={"reason": payload.reason},
    )
    db.commit()
    return {"status": "success", "message": "score_config_updated", "config": updated}


@router.post("/score-preview")
def score_preview(
    payload: ScorePreviewRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    current = _load_score_config()
    top_payload = get_top_signals(db, window="24h", top_n=payload.top_n)
    rows = _fetch_signals_by_ids(db, [item["signal_id"] for item in top_payload.get("items", []) if item.get("signal_id")])
    if payload.strategy_id:
        rows = [row for row in rows if row.strategy_id == payload.strategy_id]

    before_selected = 0
    after_selected = 0
    impact_rows = []
    factor_weights = payload.factor_weights or current.get("factor_weights", {})

    for row in rows:
        current_score = float(row.adjusted_score or 0)
        base = float(row.base_score or 0)
        trend = float(row.trend_strength or 0)
        rel_vol = float(row.relative_volume or 0)
        preview_score = (
            base * float(factor_weights.get("base_score", 0.55))
            + trend * float(factor_weights.get("trend_strength", 0.25))
            + rel_vol * float(factor_weights.get("relative_volume", 0.20))
        )
        if current_score >= float(current.get("threshold", 0.65)):
            before_selected += 1
        if preview_score >= payload.threshold:
            after_selected += 1
        if abs(preview_score - current_score) >= 0.03:
            impact_rows.append(
                {
                    "signal_id": row.id,
                    "symbol": row.symbol,
                    "current_score": round(current_score, 4),
                    "preview_score": round(preview_score, 4),
                    "delta": round(preview_score - current_score, 4),
                }
            )

    return {
        "status": "success",
        "message": "score_preview_ready",
        "state_snapshot": {
            "before_selected": before_selected,
            "after_selected": after_selected,
            "selected_delta": after_selected - before_selected,
            "impact_rows": impact_rows[:20],
        },
    }


@router.post("/score-override")
def score_override(
    payload: ScoreOverrideRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == payload.signal_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")

    before_adjusted = float(row.adjusted_score or 0)
    after_adjusted = min(max(before_adjusted + float(payload.override_delta), 0.0), 1.0)
    row.adjusted_score = after_adjusted
    row.score_delta = round(after_adjusted - float(row.base_score or 0), 6)

    override_record = {
        "signal_id": row.id,
        "symbol": row.symbol,
        "override_delta": float(payload.override_delta),
        "before_adjusted_score": before_adjusted,
        "after_adjusted_score": after_adjusted,
        "reason": payload.reason,
        "actor_id": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    redis_client.lpush(SCORE_OVERRIDE_LOG_KEY, json.dumps(override_record, ensure_ascii=False))
    redis_client.ltrim(SCORE_OVERRIDE_LOG_KEY, 0, 999)

    create_audit_log(
        db,
        action="strategy_score_override",
        entity_type="strategy_signal",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        reason=payload.reason,
        before_payload={"adjusted_score": before_adjusted},
        after_payload={"adjusted_score": after_adjusted},
        details=override_record,
    )
    db.commit()
    db.refresh(row)
    return {
        "status": "success",
        "message": "score_override_applied",
        "signal": _signal_to_dict(row),
    }


@router.post("/score-auto-tuning/toggle")
def toggle_score_auto_tuning(
    payload: ScoreAutoTuningToggleRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    current = _load_score_config()
    updated = dict(current)
    updated["auto_tuning_enabled"] = bool(payload.enabled)
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_score_config(updated)

    create_audit_log(
        db,
        action="strategy_score_auto_tuning_toggle",
        entity_type="strategy_score_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        reason=payload.reason,
        before_payload={"auto_tuning_enabled": current.get("auto_tuning_enabled", False)},
        after_payload={"auto_tuning_enabled": updated.get("auto_tuning_enabled", False)},
        details={"reason": payload.reason},
    )
    db.commit()
    return {"status": "success", "message": "auto_tuning_updated", "enabled": bool(payload.enabled)}


@router.get("/signals/{signal_id}/explainability")
def signal_explainability(signal_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == signal_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")

    score_config = _load_score_config()
    metadata = row.event_metadata or {}
    component_scores = metadata.get("component_scores") if isinstance(metadata.get("component_scores"), dict) else {}
    contribution_map = component_scores or {
        "base_score": float(row.base_score or 0),
        "trend_strength": float(row.trend_strength or 0),
        "relative_volume": float(row.relative_volume or 0),
        "score_delta": float(row.score_delta or 0),
    }

    override_history = []
    for item in redis_client.lrange(SCORE_OVERRIDE_LOG_KEY, 0, 200):
        parsed = json.loads(item.decode("utf-8") if isinstance(item, bytes) else item)
        if parsed.get("signal_id") == signal_id:
            override_history.append(parsed)

    timeline_rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == signal_id, AuditLog.action.like("strategy_%"))
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "status": "success",
        "signal": _signal_to_dict(row),
        "factor_weights": score_config.get("factor_weights", {}),
        "contribution_map": contribution_map,
        "triggered_rules": row.decision_path or [],
        "final_decision": row.event_type,
        "override_history": override_history,
        "decision_log": [
            {
                "audit_id": item.id,
                "action": item.action,
                "reason": item.reason,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "details": item.details or {},
            }
            for item in timeline_rows
        ],
    }


@router.get("/rejection-analytics")
def rejection_analytics(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_rejection_analytics(db, window=window)


@router.get("/rejection-analytics/details")
def rejection_analytics_details(
    window: str = Query(default="24h"),
    strategy_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    reason: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _, since = parse_window_to_since(window)
    query = db.query(StrategyObservabilityEvent).filter(
        StrategyObservabilityEvent.created_at >= since,
        or_(
            StrategyObservabilityEvent.event_type == "rejected",
            StrategyObservabilityEvent.rejection_reason.is_not(None),
        ),
    )
    if strategy_id:
        query = query.filter(StrategyObservabilityEvent.strategy_id == strategy_id)
    if symbol:
        query = query.filter(StrategyObservabilityEvent.symbol == symbol.upper())
    if reason:
        token = f"%{reason.strip()}%"
        query = query.filter(
            or_(
                StrategyObservabilityEvent.rejection_reason.ilike(token),
            )
        )

    rows = query.order_by(StrategyObservabilityEvent.created_at.desc()).limit(300).all()
    return {
        "window": window,
        "count": len(rows),
        "items": [_signal_to_dict(row) for row in rows],
    }


@router.get("/rejection-analytics/reasons")
def rejection_analytics_reasons(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    details = rejection_analytics_details(window=window, strategy_id=None, symbol=None, reason=None, _=None, db=db)
    reason_counts: dict[str, int] = {}
    for item in details["items"]:
        reject_reasons = item.get("reject_reasons") or []
        if not reject_reasons and item.get("rejection_reason"):
            reject_reasons = [item["rejection_reason"]]
        for reason_item in reject_reasons:
            key = str(reason_item)
            reason_counts[key] = reason_counts.get(key, 0) + 1
    return {
        "window": window,
        "reasons": [{"reason": key, "count": value} for key, value in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


@router.get("/rejection-analytics/signals/{signal_id}")
def rejection_signal_detail(signal_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == signal_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")
    return {
        "status": "success",
        "signal": _signal_to_dict(row),
        "actions": {
            "simulate": True,
            "explain": True,
            "retry": True,
        },
    }


@router.get("/score-metrics")
def score_metrics(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_score_metrics(db, window=window)


@router.get("/report")
def strategy_observability_report(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_strategy_observability_report(db, window=window)


@router.get("/audit-log")
def strategy_audit_log(
    limit: int = Query(default=100, ge=1, le=300),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.like("strategy_%"))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "items": [
            {
                "audit_id": row.id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "reason": row.reason,
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "details": row.details or {},
            }
            for row in rows
        ],
    }


@router.get("/observability-report")
def strategy_observability_report_alias(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_strategy_observability_report(db, window=window)
