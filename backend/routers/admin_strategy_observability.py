import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin, require_super_admin
from models import AuditLog, StrategyObservabilityEvent, SystemAlert, User
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


def _safe_parse_iso(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    try:
        if normalized.endswith("Z"):
            normalized = normalized.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _resolve_time_range(window: str, time_from: str | None, time_to: str | None) -> tuple[str, datetime, datetime]:
    normalized, default_since = parse_window_to_since(window)
    now = datetime.now(timezone.utc)
    start_at = _safe_parse_iso(time_from) or default_since
    end_at = _safe_parse_iso(time_to) or now
    if end_at < start_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_time_range")
    return normalized, start_at, end_at


def _query_strategy_rows(
    db: Session,
    *,
    strategy_id: str | None,
    window: str,
    time_from: str | None,
    time_to: str | None,
    limit: int = 1500,
) -> tuple[str, datetime, datetime, list[StrategyObservabilityEvent]]:
    normalized, start_at, end_at = _resolve_time_range(window, time_from, time_to)
    query = db.query(StrategyObservabilityEvent).filter(
        StrategyObservabilityEvent.created_at >= start_at,
        StrategyObservabilityEvent.created_at <= end_at,
    )
    if strategy_id:
        query = query.filter(StrategyObservabilityEvent.strategy_id == strategy_id)
    rows = query.order_by(StrategyObservabilityEvent.created_at.asc()).limit(limit).all()
    return normalized, start_at, end_at, rows


def _build_trend_rows(rows: list[StrategyObservabilityEvent], *, window: str) -> list[dict]:
    if window == "24h":
        formatter = "%Y-%m-%d %H:00"
    else:
        formatter = "%Y-%m-%d"

    bucket_map: dict[str, dict] = {}
    for row in rows:
        if not row.created_at:
            continue
        bucket_key = row.created_at.astimezone(timezone.utc).strftime(formatter)
        bucket = bucket_map.setdefault(
            bucket_key,
            {
                "bucket": bucket_key,
                "selected_count": 0,
                "rejected_count": 0,
                "avg_adjusted_score": 0.0,
                "avg_base_score": 0.0,
                "total": 0,
                "sum_adjusted": 0.0,
                "sum_base": 0.0,
            },
        )
        bucket["total"] += 1
        bucket["sum_adjusted"] += float(row.adjusted_score or 0)
        bucket["sum_base"] += float(row.base_score or 0)
        if row.event_type == "selected_for_execution":
            bucket["selected_count"] += 1
        else:
            bucket["rejected_count"] += 1

    trend_rows = []
    for bucket_key in sorted(bucket_map.keys()):
        bucket = bucket_map[bucket_key]
        total = max(int(bucket["total"]), 1)
        trend_rows.append(
            {
                "bucket": bucket_key,
                "selected_count": int(bucket["selected_count"]),
                "rejected_count": int(bucket["rejected_count"]),
                "avg_adjusted_score": round(float(bucket["sum_adjusted"]) / total, 4),
                "avg_base_score": round(float(bucket["sum_base"]) / total, 4),
            }
        )
    return trend_rows


def _rows_to_export_payload(rows: list[StrategyObservabilityEvent]) -> list[dict]:
    return [
        {
            "signal_id": row.id,
            "strategy_id": row.strategy_id,
            "symbol": row.symbol,
            "event_type": row.event_type,
            "market_regime": row.market_regime,
            "base_score": float(row.base_score or 0),
            "adjusted_score": float(row.adjusted_score or 0),
            "score_delta": float(row.score_delta or 0),
            "selection_rank": row.selection_rank,
            "rejection_reason": row.rejection_reason,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _serialize_action_timeline_items(
    *,
    audit_rows: list[AuditLog],
    system_alert_rows: list[SystemAlert],
    strategy_filter: str | None,
    signal_strategy_map: dict[str, str],
) -> list[dict]:
    timeline: list[dict] = []

    for row in audit_rows:
        details = row.details or {}
        row_strategy_id = str(details.get("strategy_id") or "").strip() or None
        if not row_strategy_id:
            signal_ids = [str(item) for item in (details.get("signal_ids") or [])]
            for signal_id in signal_ids:
                if signal_id in signal_strategy_map:
                    row_strategy_id = signal_strategy_map[signal_id]
                    break

        if strategy_filter and row_strategy_id != strategy_filter:
            continue

        timeline.append(
            {
                "event_id": row.id,
                "event_type": "manual_action",
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "strategy_id": row_strategy_id,
                "action": row.action,
                "actor_role": row.actor_role,
                "reason": details.get("reason"),
                "impact_hint": details.get("state_snapshot") or details.get("after_payload") or details,
                "chain_ref": details.get("preview_token") or details.get("request_id") or row.entity_id,
            }
        )

    for row in system_alert_rows:
        details = row.details or {}
        blob = json.dumps(details, ensure_ascii=False)
        row_strategy_id = str(details.get("strategy_id") or "").strip() or None
        if not row_strategy_id:
            for signal_id, signal_strategy in signal_strategy_map.items():
                if signal_id in blob:
                    row_strategy_id = signal_strategy
                    break

        if strategy_filter and row_strategy_id != strategy_filter:
            continue

        timeline.append(
            {
                "event_id": row.id,
                "event_type": "system_reaction",
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "strategy_id": row_strategy_id,
                "action": row.alert_type,
                "actor_role": "system",
                "reason": row.message,
                "impact_hint": details,
                "severity": row.severity,
                "status": row.status,
                "chain_ref": row.entity_key or row.state_key or row.root_cause_code,
                "alert_detail_path": f"/api/admin/action-center/alerts/{row.id}/detail",
            }
        )

    timeline.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return timeline


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
        details={
            "reason": payload.reason,
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
        details={"reason": payload.reason, "signal_ids": signal_ids, "simulation_before_execution": True},
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
        details={
            "reason": payload.reason,
            "before_payload": previous,
            "after_payload": updated,
        },
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
        details={
            "reason": payload.reason,
            "before_payload": {"adjusted_score": before_adjusted},
            "after_payload": {"adjusted_score": after_adjusted},
            **override_record,
        },
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
        details={
            "reason": payload.reason,
            "before_payload": {"auto_tuning_enabled": current.get("auto_tuning_enabled", False)},
            "after_payload": {"auto_tuning_enabled": updated.get("auto_tuning_enabled", False)},
        },
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


@router.get("/observability/strategies")
def strategy_observability_strategy_list(
    window: str = Query(default="24h"),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at, rows = _query_strategy_rows(
        db,
        strategy_id=None,
        window=window,
        time_from=time_from,
        time_to=time_to,
        limit=5000,
    )
    strategy_ids = sorted({str(row.strategy_id) for row in rows if row.strategy_id})
    return {
        "window": normalized,
        "time_from": start_at.isoformat(),
        "time_to": end_at.isoformat(),
        "items": strategy_ids,
        "count": len(strategy_ids),
    }


@router.get("/observability/{strategy_id}/detail")
def strategy_observability_detail(
    strategy_id: str,
    window: str = Query(default="24h"),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at, rows = _query_strategy_rows(
        db,
        strategy_id=strategy_id,
        window=window,
        time_from=time_from,
        time_to=time_to,
        limit=5000,
    )

    selected_rows = [row for row in rows if row.event_type == "selected_for_execution"]
    rejected_rows = [row for row in rows if row.event_type != "selected_for_execution"]
    avg_adjusted = round(sum(float(row.adjusted_score or 0) for row in rows) / max(len(rows), 1), 4)
    avg_base = round(sum(float(row.base_score or 0) for row in rows) / max(len(rows), 1), 4)

    rejection_counts: dict[str, int] = {}
    symbols_counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.rejection_reason or "")
        if reason:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        symbols_counts[row.symbol] = symbols_counts.get(row.symbol, 0) + 1

    trend_rows = _build_trend_rows(rows, window=normalized)
    top_symbols = [
        {"symbol": key, "count": value}
        for key, value in sorted(symbols_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    ]
    rejection_reasons = [
        {"reason": key, "count": value}
        for key, value in sorted(rejection_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:30]
    ]

    return {
        "status": "success",
        "strategy_id": strategy_id,
        "filters": {
            "window": normalized,
            "time_from": start_at.isoformat(),
            "time_to": end_at.isoformat(),
        },
        "summary": {
            "signals_total": len(rows),
            "signals_selected": len(selected_rows),
            "signals_rejected": len(rejected_rows),
            "avg_adjusted_score": avg_adjusted,
            "avg_base_score": avg_base,
        },
        "trend_rows": trend_rows,
        "top_symbols": top_symbols,
        "rejection_reasons": rejection_reasons,
        "recent_rows": _rows_to_export_payload(rows[-150:]),
    }


@router.get("/observability/export")
def strategy_observability_export(
    export_format: Literal["json", "csv"] = Query(default="json"),
    window: str = Query(default="24h"),
    strategy_id: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    top_n: int = Query(default=1000, ge=1, le=5000),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at, rows = _query_strategy_rows(
        db,
        strategy_id=strategy_id,
        window=window,
        time_from=time_from,
        time_to=time_to,
        limit=top_n,
    )
    payload_rows = _rows_to_export_payload(rows)
    filters_payload = {
        "window": normalized,
        "strategy_id": strategy_id,
        "time_from": start_at.isoformat(),
        "time_to": end_at.isoformat(),
        "top_n": top_n,
    }

    if export_format == "json":
        return {
            "status": "success",
            "export_format": "json",
            "filters": filters_payload,
            "count": len(payload_rows),
            "items": payload_rows,
        }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["signal_id", "strategy_id", "symbol", "event_type", "market_regime", "base_score", "adjusted_score", "score_delta", "selection_rank", "rejection_reason", "created_at"])
    for row in payload_rows:
        writer.writerow(
            [
                row.get("signal_id"),
                row.get("strategy_id"),
                row.get("symbol"),
                row.get("event_type"),
                row.get("market_regime"),
                row.get("base_score"),
                row.get("adjusted_score"),
                row.get("score_delta"),
                row.get("selection_rank"),
                row.get("rejection_reason"),
                row.get("created_at"),
            ]
        )

    filename_strategy = strategy_id or "all"
    filename = f"observability_{filename_strategy}_{normalized}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Observability-Filters": json.dumps(filters_payload, ensure_ascii=False),
        },
    )


@router.get("/action-impact-timeline")
def strategy_action_impact_timeline(
    window: str = Query(default="24h"),
    strategy_id: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at = _resolve_time_range(window, time_from, time_to)
    window_duration = end_at - start_at
    prev_start = start_at - window_duration
    prev_end = start_at

    audit_rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.created_at >= start_at,
            AuditLog.created_at <= end_at,
            AuditLog.action.like("strategy_%"),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    system_alert_rows = (
        db.query(SystemAlert)
        .filter(
            SystemAlert.created_at >= start_at,
            SystemAlert.created_at <= end_at,
            or_(
                SystemAlert.alert_type.ilike("%strategy%"),
                SystemAlert.alert_type.ilike("%breach%"),
                SystemAlert.root_cause_code.ilike("%breach%"),
                SystemAlert.entity_key.ilike("%strategy%"),
            ),
        )
        .order_by(SystemAlert.created_at.desc())
        .limit(limit)
        .all()
    )

    signal_ids: set[str] = set()
    for row in audit_rows:
        details = row.details or {}
        for signal_id in details.get("signal_ids") or []:
            value = str(signal_id or "").strip()
            if value:
                signal_ids.add(value)

    signal_strategy_map: dict[str, str] = {}
    if signal_ids:
        signal_rows = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id.in_(list(signal_ids))).all()
        signal_strategy_map = {str(item.id): str(item.strategy_id) for item in signal_rows if item.id and item.strategy_id}

    timeline_rows = _serialize_action_timeline_items(
        audit_rows=audit_rows,
        system_alert_rows=system_alert_rows,
        strategy_filter=strategy_id,
        signal_strategy_map=signal_strategy_map,
    )
    timeline_rows = timeline_rows[:limit]
    manual_count = sum(1 for item in timeline_rows if item.get("event_type") == "manual_action")
    system_count = sum(1 for item in timeline_rows if item.get("event_type") == "system_reaction")

    def _event_kpis(range_start: datetime, range_end: datetime) -> dict:
        base_query = db.query(StrategyObservabilityEvent).filter(
            StrategyObservabilityEvent.created_at >= range_start,
            StrategyObservabilityEvent.created_at <= range_end,
        )
        if strategy_id:
            base_query = base_query.filter(StrategyObservabilityEvent.strategy_id == strategy_id)
        selected = base_query.filter(StrategyObservabilityEvent.event_type == "selected_for_execution").count()
        rejected = base_query.filter(StrategyObservabilityEvent.event_type != "selected_for_execution").count()
        return {
            "selected_signals": int(selected),
            "rejected_signals": int(rejected),
        }

    def _risk_breach_count(range_start: datetime, range_end: datetime) -> int:
        rows = (
            db.query(SystemAlert)
            .filter(
                SystemAlert.created_at >= range_start,
                SystemAlert.created_at <= range_end,
                or_(
                    SystemAlert.alert_type.ilike("%breach%"),
                    SystemAlert.root_cause_code.ilike("%breach%"),
                ),
            )
            .all()
        )
        if not strategy_id:
            return len(rows)
        matched = []
        for row in rows:
            details_blob = json.dumps(row.details or {}, ensure_ascii=False)
            if strategy_id in str(row.entity_key or "") or strategy_id in details_blob:
                matched.append(row)
        return len(matched)

    after_kpis = _event_kpis(start_at, end_at)
    before_kpis = _event_kpis(prev_start, prev_end)
    after_kpis["risk_breaches"] = _risk_breach_count(start_at, end_at)
    before_kpis["risk_breaches"] = _risk_breach_count(prev_start, prev_end)

    kpi_cards = {}
    for key in ["selected_signals", "rejected_signals", "risk_breaches"]:
        before_value = int(before_kpis.get(key, 0))
        after_value = int(after_kpis.get(key, 0))
        kpi_cards[key] = {
            "before": before_value,
            "after": after_value,
            "delta": after_value - before_value,
        }

    return {
        "status": "success",
        "filters": {
            "window": normalized,
            "strategy_id": strategy_id,
            "time_from": start_at.isoformat(),
            "time_to": end_at.isoformat(),
            "limit": limit,
        },
        "summary": {
            "total": len(timeline_rows),
            "manual_action_count": manual_count,
            "system_reaction_count": system_count,
        },
        "kpi_cards": kpi_cards,
        "items": timeline_rows,
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
                "reason": (row.details or {}).get("reason"),
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
