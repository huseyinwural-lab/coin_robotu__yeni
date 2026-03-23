from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import SystemAlert, User
from routers.admin_phase3_modules.common import (
    ensure_reason,
    ensure_super_admin,
    read_preview_payload,
    read_json_config,
    save_preview_payload,
    save_json_config,
    shape_response,
    write_audit_event,
)

router = APIRouter(tags=["admin_phase3_alerts"])

AUTO_ACK_POLICY_KEY = "admin_phase3:execution_alerts:auto_ack_policy:v1"


class InfoAutoAckPolicyUpdateRequest(BaseModel):
    enabled: bool = True
    threshold_hours: int = Field(default=24, ge=1, le=168)
    only_execution_alerts: bool = True
    reason: str = Field(..., min_length=3)


def _default_policy() -> dict:
    return {
        "enabled": True,
        "threshold_hours": 24,
        "only_execution_alerts": True,
        "updated_at": None,
    }


def _load_policy() -> dict:
    return read_json_config(AUTO_ACK_POLICY_KEY, _default_policy())


def _find_policy_matches(db: Session, *, policy: dict) -> list[dict]:
    threshold_hours = int(policy.get("threshold_hours") or 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
    query = db.query(SystemAlert).filter(
        SystemAlert.severity == "INFO",
        SystemAlert.status == "open",
        SystemAlert.created_at <= cutoff,
    )
    if policy.get("only_execution_alerts", True):
        query = query.filter(SystemAlert.alert_type.ilike("execution_%"))
    rows = query.order_by(SystemAlert.created_at.asc()).limit(500).all()

    matched: list[dict] = []
    for row in rows:
        matched_rules = ["severity_info", "older_than_threshold_hours"]
        if policy.get("only_execution_alerts", True):
            matched_rules.append("execution_alert_type")
        matched.append(
            {
                "alert_id": row.id,
                "severity": row.severity,
                "alert_type": row.alert_type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "matched_rules": matched_rules,
            }
        )
    return matched


@router.get("/execution-alerts/auto-ack/policy")
def execution_alerts_auto_ack_policy_get(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = db
    return shape_response(policy=_load_policy())


@router.put("/execution-alerts/auto-ack/policy")
def execution_alerts_auto_ack_policy_update(
    payload: InfoAutoAckPolicyUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    ensure_super_admin(current_admin)
    reason = ensure_reason(payload.reason, min_length=3)
    next_policy = {
        "enabled": bool(payload.enabled),
        "threshold_hours": int(payload.threshold_hours),
        "only_execution_alerts": bool(payload.only_execution_alerts),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_json_config(AUTO_ACK_POLICY_KEY, next_policy)

    write_audit_event(
        db,
        user=current_admin,
        action="execution_alert_auto_ack_policy_update",
        entity_type="system_alert_policy",
        entity_id="execution_info_auto_ack",
        details={
            "reason": reason,
            "policy": next_policy,
        },
        severity="warning",
    )
    db.commit()

    return shape_response(message="auto_ack_policy_updated", policy=next_policy)


@router.post("/execution-alerts/auto-ack/run")
@router.post("/auto-ack/run")
def execution_alerts_auto_ack_run(
    preview_token: str = Query(...),
    reason: str = Query(default="scheduled_auto_ack"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = _load_policy()
    if not policy.get("enabled"):
        return shape_response(message="auto_ack_policy_disabled", policy=policy, acked_count=0, ids=[])

    preview_payload = read_preview_payload(preview_token)
    if not preview_payload or preview_payload.get("type") != "auto_ack_preview":
        raise HTTPException(status_code=422, detail="preview_token_invalid_or_expired")

    reason_value = ensure_reason(reason, min_length=3)
    matched_payload = list(preview_payload.get("matched_alerts") or [])
    matched_ids = [str(item.get("alert_id") or "") for item in matched_payload if str(item.get("alert_id") or "").strip()]
    if not matched_ids:
        raise HTTPException(status_code=422, detail="auto_ack_preview_empty")

    rows = db.query(SystemAlert).filter(SystemAlert.id.in_(matched_ids), SystemAlert.status == "open").all()
    if not rows:
        raise HTTPException(status_code=422, detail="auto_ack_no_longer_match")

    now = datetime.now(timezone.utc)
    acked_ids = []
    for row in rows:
        details = dict(row.details or {})
        details["auto_acked"] = True
        details["auto_acked_at"] = now.isoformat()
        details["auto_acked_by"] = "policy"
        details["auto_acked_preview_token"] = preview_token
        row.details = details
        row.status = "ack"
        row.updated_at = now
        acked_ids.append(row.id)

    rule_match_counter: dict[str, int] = {}
    for item in matched_payload:
        if item.get("alert_id") not in acked_ids:
            continue
        for rule_name in item.get("matched_rules") or []:
            rule_match_counter[rule_name] = rule_match_counter.get(rule_name, 0) + 1

    write_audit_event(
        db,
        user=current_admin,
        action="execution_alert_info_auto_ack_run",
        entity_type="system_alert",
        entity_id="bulk",
        details={
            "reason": reason_value,
            "policy": policy,
            "preview_token": preview_token,
            "matched_count": len(acked_ids),
            "matched_ids": acked_ids,
            "matched_rule_counter": rule_match_counter,
        },
        severity="warning",
    )
    db.commit()

    return shape_response(
        message="auto_ack_run_completed",
        policy=policy,
        preview_token=preview_token,
        acked_count=len(acked_ids),
        ids=acked_ids,
        matched_rule_counter=rule_match_counter,
    )


@router.post("/execution-alerts/auto-ack/preview")
@router.post("/auto-ack/preview")
def execution_alerts_auto_ack_preview(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = _load_policy()
    matched_alerts = _find_policy_matches(db, policy=policy)
    matched_ids = [row.get("alert_id") for row in matched_alerts]
    rule_match_counter: dict[str, int] = {}
    for item in matched_alerts:
        for rule_name in item.get("matched_rules") or []:
            rule_match_counter[rule_name] = rule_match_counter.get(rule_name, 0) + 1

    preview_payload = {
        "type": "auto_ack_preview",
        "policy": policy,
        "matched_ids": matched_ids,
        "matched_alerts": matched_alerts,
        "rule_match_counter": rule_match_counter,
        "created_by": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = save_preview_payload(preview_payload)

    write_audit_event(
        db,
        user=current_admin,
        action="execution_alert_info_auto_ack_preview",
        entity_type="system_alert",
        entity_id="bulk",
        details={
            "policy": policy,
            "preview_token": preview_token,
            "matched_count": len(matched_ids),
            "matched_ids": matched_ids,
            "matched_rule_counter": rule_match_counter,
        },
    )
    db.commit()

    return shape_response(
        message="auto_ack_preview_ready",
        policy=policy,
        preview_token=preview_token,
        matched_count=len(matched_ids),
        ids=matched_ids,
        matched_alerts=matched_alerts,
        matched_rule_counter=rule_match_counter,
    )
