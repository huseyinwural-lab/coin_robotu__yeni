import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin, require_super_admin
from models import AuditLog, SystemAlert, User
from services.audit_service import create_audit_log
from services.pipeline.runtime import pipeline_runtime
from services.pipeline.spot_risk_capital_service import risk_capital_snapshot

router = APIRouter(prefix="/admin/strategy/risk-capital", tags=["admin_strategy_risk_capital"])

RISK_LIMIT_OVERRIDES_KEY = "strategy:risk_capital:limit_overrides:v1"
RISK_EXPOSURE_OVERRIDES_KEY = "strategy:risk_capital:exposure_overrides:v1"
RISK_PREVIEW_TOKEN_PREFIX = "strategy:risk_capital:preview"
RISK_PREVIEW_TTL_SECONDS = 600


class RiskLimitsPreviewRequest(BaseModel):
    max_open_risk_pct: float | None = Field(default=None, ge=0, le=100)
    max_daily_loss_pct: float | None = Field(default=None, ge=0, le=100)
    max_portfolio_drawdown_pct: float | None = Field(default=None, ge=0, le=100)
    max_strategy_drawdown_pct: float | None = Field(default=None, ge=0, le=100)
    max_positions_per_strategy: int | None = Field(default=None, ge=1, le=50)
    max_sector_exposure_pct: float | None = Field(default=None, ge=0, le=100)
    max_correlated_positions: int | None = Field(default=None, ge=1, le=30)


class RiskLimitsApplyRequest(BaseModel):
    preview_token: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


class ExposureOverridePreviewRequest(BaseModel):
    strategy_id: str = Field(..., min_length=2)
    override_cap_pct: float = Field(..., ge=0, le=100)


class ExposureOverrideApplyRequest(BaseModel):
    preview_token: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


def _role_value(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


def _load_json_from_redis(key: str, fallback: dict) -> dict:
    raw = redis_client.get(key)
    if not raw:
        return fallback
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        return fallback


def _save_json_to_redis(key: str, payload: dict) -> None:
    redis_client.set(key, json.dumps(payload, ensure_ascii=False))


def _save_preview_payload(payload: dict) -> str:
    token = str(uuid.uuid4())
    redis_client.set(f"{RISK_PREVIEW_TOKEN_PREFIX}:{token}", json.dumps(payload, ensure_ascii=False))
    redis_client.expire(f"{RISK_PREVIEW_TOKEN_PREFIX}:{token}", RISK_PREVIEW_TTL_SECONDS)
    return token


def _read_preview_payload(token: str) -> dict | None:
    raw = redis_client.get(f"{RISK_PREVIEW_TOKEN_PREFIX}:{token}")
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _effective_limits(base_limits: dict) -> dict:
    overrides = _load_json_from_redis(RISK_LIMIT_OVERRIDES_KEY, {})
    effective = dict(base_limits or {})
    for key, value in overrides.items():
        if key in effective and isinstance(value, (int, float)):
            effective[key] = float(value)
    return effective


def _effective_allocation(base_allocation: dict) -> tuple[dict, dict]:
    overrides = _load_json_from_redis(RISK_EXPOSURE_OVERRIDES_KEY, {})
    effective = {}
    for strategy_id, payload in (base_allocation or {}).items():
        row = dict(payload or {})
        original_effective = float(row.get("effective_allocation") or 0)
        cap_pct = overrides.get(strategy_id)
        if isinstance(cap_pct, (int, float)):
            cap_as_ratio = max(float(cap_pct), 0.0) / 100
            row["override_cap_pct"] = float(cap_pct)
            row["is_overridden"] = True
            row["effective_allocation"] = round(min(original_effective, cap_as_ratio), 6)
        else:
            row["override_cap_pct"] = None
            row["is_overridden"] = False
            row["effective_allocation"] = round(original_effective, 6)
        effective[strategy_id] = row
    return effective, overrides


def _build_breaches(snapshot: dict, alerts: list[dict]) -> list[dict]:
    limits = snapshot.get("limits") or {}
    breaches: list[dict] = []

    equity = float(snapshot.get("equity") or 0)
    open_risk_pct = float(snapshot.get("open_risk_pct") or 0)
    daily_loss_amount = float((snapshot.get("daily_loss") or {}).get("daily_loss_amount") or 0)
    daily_loss_pct = (daily_loss_amount / max(equity, 0.0001)) * 100
    portfolio_drawdown_pct = float(snapshot.get("portfolio_drawdown_pct") or 0)

    checks = [
        ("max_open_risk_pct", open_risk_pct, "Open Risk"),
        ("max_daily_loss_pct", daily_loss_pct, "Daily Loss"),
        ("max_portfolio_drawdown_pct", portfolio_drawdown_pct, "Portfolio Drawdown"),
    ]

    for code, current_value, label in checks:
        limit_value = float(limits.get(code) or 0)
        is_breached = current_value > limit_value
        linked_alerts = [
            item
            for item in alerts
            if code in str(item.get("alert_type") or "").lower() or code in str(item.get("root_cause_code") or "").lower()
        ]
        breaches.append(
            {
                "breach_code": code,
                "label": label,
                "current_value": round(current_value, 4),
                "limit_value": round(limit_value, 4),
                "is_breached": is_breached,
                "severity": "CRITICAL" if is_breached else "INFO",
                "linked_alerts": linked_alerts,
            }
        )

    strategy_drawdown_limit = float(limits.get("max_strategy_drawdown_pct") or 0)
    for strategy_id, drawdown_value in (snapshot.get("strategy_drawdown") or {}).items():
        strategy_drawdown = float(drawdown_value or 0)
        is_breached = strategy_drawdown > strategy_drawdown_limit
        breaches.append(
            {
                "breach_code": f"strategy_drawdown:{strategy_id}",
                "label": f"Strategy Drawdown ({strategy_id})",
                "current_value": round(strategy_drawdown, 4),
                "limit_value": round(strategy_drawdown_limit, 4),
                "is_breached": is_breached,
                "severity": "WARNING" if is_breached else "INFO",
                "linked_alerts": [
                    item
                    for item in alerts
                    if strategy_id in str(item.get("entity_key") or "")
                    or strategy_id in json.dumps(item.get("details") or {}, ensure_ascii=False)
                ],
            }
        )

    max_positions = int(float(limits.get("max_positions_per_strategy") or 0))
    for strategy_id, open_positions_count in (snapshot.get("strategy_open_positions") or {}).items():
        open_count = int(open_positions_count or 0)
        is_breached = open_count > max_positions
        breaches.append(
            {
                "breach_code": f"max_positions:{strategy_id}",
                "label": f"Max Positions ({strategy_id})",
                "current_value": open_count,
                "limit_value": max_positions,
                "is_breached": is_breached,
                "severity": "WARNING" if is_breached else "INFO",
                "linked_alerts": [
                    item
                    for item in alerts
                    if strategy_id in str(item.get("entity_key") or "")
                ],
            }
        )

    return sorted(breaches, key=lambda row: (not row["is_breached"], row["breach_code"]))


def _serialize_alert_row(row: SystemAlert) -> dict:
    return {
        "alert_id": row.id,
        "alert_type": row.alert_type,
        "severity": row.severity,
        "status": row.status,
        "message": row.message,
        "entity_key": row.entity_key,
        "root_cause_code": row.root_cause_code,
        "details": row.details or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "alert_detail_path": f"/api/admin/action-center/alerts/{row.id}/detail",
    }


def _linked_breach_alerts(db: Session, *, limit: int = 50) -> list[dict]:
    rows = (
        db.query(SystemAlert)
        .filter(
            or_(
                SystemAlert.alert_type.ilike("%breach%"),
                SystemAlert.root_cause_code.ilike("%breach%"),
                SystemAlert.state_key.ilike("%breach%"),
            )
        )
        .order_by(SystemAlert.last_triggered_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_alert_row(row) for row in rows]


def _build_effective_snapshot(db: Session, *, user_id: str) -> dict:
    base_snapshot = risk_capital_snapshot(db, pipeline_runtime.cache, user_id)
    base_limits = dict(base_snapshot.get("limits") or {})
    effective_limits = _effective_limits(base_limits)
    effective_allocation, exposure_overrides = _effective_allocation(base_snapshot.get("allocation") or {})
    linked_alerts = _linked_breach_alerts(db, limit=60)

    snapshot = {
        **base_snapshot,
        "limits_base": base_limits,
        "limits": effective_limits,
        "allocation": effective_allocation,
        "exposure_overrides": exposure_overrides,
        "linked_alerts": linked_alerts,
    }
    snapshot["breaches"] = _build_breaches(snapshot, linked_alerts)
    snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
    return snapshot


@router.get("/status")
def strategy_risk_capital_status(
    include_alerts: bool = Query(default=True),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot = _build_effective_snapshot(db, user_id=current_admin.id)
    if not include_alerts:
        snapshot["linked_alerts"] = []
    return snapshot


@router.post("/limits/preview")
def strategy_risk_limits_preview(
    payload: RiskLimitsPreviewRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    before_snapshot = _build_effective_snapshot(db, user_id=current_admin.id)
    before_limits = dict(before_snapshot.get("limits") or {})
    patch = payload.model_dump(exclude_none=True)
    next_limits = {
        **before_limits,
        **{key: float(value) for key, value in patch.items()},
    }

    preview_snapshot = dict(before_snapshot)
    preview_snapshot["limits"] = next_limits
    preview_snapshot["breaches"] = _build_breaches(preview_snapshot, preview_snapshot.get("linked_alerts") or [])

    preview_payload = {
        "type": "risk_limits_preview",
        "actor_id": current_admin.id,
        "limits_after": next_limits,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = _save_preview_payload(preview_payload)

    create_audit_log(
        db,
        action="strategy_risk_limits_preview",
        entity_type="strategy_risk_capital",
        entity_id=preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "preview_token": preview_token,
            "limits_before": before_limits,
            "limits_after": next_limits,
            "changed_fields": sorted(patch.keys()),
        },
    )

    return {
        "status": "success",
        "message": "risk_limits_preview_ready",
        "preview_token": preview_token,
        "state_snapshot": {
            "before_limits": before_limits,
            "after_limits": next_limits,
            "breaches_before": before_snapshot.get("breaches") or [],
            "breaches_after": preview_snapshot.get("breaches") or [],
            "changed_fields": sorted(patch.keys()),
        },
    }


@router.post("/limits/apply")
def strategy_risk_limits_apply(
    payload: RiskLimitsApplyRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")

    preview = _read_preview_payload(payload.preview_token)
    if not preview or preview.get("type") != "risk_limits_preview":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_invalid_or_expired")

    before_overrides = _load_json_from_redis(RISK_LIMIT_OVERRIDES_KEY, {})
    next_limits = preview.get("limits_after") or {}
    _save_json_to_redis(RISK_LIMIT_OVERRIDES_KEY, next_limits)

    create_audit_log(
        db,
        action="strategy_risk_limits_apply",
        entity_type="strategy_risk_capital",
        entity_id=payload.preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "before_limits": before_overrides,
            "after_limits": next_limits,
            "preview_token": payload.preview_token,
            "preview_required": True,
        },
    )

    return {
        "status": "success",
        "message": "risk_limits_applied",
        "state_snapshot": _build_effective_snapshot(db, user_id=current_admin.id),
    }


@router.post("/exposure-override/preview")
def strategy_exposure_override_preview(
    payload: ExposureOverridePreviewRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    before_snapshot = _build_effective_snapshot(db, user_id=current_admin.id)
    before_overrides = _load_json_from_redis(RISK_EXPOSURE_OVERRIDES_KEY, {})
    strategy_id = payload.strategy_id.strip()

    if strategy_id not in (before_snapshot.get("allocation") or {}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    after_overrides = {**before_overrides, strategy_id: float(payload.override_cap_pct)}
    _save_json_to_redis(RISK_EXPOSURE_OVERRIDES_KEY, after_overrides)
    after_snapshot = _build_effective_snapshot(db, user_id=current_admin.id)
    _save_json_to_redis(RISK_EXPOSURE_OVERRIDES_KEY, before_overrides)

    preview_payload = {
        "type": "exposure_override_preview",
        "actor_id": current_admin.id,
        "strategy_id": strategy_id,
        "override_cap_pct": float(payload.override_cap_pct),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = _save_preview_payload(preview_payload)

    create_audit_log(
        db,
        action="strategy_exposure_override_preview",
        entity_type="strategy_risk_capital",
        entity_id=preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "preview_token": preview_token,
            "strategy_id": strategy_id,
            "before_override": before_overrides.get(strategy_id),
            "after_override": float(payload.override_cap_pct),
        },
    )

    return {
        "status": "success",
        "message": "exposure_override_preview_ready",
        "preview_token": preview_token,
        "state_snapshot": {
            "strategy_id": strategy_id,
            "before": (before_snapshot.get("allocation") or {}).get(strategy_id),
            "after": (after_snapshot.get("allocation") or {}).get(strategy_id),
            "breaches_before": before_snapshot.get("breaches") or [],
            "breaches_after": after_snapshot.get("breaches") or [],
        },
    }


@router.post("/exposure-override/apply")
def strategy_exposure_override_apply(
    payload: ExposureOverrideApplyRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")

    preview = _read_preview_payload(payload.preview_token)
    if not preview or preview.get("type") != "exposure_override_preview":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_invalid_or_expired")

    strategy_id = str(preview.get("strategy_id") or "").strip()
    override_cap_pct = float(preview.get("override_cap_pct") or 0)
    if not strategy_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="strategy_id_missing_in_preview")

    before_overrides = _load_json_from_redis(RISK_EXPOSURE_OVERRIDES_KEY, {})
    next_overrides = {**before_overrides, strategy_id: override_cap_pct}
    _save_json_to_redis(RISK_EXPOSURE_OVERRIDES_KEY, next_overrides)

    create_audit_log(
        db,
        action="strategy_exposure_override_apply",
        entity_type="strategy_risk_capital",
        entity_id=payload.preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "strategy_id": strategy_id,
            "before_override": before_overrides.get(strategy_id),
            "after_override": override_cap_pct,
            "preview_required": True,
        },
    )

    return {
        "status": "success",
        "message": "exposure_override_applied",
        "state_snapshot": _build_effective_snapshot(db, user_id=current_admin.id),
    }


@router.get("/breaches")
def strategy_risk_breaches(
    only_open: bool = Query(default=False),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot = _build_effective_snapshot(db, user_id=current_admin.id)
    breaches = snapshot.get("breaches") or []
    if only_open:
        breaches = [item for item in breaches if item.get("is_breached")]
    return {
        "count": len(breaches),
        "items": breaches,
    }


@router.get("/alerts/{alert_id}/breach-link")
def strategy_risk_alert_breach_link(
    alert_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    alert_row = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if alert_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")

    snapshot = _build_effective_snapshot(db, user_id=current_admin.id)
    alert_blob = json.dumps(alert_row.details or {}, ensure_ascii=False)
    linked_breaches = [
        item
        for item in (snapshot.get("breaches") or [])
        if item.get("breach_code") in alert_blob
        or item.get("breach_code") in str(alert_row.alert_type or "")
        or item.get("breach_code") in str(alert_row.root_cause_code or "")
    ]
    return {
        "alert": _serialize_alert_row(alert_row),
        "linked_breaches": linked_breaches,
        "alert_detail_path": f"/api/admin/action-center/alerts/{alert_id}/detail",
    }


@router.get("/action-log")
def strategy_risk_action_log(
    limit: int = Query(default=100, ge=1, le=300),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.like("strategy_risk_%"))
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
                "actor_role": row.actor_role,
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }
