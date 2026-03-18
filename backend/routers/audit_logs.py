import io
import json
import zipfile
import csv
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin, require_super_admin
from models import AuditLog, User
from schemas import AuditLogResponse, AuditTimelineItemResponse, AuditTimelineResponse
from services.audit_service import create_audit_log

router = APIRouter(prefix="/audit-logs", tags=["audit_logs"])


def _parse_iso_datetime(value: str | None, *, detail_code: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail_code) from exc


def _build_timeline_query(
    db: Session,
    *,
    action: str | None,
    severity: str | None,
    entity_type: str | None,
    actor_user_id: str | None,
    request_id: str | None,
    session_id: str | None,
    q: str | None,
    date_from: str | None,
    date_to: str | None,
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if severity:
        query = query.filter(AuditLog.severity == severity.strip())
    if entity_type:
        query = query.filter(AuditLog.entity_type.ilike(f"%{entity_type.strip()}%"))
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id.strip())

    details_text = cast(AuditLog.details, String)
    if request_id:
        query = query.filter(details_text.ilike(f"%{request_id.strip()}%"))
    if session_id:
        query = query.filter(details_text.ilike(f"%{session_id.strip()}%"))
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            AuditLog.action.ilike(needle)
            | AuditLog.entity_type.ilike(needle)
            | AuditLog.entity_id.ilike(needle)
            | details_text.ilike(needle)
        )

    parsed_from = _parse_iso_datetime(date_from, detail_code="invalid_date_from")
    parsed_to = _parse_iso_datetime(date_to, detail_code="invalid_date_to")
    if parsed_from:
        query = query.filter(AuditLog.created_at >= parsed_from)
    if parsed_to:
        query = query.filter(AuditLog.created_at <= parsed_to)
    return query


def _serialize_timeline_item(row: AuditLog) -> dict:
    details = row.details or {}
    return {
        "id": row.id,
        "actor_user_id": row.actor_user_id,
        "actor_role": row.actor_role,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "severity": row.severity,
        "details": details,
        "request_id": details.get("request_id"),
        "session_id": details.get("session_id"),
        "route": details.get("route"),
        "method": details.get("method"),
        "created_at": row.created_at.isoformat(),
    }


def _root_cause_labels(*, action: str, details: dict, route: str | None) -> dict:
    reason_codes = details.get("reason_codes") or []
    if not isinstance(reason_codes, list):
        reason_codes = [str(reason_codes)]
    reason_candidates = [str(item).lower() for item in reason_codes if item is not None]

    explicit_error = str(details.get("error") or details.get("error_code") or "").strip().lower()
    status_code_raw = details.get("status_code")
    try:
        status_code = int(status_code_raw) if status_code_raw is not None else None
    except (TypeError, ValueError):
        status_code = None

    causes: list[dict] = []

    if any(code in {"timeout", "network_error", "exchange_unreachable"} for code in reason_candidates) or "timeout" in explicit_error:
        causes.append({"type": "TIMEOUT_NETWORK", "error_code": "timeout", "confidence": 0.92, "priority": "HIGH"})

    if (status_code in {401, 403}) or any(code in {"invalid_key", "missing_trade_permission", "permission_restricted", "auth_failed"} for code in reason_candidates):
        causes.append({"type": "AUTH", "error_code": "auth_error", "confidence": 0.9, "priority": "HIGH"})

    if (status_code is not None and status_code >= 500) or any(code in {"exchange_unreachable", "exchange_http_error", "exchange_error"} for code in reason_candidates):
        causes.append({"type": "EXCHANGE", "error_code": "exchange_5xx", "confidence": 0.86, "priority": "HIGH"})

    if any(code in {"assignment_required", "environment_not_allowed", "futures_not_allowed", "validation_failed"} for code in reason_candidates):
        causes.append({"type": "VALIDATION", "error_code": "validation_failed", "confidence": 0.78, "priority": "MED"})

    if not causes:
        fallback_error = reason_candidates[0] if reason_candidates else (explicit_error or "unknown")
        causes.append({"type": "UNKNOWN", "error_code": fallback_error, "confidence": 0.25, "priority": "LOW"})

    dedup = []
    seen = set()
    for cause in causes:
        key = cause["type"]
        if key in seen:
            continue
        seen.add(key)
        dedup.append(cause)

    primary = dedup[0]
    secondary = dedup[1] if len(dedup) > 1 else None
    confidence_score = round(float(primary["confidence"]), 3)
    priority_level = primary["priority"]

    normalized_route = str(route or "").lower()
    if "/v1/user/trading/preview" in normalized_route:
        failure_stage = "trade_preview"
    elif "/exchange-connections" in normalized_route:
        failure_stage = "connectivity_validation"
    elif "/admin/users" in normalized_route:
        failure_stage = "admin_user_ops"
    elif "domain_" in (action or "").lower():
        failure_stage = "domain_event"
    else:
        failure_stage = "unknown_stage"

    return {
        "root_cause_type": primary["type"],
        "failure_stage": failure_stage,
        "primary_error_code": primary["error_code"],
        "primary_cause": primary,
        "secondary_cause": secondary,
        "confidence_score": confidence_score,
        "priority_level": priority_level,
        "causes": dedup,
    }


def _build_replay_steps(rows: list[AuditLog]) -> tuple[list[dict], Counter]:
    steps = []
    root_cause_counter: Counter = Counter()
    prev_ts = None
    for index, row in enumerate(rows, start=1):
        details = row.details or {}
        current_ts = row.created_at
        delta_ms = None
        if prev_ts is not None:
            delta_ms = round((current_ts - prev_ts).total_seconds() * 1000, 2)
        prev_ts = current_ts

        labels = _root_cause_labels(action=row.action, details=details, route=details.get("route"))
        root_cause_counter[labels["root_cause_type"]] += 1
        steps.append(
            {
                "step_index": index,
                "timestamp": current_ts.isoformat(),
                "delta_ms_from_prev": delta_ms,
                "status": "error" if str(row.severity or "").lower() in {"warning", "critical"} else "ok",
                "action": row.action,
                "severity": row.severity,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "route": details.get("route"),
                "method": details.get("method"),
                "request_id": details.get("request_id"),
                "session_id": details.get("session_id"),
                "root_cause_type": labels["root_cause_type"],
                "failure_stage": labels["failure_stage"],
                "primary_error_code": labels["primary_error_code"],
                "primary_cause": labels["primary_cause"],
                "secondary_cause": labels["secondary_cause"],
                "confidence_score": labels["confidence_score"],
                "priority_level": labels["priority_level"],
                "causes": labels["causes"],
                "details": details,
            }
        )
    return steps, root_cause_counter


def _resolve_export_window(
    *,
    window_days: int | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str | None, str | None]:
    if window_days is None:
        return date_from, date_to
    if window_days not in {1, 7, 30, 90}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_window_days")
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=window_days)).isoformat(), now.isoformat()


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=10, le=300),
):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/timeline", response_model=AuditTimelineResponse)
def audit_logs_timeline(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=20, le=500),
    action: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    query = _build_timeline_query(
        db,
        action=action,
        severity=severity,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        request_id=request_id,
        session_id=session_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )

    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    items = [
        AuditTimelineItemResponse(
            id=row.id,
            actor_user_id=row.actor_user_id,
            actor_role=row.actor_role,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            severity=row.severity,
            details=row.details or {},
            request_id=(row.details or {}).get("request_id"),
            session_id=(row.details or {}).get("session_id"),
            route=(row.details or {}).get("route"),
            method=(row.details or {}).get("method"),
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AuditTimelineResponse(total=len(items), items=items)


@router.post("/admin/retention/prune")
def prune_old_audit_logs(
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
    days: int = Query(default=90, ge=30, le=365),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    to_delete_ids = [row.id for row in db.query(AuditLog.id).filter(AuditLog.created_at < cutoff).all()]
    deleted_count = 0
    if to_delete_ids:
        deleted_count = (
            db.query(AuditLog)
            .filter(AuditLog.id.in_(to_delete_ids))
            .delete(synchronize_session=False)
        )
        db.commit()

    create_audit_log(
        db,
        action="AUDIT_RETENTION_PRUNE",
        entity_type="audit_logs",
        entity_id="retention",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"days": days, "deleted_count": int(deleted_count)},
    )
    return {"days": days, "deleted_count": int(deleted_count)}


@router.get("/admin/incident-export")
def export_incident_package(
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=500, ge=50, le=1500),
    action: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    window_days: int | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    effective_date_from, effective_date_to = _resolve_export_window(
        window_days=window_days,
        date_from=date_from,
        date_to=date_to,
    )

    query = _build_timeline_query(
        db,
        action=action,
        severity=severity,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        request_id=request_id,
        session_id=session_id,
        q=q,
        date_from=effective_date_from,
        date_to=effective_date_to,
    )
    timeline_rows = query.order_by(AuditLog.created_at.asc()).limit(limit).all()
    replay_steps, root_cause_counter = _build_replay_steps(timeline_rows)
    timeline_items = [_serialize_timeline_item(row) for row in timeline_rows]

    request_ids = {item.get("request_id") for item in timeline_items if item.get("request_id")}
    session_ids = {item.get("session_id") for item in timeline_items if item.get("session_id")}
    actor_ids = {item.get("actor_user_id") for item in timeline_items if item.get("actor_user_id")}

    domain_query = db.query(AuditLog).filter(AuditLog.action.ilike("DOMAIN_%"))
    if timeline_rows:
        from_ts = min(row.created_at for row in timeline_rows) - timedelta(minutes=30)
        to_ts = max(row.created_at for row in timeline_rows) + timedelta(minutes=30)
        domain_query = domain_query.filter(AuditLog.created_at >= from_ts, AuditLog.created_at <= to_ts)

    details_text = cast(AuditLog.details, String)
    if request_ids or session_ids:
        or_filters = []
        for rid in request_ids:
            or_filters.append(details_text.ilike(f"%{rid}%"))
        for sid in session_ids:
            or_filters.append(details_text.ilike(f"%{sid}%"))
        from sqlalchemy import or_  # local import to keep file lightweight

        domain_query = domain_query.filter(or_(*or_filters))
    elif actor_ids:
        domain_query = domain_query.filter(AuditLog.actor_user_id.in_(list(actor_ids)))

    domain_rows = domain_query.order_by(AuditLog.created_at.desc()).limit(600).all()
    domain_items = [_serialize_timeline_item(row) for row in domain_rows]

    severity_counter = Counter(item.get("severity") or "unknown" for item in timeline_items)
    action_counter = Counter(item.get("action") or "unknown" for item in timeline_items)

    incident_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "limit": limit,
            "action": action,
            "severity": severity,
            "entity_type": entity_type,
            "actor_user_id": actor_user_id,
            "request_id": request_id,
            "session_id": session_id,
            "q": q,
            "window_days": window_days,
            "date_from": effective_date_from,
            "date_to": effective_date_to,
        },
        "timeline": timeline_items,
        "replay_steps": replay_steps,
        "related_domain_events": domain_items,
    }
    summary_payload = {
        "generated_at": incident_payload["generated_at"],
        "metrics": {
            "timeline_event_count": len(timeline_items),
            "related_domain_event_count": len(domain_items),
            "unique_request_ids": len(request_ids),
            "unique_session_ids": len(session_ids),
            "severity_breakdown": dict(severity_counter),
            "top_actions": action_counter.most_common(10),
            "window_start": timeline_items[0]["created_at"] if timeline_items else None,
            "window_end": timeline_items[-1]["created_at"] if timeline_items else None,
            "root_cause_breakdown": dict(root_cause_counter),
        },
        "notes": [
            "Bu özet hızlı yönetici okuması için hazırlanır.",
            "Teknik detaylar incident.json içinde tutulur.",
        ],
    }

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow([
        "timeline",
        "step",
        "status",
        "timestamp",
        "action",
        "severity",
        "route",
        "root_cause_type",
        "failure_stage",
        "primary_error_code",
        "confidence_score",
        "priority_level",
    ])
    for step in replay_steps:
        writer.writerow(
            [
                "incident_replay",
                step.get("step_index"),
                step.get("status"),
                step.get("timestamp"),
                step.get("action"),
                step.get("severity"),
                step.get("route"),
                step.get("root_cause_type"),
                step.get("failure_stage"),
                step.get("primary_error_code"),
                step.get("confidence_score"),
                step.get("priority_level"),
            ]
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("incident.json", json.dumps(incident_payload, ensure_ascii=False, indent=2))
        archive.writestr("summary.json", json.dumps(summary_payload, ensure_ascii=False, indent=2))
        archive.writestr("timeline.csv", csv_buffer.getvalue())
    buffer.seek(0)

    create_audit_log(
        db,
        action="INCIDENT_PACKAGE_EXPORTED",
        entity_type="incident_export",
        entity_id="audit_logs",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "timeline_event_count": len(timeline_items),
            "related_domain_event_count": len(domain_items),
            "limit": limit,
            "severity": severity,
            "action": action,
            "window_days": window_days,
        },
    )

    filename = f"incident_package_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="application/zip", headers=headers)


@router.get("/incident-replay")
def incident_replay(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    request_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    limit: int = Query(default=800, ge=20, le=3000),
):
    if not request_id and not session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request_id_or_session_id_required")

    details_text = cast(AuditLog.details, String)
    query = db.query(AuditLog)
    if request_id and session_id:
        from sqlalchemy import or_

        query = query.filter(or_(details_text.ilike(f"%{request_id}%"), details_text.ilike(f"%{session_id}%")))
    elif request_id:
        query = query.filter(details_text.ilike(f"%{request_id}%"))
    else:
        query = query.filter(details_text.ilike(f"%{session_id}%"))

    rows = query.order_by(AuditLog.created_at.asc()).limit(limit).all()
    if not rows:
        return {
            "filters": {"request_id": request_id, "session_id": session_id, "limit": limit},
            "summary": {"step_count": 0, "error_steps": 0},
            "steps": [],
            "related_domain_events": [],
        }

    steps, root_cause_counter = _build_replay_steps(rows)

    window_start = rows[0].created_at
    window_end = rows[-1].created_at
    details_text = cast(AuditLog.details, String)
    domain_query = db.query(AuditLog).filter(AuditLog.action.ilike("DOMAIN_%"))
    domain_query = domain_query.filter(
        AuditLog.created_at >= (window_start - timedelta(minutes=30)),
        AuditLog.created_at <= (window_end + timedelta(minutes=30)),
    )
    if request_id and session_id:
        from sqlalchemy import or_

        domain_query = domain_query.filter(or_(details_text.ilike(f"%{request_id}%"), details_text.ilike(f"%{session_id}%")))
    elif request_id:
        domain_query = domain_query.filter(details_text.ilike(f"%{request_id}%"))
    elif session_id:
        domain_query = domain_query.filter(details_text.ilike(f"%{session_id}%"))

    domain_rows = domain_query.order_by(AuditLog.created_at.asc()).limit(400).all()
    action_counter = Counter(step["action"] for step in steps)
    error_steps = sum(1 for step in steps if str(step.get("severity") or "").lower() in {"warning", "critical"})

    return {
        "filters": {"request_id": request_id, "session_id": session_id, "limit": limit},
        "summary": {
            "step_count": len(steps),
            "error_steps": error_steps,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "top_actions": action_counter.most_common(10),
            "root_cause_breakdown": dict(root_cause_counter),
        },
        "steps": steps,
        "related_domain_events": [_serialize_timeline_item(row) for row in domain_rows],
    }