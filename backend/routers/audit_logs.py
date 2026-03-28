import io
import json
import zipfile
import csv
import os
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin, require_super_admin
from models import AuditLog, User
from schemas import AuditLogResponse, AuditTimelineItemResponse, AuditTimelineResponse
from services.audit_service import create_audit_log
from services.audit_retention_service import prune_audit_logs_with_policy
from services.audit_integrity_service import compare_correlation_across_environments, verify_trace_integrity
from services.debug_incident_service import (
    build_incident_debug_bundle,
    close_incident,
    create_manual_incident,
    get_incident,
    list_incidents,
    serialize_incident,
)
from services.lifecycle_query_service import (
    create_saved_query,
    delete_saved_query,
    list_saved_queries,
    search_lifecycle_events,
)
from services.trading_lifecycle_debugger_service import get_lifecycle_chain, list_lifecycle_summaries, replay_lifecycle

router = APIRouter(prefix="/audit-logs", tags=["audit_logs"])


class LifecycleExplainRequest(BaseModel):
    correlation_id: str = Field(min_length=1, max_length=255)


class SavedQueryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    params: dict = Field(default_factory=dict)


class IncidentCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    severity: str = Field(default="CRITICAL")
    tags: list[str] = Field(default_factory=list)
    linked_correlation_id: str = Field(min_length=1, max_length=120)
    source_event_id: str | None = Field(default=None, max_length=120)
    root_cause: str | None = Field(default=None, max_length=160)
    cluster_id: str | None = Field(default=None, max_length=80)
    details: dict = Field(default_factory=dict)


class IncidentStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=20)


def _current_repo_commit_hash() -> str:
    try:
        return (
            subprocess.check_output(["git", "-C", "/app", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL)
            .strip()
        )
    except Exception:
        return "unknown"


def _repo_deploy_consistency() -> dict:
    repo_hash = _current_repo_commit_hash()
    deploy_hash = (
        os.environ.get("DEPLOY_COMMIT_HASH")
        or os.environ.get("PREVIEW_DEPLOY_COMMIT_HASH")
        or repo_hash
    )
    return {
        "repo_commit_hash": repo_hash,
        "deploy_commit_hash": deploy_hash,
        "is_match": bool(repo_hash and deploy_hash and repo_hash == deploy_hash),
    }


def _enforce_repo_deploy_consistency() -> dict:
    status_payload = _repo_deploy_consistency()
    if not status_payload["is_match"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "repo_deploy_mismatch",
                "repo_commit_hash": status_payload["repo_commit_hash"],
                "deploy_commit_hash": status_payload["deploy_commit_hash"],
            },
        )
    return status_payload


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


def _build_lifecycle_explain_payload(db: Session, correlation_id: str, *, limit: int = 1200) -> dict:
    payload = get_lifecycle_chain(db, correlation_id, limit=limit)
    chain = payload.get("chain") or {}
    events = payload.get("events") or chain.get("events") or []
    explain = payload.get("explain_failure") or {}

    broken_step_payload = explain.get("broken_step") or {}
    broken_step = (
        broken_step_payload.get("stage")
        or broken_step_payload.get("event_type")
        or (events[-1].get("lifecycle_stage") if events else None)
        or "unknown"
    )
    root_cause = explain.get("root_cause") or "insufficient_context"
    missing_stages = list(chain.get("missing_critical_stages") or payload.get("missing_critical_stages") or [])
    upstream_event = (explain.get("upstream_cause") or {}).get("event_type") or (explain.get("upstream_cause") or {}).get("event_id")
    downstream_impact = explain.get("downstream_impact") or []

    insufficient_data = len(events) == 0 or (root_cause in {"insufficient_context", "unknown"} and not broken_step)
    if insufficient_data:
        confidence = "low"
    elif missing_stages:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "correlation_id": correlation_id,
        "events": events,
        "trace_incomplete": bool(chain.get("trace_incomplete") or payload.get("trace_incomplete")),
        "missing_critical_stages": missing_stages,
        "broken_chain": bool(chain.get("broken_chain") or payload.get("broken_chain") or missing_stages),
        "broken_step": broken_step,
        "root_cause": root_cause,
        "missing_stages": missing_stages,
        "upstream_event": upstream_event,
        "downstream_impact": downstream_impact,
        "confidence": confidence,
        "insufficient_data": insufficient_data,
        "schema_version": payload.get("schema_version"),
        "explain_failure": explain,
        "root_cause_breakdown": payload.get("root_cause_breakdown") or {},
        "cluster_id": payload.get("cluster_id"),
        "pattern_tag": payload.get("pattern_tag"),
        "critical_blockers": payload.get("critical_blockers") or [],
    }


def _build_canonical_lifecycle_payload(payload: dict) -> dict:
    chain = payload.get("chain") or {}
    events = payload.get("events") or chain.get("events") or []
    missing_stages = list(chain.get("missing_critical_stages") or payload.get("missing_critical_stages") or [])
    broken_chain = bool(chain.get("broken_chain") or payload.get("broken_chain") or missing_stages)
    canonical = {
        "correlation_id": payload.get("correlation_id"),
        "events": events,
        "trace_incomplete": bool(chain.get("trace_incomplete") or payload.get("trace_incomplete") or missing_stages),
        "missing_critical_stages": missing_stages,
        "broken_chain": broken_chain,
    }
    merged = dict(payload)
    merged.update(canonical)
    return merged


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=10, le=300),
):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/timeline", response_model=AuditTimelineResponse)
def audit_logs_timeline(
    response: Response,
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
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-12-31"
    response.headers["Link"] = '</api/audit-logs/trading-lifecycle>; rel="successor-version"'
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
    return AuditTimelineResponse(
        total=len(items),
        items=items,
        deprecated=True,
        primary_endpoint="/api/audit-logs/trading-lifecycle",
    )


@router.get("/trading-lifecycle")
def trading_lifecycle_index(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=20, le=500),
    q: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    payload_query: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    include_test_events: bool = Query(default=False),
    archive_mode: bool = Query(default=False),
    archive_cutoff_days: int = Query(default=7, ge=1, le=365),
):
    return list_lifecycle_summaries(
        db,
        limit=limit,
        q=q,
        severity=severity,
        strategy_id=strategy_id,
        symbol=symbol,
        user_id=user_id,
        event_type=event_type,
        environment=environment,
        start_time=start_time,
        end_time=end_time,
        payload_query=payload_query,
        cursor=cursor,
        include_test_events=include_test_events,
        archive_mode=archive_mode,
        archive_cutoff_days=archive_cutoff_days,
    )


@router.get("/trading-lifecycle/search")
def trading_lifecycle_search(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    page_size: int = Query(default=100, ge=20, le=300),
    cursor: str | None = Query(default=None),
    q: str | None = Query(default=None),
    payload_query: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    include_test_events: bool = Query(default=False),
    archive_mode: bool = Query(default=False),
    archive_cutoff_days: int = Query(default=7, ge=1, le=365),
):
    return search_lifecycle_events(
        db,
        page_size=page_size,
        cursor=cursor,
        q=q,
        payload_query=payload_query,
        severity=severity,
        strategy_id=strategy_id,
        symbol=symbol,
        user_id=user_id,
        event_type=event_type,
        environment=environment,
        start_time=start_time,
        end_time=end_time,
        include_test_events=include_test_events,
        archive_mode=archive_mode,
        archive_cutoff_days=archive_cutoff_days,
    )


@router.get("/saved-queries")
def get_saved_queries(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
):
    return {"items": list_saved_queries(db, user_id=current_admin.id, limit=limit)}


@router.post("/saved-queries")
def save_query(
    request: SavedQueryCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    saved = create_saved_query(db, user_id=current_admin.id, name=request.name, params=request.params)
    return {"saved_query": saved}


@router.delete("/saved-queries/{query_id}")
def remove_saved_query(
    query_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    deleted = delete_saved_query(db, user_id=current_admin.id, query_id=query_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="saved_query_not_found")
    return {"deleted": True, "query_id": query_id}


@router.get("/lifecycle/{correlation_id}")
def lifecycle_detail(
    correlation_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=800, ge=50, le=3000),
    environment: str | None = Query(default=None),
):
    payload = get_lifecycle_chain(db, correlation_id, limit=limit, environment=environment)
    return _build_canonical_lifecycle_payload(payload)


@router.post("/explain")
def lifecycle_explain(
    request: LifecycleExplainRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _enforce_repo_deploy_consistency()
    return _build_lifecycle_explain_payload(db, request.correlation_id, limit=1200)


@router.get("/lifecycle/compare/{correlation_id}")
def lifecycle_compare_by_environment(
    correlation_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environments: str | None = Query(default="prod,staging"),
    limit: int = Query(default=1200, ge=50, le=3000),
):
    selected_environments = [item.strip().lower() for item in str(environments or "").split(",") if item.strip()]
    return compare_correlation_across_environments(
        db,
        correlation_id=correlation_id,
        environments=selected_environments,
        limit=limit,
    )


@router.get("/verify-integrity/{correlation_id}")
def verify_lifecycle_integrity(
    correlation_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str | None = Query(default=None),
):
    return verify_trace_integrity(db, correlation_id=correlation_id, environment=environment)


@router.post("/trading-lifecycle/{correlation_id}/replay")
def trading_lifecycle_replay(
    correlation_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    snapshot_id: str | None = Query(default=None),
):
    consistency = _enforce_repo_deploy_consistency()
    chain_payload = get_lifecycle_chain(db, correlation_id, limit=2000)
    replay_payload = replay_lifecycle(chain_payload, snapshot_id=snapshot_id, run_by=current_admin.id)
    replay_payload["repo_deploy_consistency"] = consistency
    create_audit_log(
        db,
        action="TRADING_LIFECYCLE_REPLAY",
        entity_type="trading_lifecycle",
        entity_id=correlation_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if replay_payload.get("result") == "FAILED" else "info",
        details={
            "snapshot_id": replay_payload.get("snapshot_id"),
            "result": replay_payload.get("result"),
            "step_count": replay_payload.get("step_count"),
            "break_step": replay_payload.get("break_step"),
            "side_effects_blocked": True,
        },
    )
    return replay_payload


@router.get("/consistency/repo-deploy")
def repo_deploy_consistency_status(_: User = Depends(require_admin)):
    return _repo_deploy_consistency()


@router.post("/incidents")
def create_incident(
    request: IncidentCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    incident = create_manual_incident(
        db,
        title=request.title,
        severity=request.severity,
        tags=request.tags,
        linked_correlation_id=request.linked_correlation_id,
        source_event_id=request.source_event_id,
        root_cause=request.root_cause,
        cluster_id=request.cluster_id,
        created_by=current_admin.id,
        details=request.details,
    )
    create_audit_log(
        db,
        action="DEBUG_INCIDENT_CREATED",
        entity_type="debug_incident",
        entity_id=incident.incident_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "linked_correlation_id": incident.linked_correlation_id,
            "auto_created": False,
            "status": incident.status,
        },
    )
    return {"incident": serialize_incident(incident)}


@router.get("/incidents")
def get_incidents(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    linked_correlation_id: str | None = Query(default=None),
):
    rows = list_incidents(
        db,
        limit=limit,
        status=status_filter,
        severity=severity,
        linked_correlation_id=linked_correlation_id,
    )
    return {"items": [serialize_incident(row) for row in rows]}


@router.get("/incidents/{incident_id}")
def get_incident_detail(
    incident_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = get_incident(db, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident_not_found")
    lifecycle = {}
    if row.linked_correlation_id:
        lifecycle = get_lifecycle_chain(db, row.linked_correlation_id, limit=1200)
    return {"incident": serialize_incident(row), "lifecycle": lifecycle}


@router.patch("/incidents/{incident_id}/status")
def update_incident_status(
    incident_id: str,
    request: IncidentStatusRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = get_incident(db, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident_not_found")

    normalized_status = str(request.status or "").strip().lower()
    if normalized_status == "closed":
        row = close_incident(db, incident=row, closed_by=current_admin.id)
    elif normalized_status in {"open", "in_progress"}:
        row.status = normalized_status
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_incident_status")

    return {"incident": serialize_incident(row)}


@router.get("/incidents/{incident_id}/bundle")
def export_incident_bundle(
    incident_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = get_incident(db, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident_not_found")

    bundle_payload = build_incident_debug_bundle(db, incident=row)
    payload_bytes = json.dumps(bundle_payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"debug_bundle_{incident_id}.json"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([payload_bytes]), media_type="application/json", headers=headers)


@router.post("/admin/retention/prune")
def prune_old_audit_logs(
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
    days: int = Query(default=90, ge=30, le=365),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = prune_audit_logs_with_policy(db, cutoff=cutoff, dry_run=False)

    create_audit_log(
        db,
        action="AUDIT_RETENTION_PRUNE",
        entity_type="audit_logs",
        entity_id="retention",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "days": days,
            "deleted_count": int(result.get("deleted_count") or 0),
            "protected_count": int(result.get("protected_count") or 0),
            "retention_policy_applied": bool(result.get("retention_policy_applied")),
            "preserved_categories": result.get("preserved_categories") or [],
        },
    )
    return {
        "days": days,
        "deleted_count": int(result.get("deleted_count") or 0),
        "protected_count": int(result.get("protected_count") or 0),
        "retention_policy_applied": bool(result.get("retention_policy_applied")),
        "preserved_categories": result.get("preserved_categories") or [],
    }


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