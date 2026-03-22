import csv
import json
from io import StringIO
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import (
    ManualOverrideLog,
    PortfolioExposureSnapshot,
    StrategyAllocation,
    StrategyAllocationApprovalRequest,
    StrategyAllocationSnapshot,
    User,
    UserExecutionIntent,
    UserRole,
)
from schemas import (
    PortfolioRiskLimitsResponse,
    PortfolioRiskLimitsUpdate,
    RiskClusterResponse,
    RiskClusterUpsertRequest,
    StrategyAllocationActionEnvelope,
    StrategyAllocationApprovalRequestsResponse,
    StrategyAllocationBulkUpdateRequest,
    StrategyAllocationCreateRequest,
    StrategyAllocationSnapshotCreateResponse,
    StrategyAllocationSnapshotRestoreRequest,
    StrategyAllocationSnapshotsResponse,
    StrategyAllocationWhatIfRequest,
    StrategyAllocationWhatIfResponse,
    StrategyAllocationReasonNoteRequest,
    StrategyAllocationNormalizeRequest,
    StrategyAllocationRebalanceSuggestRequest,
    StrategyAllocationRebalanceSuggestionResponse,
    StrategyAllocationResponse,
    StrategyAllocationStateHistoryEntry,
    StrategyAllocationStateHistoryResponse,
    StrategyAllocationSummaryResponse,
    StrategyAllocationThrottleToggleRequest,
    StrategyAllocationUpdateRequest,
)
from services.meta_strategy_engine_service import (
    build_strategy_allocation_row_payload,
    build_projection_from_rebalance_suggestions,
    build_projection_from_rows,
    bulk_update_strategy_allocations,
    create_strategy_allocation,
    delete_strategy_allocation,
    generate_rebalance_suggestions,
    get_strategy_allocation_summary,
    list_strategy_allocation_dashboard_rows,
    normalize_strategy_allocations,
    recalculate_strategy_drift,
    toggle_strategy_throttle,
    update_strategy_allocation,
)
from services.portfolio_risk_service import list_risk_clusters, load_portfolio_risk_limits, save_portfolio_risk_limits, upsert_risk_cluster

router = APIRouter(prefix="/admin", tags=["admin_phase9_meta"])
ALLOCATION_REQUEST_PREFIX = "strategy_allocation"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _role_name(current_user: User) -> str:
    role = current_user.role
    if isinstance(role, UserRole):
        return str(role.value)
    return str(role)


def _require_reason_note(reason_note: str | None) -> str:
    note = str(reason_note or "").strip()
    if not note:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason_note zorunlu")
    return note


def _coerce_expected_revision(value, *, field_name: str = "expected_revision") -> int:
    try:
        revision = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} sayısal ve >= 1 olmalı",
        ) from exc
    if revision < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} >= 1 olmalı")
    return revision


def _build_revision_conflict_payload(*, action_type: str, conflicts: list[dict], request_id: str | None = None) -> dict:
    payload = {
        "code": "REVISION_CONFLICT",
        "message": "Veri başka bir işlem tarafından güncellendi. Lütfen en güncel halini yükleyin.",
        "action_type": action_type,
        "conflicts": conflicts,
    }
    if request_id:
        payload["request_id"] = request_id
    return payload


def _validate_revision_expectations(db: Session, expectations: dict[str, int], *, action_type: str) -> list[dict]:
    if not expectations:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expected_revision zorunlu")

    strategy_ids = list(expectations.keys())
    rows = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id.in_(strategy_ids)).all()
    row_map = {str(item.strategy_id): item for item in rows}

    conflicts: list[dict] = []
    for strategy_id, expected_revision in expectations.items():
        row = row_map.get(strategy_id)
        if not row:
            conflicts.append(
                {
                    "strategy_id": strategy_id,
                    "expected_revision": int(expected_revision),
                    "current_revision": None,
                    "reason": "MISSING_TARGET",
                }
            )
            continue
        current_revision = int(getattr(row, "revision_id", 1) or 1)
        if current_revision != int(expected_revision):
            conflicts.append(
                {
                    "strategy_id": strategy_id,
                    "expected_revision": int(expected_revision),
                    "current_revision": current_revision,
                    "reason": "REVISION_MISMATCH",
                    "action_type": action_type,
                }
            )
    return conflicts


def _raise_revision_conflict(*, action_type: str, conflicts: list[dict], request_id: str | None = None) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_build_revision_conflict_payload(action_type=action_type, conflicts=conflicts, request_id=request_id),
    )


def _extract_revision_expectations_for_request(action_type: str, payload: dict) -> dict[str, int]:
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    expectations: dict[str, int] = {}

    if action_type == "update":
        strategy_id = str(payload.get("strategy_id") or "").strip()
        expected_revision = body.get("expected_revision")
        if strategy_id and expected_revision is not None:
            expectations[strategy_id] = _coerce_expected_revision(expected_revision, field_name="expected_revision")
        return expectations

    if action_type == "delete":
        strategy_id = str(payload.get("strategy_id") or "").strip()
        expected_revision = payload.get("expected_revision")
        if strategy_id and expected_revision is not None:
            expectations[strategy_id] = _coerce_expected_revision(expected_revision, field_name="expected_revision")
        return expectations

    if action_type == "throttle_toggle":
        strategy_id = str(payload.get("strategy_id") or "").strip()
        expected_revision = body.get("expected_revision")
        if strategy_id and expected_revision is not None:
            expectations[strategy_id] = _coerce_expected_revision(expected_revision, field_name="expected_revision")
        return expectations

    if action_type == "bulk_update":
        updates = body.get("updates") or []
        for item in updates:
            if not isinstance(item, dict):
                continue
            strategy_id = str(item.get("strategy_id") or "").strip()
            if not strategy_id:
                continue
            if item.get("expected_revision") is None:
                continue
            expectations[strategy_id] = _coerce_expected_revision(
                item.get("expected_revision"),
                field_name=f"expected_revision[{strategy_id}]",
            )
        return expectations

    if action_type in {"normalize", "snapshot_restore"}:
        expected_revisions = body.get("expected_revisions") or {}
        if not expected_revisions:
            return expectations
        if not isinstance(expected_revisions, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expected_revisions map olmalı")
        for strategy_id, revision in expected_revisions.items():
            key = str(strategy_id or "").strip()
            if not key:
                continue
            expectations[key] = _coerce_expected_revision(revision, field_name=f"expected_revisions[{key}]")
        return expectations

    return expectations


def _allocation_request_type(action_type: str) -> str:
    return f"{ALLOCATION_REQUEST_PREFIX}:{action_type}"


def _extract_action_type_from_request(row: StrategyAllocationApprovalRequest) -> str:
    payload = row.payload if isinstance(row.payload, dict) else {}
    if payload.get("action_type"):
        return str(payload.get("action_type"))
    parts = str(row.request_type or "").split(":", 1)
    return parts[1] if len(parts) == 2 else str(row.request_type or "unknown")


def _map_decision_request_to_allocation_item(row: StrategyAllocationApprovalRequest) -> dict:
    payload = row.payload if isinstance(row.payload, dict) else {}
    stale_state = row.stale_state or payload.get("stale_state")
    stale_reason_code = row.stale_reason_code or payload.get("stale_reason_code")
    stale_conflicts = row.stale_conflicts if isinstance(row.stale_conflicts, list) else []
    if not stale_conflicts and isinstance(payload.get("stale_conflicts"), list):
        stale_conflicts = payload.get("stale_conflicts")
    revision_context = row.revision_context if isinstance(row.revision_context, dict) else {}
    if not revision_context and isinstance(payload.get("revision_context"), dict):
        revision_context = payload.get("revision_context")
    return {
        "request_id": row.request_id,
        "request_type": row.request_type,
        "action_type": _extract_action_type_from_request(row),
        "target_type": payload.get("target_type"),
        "target_id": payload.get("target_id"),
        "status": row.status,
        "requested_by": str(row.requested_by),
        "requested_role": row.requested_role,
        "reason_note": row.reason_note,
        "created_at": row.created_at,
        "requested_at": row.created_at,
        "expires_at": row.expires_at,
        "payload": payload,
        "revision_context": revision_context,
        "stale_state": stale_state,
        "stale_reason_code": stale_reason_code,
        "stale_conflicts": stale_conflicts,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at,
    }


def _build_global_revision_map(db: Session) -> dict[str, int]:
    rows = db.query(StrategyAllocation).all()
    return {str(item.strategy_id): int(getattr(item, "revision_id", 1) or 1) for item in rows}


def _queue_allocation_approval_request(
    *,
    db: Session,
    action_type: str,
    current_user: User,
    reason_note: str,
    payload: dict,
    target_type: str,
    target_id: str,
) -> dict:
    now = _now()
    request_id = f"alloc_req_{uuid4().hex[:12]}"
    revision_context: dict = {}
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    if action_type in {"normalize", "snapshot_restore"}:
        expected = body.get("expected_revisions") if isinstance(body.get("expected_revisions"), dict) else {}
        revision_context = {
            "scope": "global",
            "expected_revisions": expected,
            "expected_revision_count": len(expected),
        }
    elif action_type in {"update", "throttle_toggle"}:
        strategy_id = str(payload.get("strategy_id") or "")
        expected_revision = body.get("expected_revision")
        if strategy_id and expected_revision is not None:
            revision_context = {
                "scope": "single_strategy",
                "expected_revisions": {strategy_id: expected_revision},
                "expected_revision_count": 1,
            }
    elif action_type == "delete":
        strategy_id = str(payload.get("strategy_id") or "")
        expected_revision = payload.get("expected_revision")
        if strategy_id and expected_revision is not None:
            revision_context = {
                "scope": "single_strategy",
                "expected_revisions": {strategy_id: expected_revision},
                "expected_revision_count": 1,
            }
    elif action_type == "bulk_update":
        expected_map = {}
        for item in body.get("updates") or []:
            if not isinstance(item, dict):
                continue
            strategy_id = str(item.get("strategy_id") or "")
            expected_revision = item.get("expected_revision")
            if strategy_id and expected_revision is not None:
                expected_map[strategy_id] = expected_revision
        revision_context = {
            "scope": "bulk",
            "expected_revisions": expected_map,
            "expected_revision_count": len(expected_map),
        }

    normalized_payload = {
        **(payload or {}),
        "action_type": action_type,
        "target_type": target_type,
        "target_id": target_id,
        "revision_context": revision_context,
    }

    row = StrategyAllocationApprovalRequest(
        request_id=request_id,
        request_type=_allocation_request_type(action_type),
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        status="pending",
        requested_by=str(current_user.id),
        requested_role=_role_name(current_user),
        reason_note=reason_note,
        revision_context=revision_context,
        payload=normalized_payload,
        expires_at=now + timedelta(hours=24),
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _map_decision_request_to_allocation_item(row)


def _build_snapshot_payload(
    db: Session,
    *,
    created_by: str,
    reason_note: str,
    source_request_id: str | None = None,
) -> dict:
    rows = list_strategy_allocation_dashboard_rows(db, limit=500)
    summary = get_strategy_allocation_summary(db)
    rows_json_safe = json.loads(json.dumps(rows, default=str, ensure_ascii=False))
    summary_json_safe = json.loads(json.dumps(summary, default=str, ensure_ascii=False))
    snapshot_id = f"alloc_snapshot_{uuid4().hex[:12]}"

    revision_map = {str(item.get("strategy_id")): int(item.get("revision_id") or 1) for item in rows_json_safe}

    snapshot_row = StrategyAllocationSnapshot(
        snapshot_id=snapshot_id,
        created_at=_now(),
        created_by=created_by,
        reason_note=reason_note,
        strategy_count=len(rows),
        total_weight=float(summary_json_safe.get("total_weight") or 0),
        total_capital=float(summary_json_safe.get("total_capital") or 0),
        used_capital=float(summary_json_safe.get("used_capital") or 0),
        summary_payload=summary_json_safe,
        rows_payload=rows_json_safe,
        revision_map=revision_map,
        source_request_id=source_request_id,
    )
    db.add(snapshot_row)
    db.commit()
    db.refresh(snapshot_row)

    payload = {
        "snapshot_id": snapshot_row.snapshot_id,
        "created_at": snapshot_row.created_at,
        "created_by": snapshot_row.created_by,
        "reason_note": snapshot_row.reason_note,
        "strategy_count": int(snapshot_row.strategy_count),
        "total_weight": float(snapshot_row.total_weight),
        "total_capital": float(snapshot_row.total_capital),
        "used_capital": float(snapshot_row.used_capital),
        "source_request_id": snapshot_row.source_request_id,
        "restored_at": snapshot_row.restored_at,
        "restored_by": snapshot_row.restored_by,
        "summary": summary_json_safe,
        "rows": rows_json_safe,
        "revision_map": revision_map,
    }
    return payload


def _build_what_if_payload(db: Session, strategy_ids: list[str] | None = None) -> dict:
    suggestion = generate_rebalance_suggestions(db, strategy_ids=strategy_ids)
    rows = suggestion.get("suggestions") or []
    if not rows:
        return {
            "status": "empty",
            "message": "What-if için veri bulunamadı",
            "trace_id": suggestion.get("trace_id") or f"alloc_whatif_{uuid4().hex[:10]}",
            "read_only": True,
            "selection_count": int(suggestion.get("selection_count") or 0),
            "projected_portfolio_return_delta_pct": 0.0,
            "projected_portfolio_risk_delta_pct": 0.0,
            "rows": [],
        }
    projection = build_projection_from_rebalance_suggestions(rows)

    return {
        "status": "success",
        "message": "What-if preview hazır (read-only)",
        "trace_id": suggestion.get("trace_id") or f"alloc_whatif_{uuid4().hex[:10]}",
        "read_only": True,
        "selection_count": int(suggestion.get("selection_count") or 0),
        "projected_portfolio_return_delta_pct": projection.get("projected_portfolio_return_delta_pct", 0),
        "projected_portfolio_risk_delta_pct": projection.get("projected_portfolio_risk_delta_pct", 0),
        "rows": projection.get("rows") or [],
    }


def _validate_global_revision_scope(db: Session, expected_revisions: dict[str, int], *, action_type: str) -> None:
    if not expected_revisions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expected_revisions zorunlu")

    current_ids = {
        str(getattr(item, "strategy_id", item[0]))
        for item in db.query(StrategyAllocation.strategy_id).all()
    }
    expected_ids = set(expected_revisions.keys())
    scope_conflicts: list[dict] = []

    for strategy_id in sorted(current_ids - expected_ids):
        scope_conflicts.append(
            {
                "strategy_id": strategy_id,
                "expected_revision": None,
                "current_revision": "known",
                "reason": "MISSING_EXPECTATION",
                "action_type": action_type,
            }
        )
    for strategy_id in sorted(expected_ids - current_ids):
        scope_conflicts.append(
            {
                "strategy_id": strategy_id,
                "expected_revision": expected_revisions.get(strategy_id),
                "current_revision": None,
                "reason": "UNKNOWN_STRATEGY",
                "action_type": action_type,
            }
        )
    if scope_conflicts:
        _raise_revision_conflict(action_type=action_type, conflicts=scope_conflicts)

    conflicts = _validate_revision_expectations(db, expected_revisions, action_type=action_type)
    if conflicts:
        _raise_revision_conflict(action_type=action_type, conflicts=conflicts)


def _get_snapshot_or_404(db: Session, snapshot_id: str) -> StrategyAllocationSnapshot:
    row = db.query(StrategyAllocationSnapshot).filter(StrategyAllocationSnapshot.snapshot_id == snapshot_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"snapshot not found: {snapshot_id}")
    return row


def _invalidate_pending_allocation_requests(
    db: Session,
    *,
    restore_snapshot_id: str,
    restore_trace_id: str,
    exclude_request_id: str | None = None,
) -> int:
    pending_rows = (
        db.query(StrategyAllocationApprovalRequest)
        .filter(
            StrategyAllocationApprovalRequest.request_type.like(f"{ALLOCATION_REQUEST_PREFIX}:%"),
            StrategyAllocationApprovalRequest.status == "pending",
        )
        .all()
    )
    invalidated_count = 0
    for row in pending_rows:
        if exclude_request_id and row.request_id == exclude_request_id:
            continue
        payload = row.payload if isinstance(row.payload, dict) else {}
        payload["stale_state"] = "STALE"
        payload["stale_reason_code"] = "RESTORE_INVALIDATION"
        payload["stale_conflicts"] = payload.get("stale_conflicts") or []
        payload["restore_context"] = {
            "snapshot_id": restore_snapshot_id,
            "restore_trace_id": restore_trace_id,
        }
        row.payload = payload
        row.status = "requires_review"
        row.stale_state = "STALE"
        row.stale_reason_code = "RESTORE_INVALIDATION"
        row.stale_conflicts = payload.get("stale_conflicts") or []
        row.review_note = f"restore_invalidated::{restore_snapshot_id}"
        row.reviewed_at = _now()
        invalidated_count += 1
    if invalidated_count > 0:
        db.commit()
    return invalidated_count


def _restore_snapshot_to_allocation(
    db: Session,
    *,
    snapshot_row: StrategyAllocationSnapshot,
    actor_id: str,
    reason_note: str,
    related_request_id: str | None = None,
) -> dict:
    snapshot_rows = snapshot_row.rows_payload if isinstance(snapshot_row.rows_payload, list) else []
    if not snapshot_rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="snapshot rows boş, restore yapılamaz")

    current_rows = db.query(StrategyAllocation).all()
    current_map = {str(item.strategy_id): item for item in current_rows}
    snapshot_ids = {str(item.get("strategy_id")) for item in snapshot_rows if item.get("strategy_id")}

    for existing_id, existing_row in current_map.items():
        if existing_id in snapshot_ids:
            continue
        db.delete(existing_row)

    base_revision = int(max([int(getattr(item, "revision_id", 1) or 1) for item in current_rows] + [1])) + 1
    global_revision_id = max(base_revision, int(_now().timestamp()))

    for row_payload in snapshot_rows:
        strategy_id = str(row_payload.get("strategy_id") or "").strip()
        if not strategy_id:
            continue
        row = current_map.get(strategy_id)
        if not row:
            row = StrategyAllocation(strategy_id=strategy_id)
            db.add(row)

        row.capital_weight = float(row_payload.get("capital_weight") or 0)
        row.max_capital = float(row_payload.get("max_capital") or 0)
        row.current_capital = float(row_payload.get("current_capital") or 0)
        row.confidence_score = float(row_payload.get("confidence_score") or 0)
        row.performance_score = float(row_payload.get("performance_score") or 0)
        row.state = str(row_payload.get("state") or "ACTIVE")
        row.expected_return = float(row_payload.get("expected_return") or 0)
        row.realized_return = float(row_payload.get("realized_return") or 0)
        row.signal_decay = float(row_payload.get("signal_decay") or 0)
        row.execution_quality_score = float(row_payload.get("execution_quality_score") or 0)
        row.revision_id = global_revision_id
        row.updated_by = str(actor_id)
        row.change_reason = f"snapshot_restore::{snapshot_row.snapshot_id}::{reason_note}"
        row.updated_at = _now()

    db.flush()

    for strategy_id in snapshot_ids:
        recalculate_strategy_drift(db, strategy_id)

    restored_rows = db.query(StrategyAllocation).all()
    for item in restored_rows:
        item.revision_id = global_revision_id
        item.updated_by = str(actor_id)
        item.change_reason = f"snapshot_restore::{snapshot_row.snapshot_id}::{reason_note}"
        item.updated_at = _now()

    db.commit()

    snapshot_row.restored_at = _now()
    snapshot_row.restored_by = str(actor_id)
    db.add(snapshot_row)
    db.commit()

    trace_id = _write_allocation_log(
        db,
        admin_id=actor_id,
        action_type="strategy_allocation_snapshot_restore",
        strategy_id="*",
        previous_state=None,
        new_state=None,
        reason_code="SNAPSHOT_RESTORE",
        reason_detail=reason_note,
        payload={
            "snapshot_id": snapshot_row.snapshot_id,
            "global_revision_id": global_revision_id,
            "invalidated_pending_requests": 0,
            "related_request_id": related_request_id,
        },
    )

    invalidated = _invalidate_pending_allocation_requests(
        db,
        restore_snapshot_id=snapshot_row.snapshot_id,
        restore_trace_id=trace_id,
        exclude_request_id=related_request_id,
    )

    summary = get_strategy_allocation_summary(db)

    return {
        "trace_id": trace_id,
        "summary": summary,
        "invalidated_pending_requests": invalidated,
        "global_revision_id": global_revision_id,
    }


def _resolve_export_meta(
    db: Session,
    *,
    current_user: User,
    reason_note: str | None,
    related_request_id: str | None,
    snapshot_id: str | None,
    selected_strategy_ids: list[str],
) -> dict:
    normalized_reason = str(reason_note or "").strip()
    normalized_related = str(related_request_id or "").strip() or None
    normalized_snapshot = str(snapshot_id or "").strip() or None
    source_context = "manual"

    latest_approved_request = (
        db.query(StrategyAllocationApprovalRequest)
        .filter(
            StrategyAllocationApprovalRequest.request_type.like(f"{ALLOCATION_REQUEST_PREFIX}:%"),
            StrategyAllocationApprovalRequest.status == "approved",
        )
        .order_by(StrategyAllocationApprovalRequest.reviewed_at.desc(), StrategyAllocationApprovalRequest.created_at.desc())
        .first()
    )

    latest_snapshot = (
        db.query(StrategyAllocationSnapshot)
        .order_by(StrategyAllocationSnapshot.created_at.desc())
        .first()
    )

    if not normalized_related and latest_approved_request:
        normalized_related = latest_approved_request.request_id
        source_context = "request"
    if not normalized_snapshot and latest_snapshot:
        normalized_snapshot = latest_snapshot.snapshot_id
        if source_context == "manual":
            source_context = "snapshot"
    if not normalized_reason and latest_approved_request:
        normalized_reason = str(latest_approved_request.review_note or latest_approved_request.reason_note or "").strip()
    if not normalized_reason and latest_snapshot:
        normalized_reason = str(latest_snapshot.reason_note or "").strip()

    revision_context = _build_global_revision_map(db)
    max_revision = max(revision_context.values()) if revision_context else 0

    return {
        "exported_at": _now().isoformat(),
        "exported_by": str(current_user.id),
        "config_version": f"alloc-rev-{max_revision}",
        "snapshot_id": normalized_snapshot,
        "reason_note": normalized_reason or "manual_export",
        "related_request_id": normalized_related,
        "revision_context": revision_context,
        "source_context": source_context,
        "selected_strategy_ids": selected_strategy_ids,
    }


def _write_allocation_log(
    db: Session,
    *,
    admin_id: str,
    action_type: str,
    strategy_id: str,
    previous_state: str | None,
    new_state: str | None,
    reason_code: str | None,
    reason_detail: str | None,
    payload: dict,
) -> str:
    trace_id = f"alloc_trace_{uuid4().hex[:12]}"
    row = ManualOverrideLog(
        override_id=trace_id,
        admin_id=str(admin_id),
        action_type=action_type,
        reason=f"strategy_allocation::{action_type}",
        payload={
            "strategy_id": strategy_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "reason_code": reason_code,
            "reason_detail": reason_detail,
            "details": payload,
        },
        timestamp=_now(),
    )
    db.add(row)
    db.commit()
    return trace_id


def _execute_allocation_approval_request(
    *,
    db: Session,
    current_user: User,
    request_row: dict,
):
    action_type = str(request_row.get("action_type") or "")
    payload = request_row.get("payload") or {}
    reason_note = str(request_row.get("reason_note") or "approved_request")

    if action_type == "normalize":
        result = normalize_strategy_allocations(
            db,
            actor_id=str(current_user.id),
            change_reason=f"approval::{reason_note}",
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_normalize",
            strategy_id="*",
            previous_state=None,
            new_state=None,
            reason_code="WEIGHT_NORMALIZED",
            reason_detail=reason_note,
            payload=result,
        )
        return StrategyAllocationActionEnvelope(
            status="success",
            message="Approval sonrası normalize tamamlandı",
            trace_id=str(result.get("trace_id") or request_row.get("request_id")),
            summary=StrategyAllocationSummaryResponse(**(result.get("summary") or {})),
        )

    if action_type == "snapshot_create":
        snapshot = _build_snapshot_payload(
            db,
            created_by=str(current_user.id),
            reason_note=reason_note,
            source_request_id=str(request_row.get("request_id") or ""),
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_snapshot_create",
            strategy_id="*",
            previous_state=None,
            new_state=None,
            reason_code="SNAPSHOT_CREATED",
            reason_detail=reason_note,
            payload={"snapshot_id": snapshot.get("snapshot_id"), "strategy_count": snapshot.get("strategy_count")},
        )
        return StrategyAllocationSnapshotCreateResponse(
            status="success",
            message="Approval sonrası snapshot oluşturuldu",
            snapshot=snapshot,
            trace_id=snapshot.get("snapshot_id"),
        )

    if action_type == "snapshot_restore":
        snapshot_id = str(payload.get("snapshot_id") or "")
        snapshot_row = _get_snapshot_or_404(db, snapshot_id)
        restore_body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
        expected_revisions = {
            str(k): _coerce_expected_revision(v, field_name=f"expected_revisions[{k}]")
            for k, v in (restore_body.get("expected_revisions") or {}).items()
        }
        _validate_global_revision_scope(db, expected_revisions, action_type="snapshot_restore")

        restore_result = _restore_snapshot_to_allocation(
            db,
            snapshot_row=snapshot_row,
            actor_id=str(current_user.id),
            reason_note=reason_note,
            related_request_id=str(request_row.get("request_id") or ""),
        )
        return StrategyAllocationActionEnvelope(
            status="success",
            message=(
                f"Snapshot restore tamamlandı: {snapshot_id} "
                f"(invalidated_pending_requests={restore_result.get('invalidated_pending_requests', 0)})"
            ),
            trace_id=str(restore_result.get("trace_id") or request_row.get("request_id")),
            summary=StrategyAllocationSummaryResponse(**(restore_result.get("summary") or {})),
        )

    if action_type == "create":
        row = create_strategy_allocation(
            db,
            payload.get("body") or {},
            actor_id=str(current_user.id),
            change_reason=f"approval::{reason_note}",
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_create",
            strategy_id=row.strategy_id,
            previous_state=None,
            new_state=row.state,
            reason_code="MANUAL_CREATE",
            reason_detail=reason_note,
            payload=payload,
        )
        return StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row, db=db))

    if action_type == "update":
        strategy_id = str(payload.get("strategy_id") or "")
        body = payload.get("body") or {}
        row = update_strategy_allocation(
            db,
            strategy_id,
            body,
            actor_id=str(current_user.id),
            change_reason=f"approval::{reason_note}",
        )
        row_payload = build_strategy_allocation_row_payload(row, db=db, requested_state=body.get("state"))
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_state_change",
            strategy_id=strategy_id,
            previous_state=payload.get("previous_state"),
            new_state=row.state,
            reason_code=row_payload.get("state_reason_code"),
            reason_detail=reason_note,
            payload={
                **body,
                "projection_preview": payload.get("projection_preview") or {},
            },
        )
        return StrategyAllocationResponse.model_validate(row_payload)

    if action_type == "delete":
        strategy_id = str(payload.get("strategy_id") or "")
        result = delete_strategy_allocation(
            db,
            strategy_id,
            auto_normalize=bool(payload.get("auto_normalize", True)),
            actor_id=str(current_user.id),
            change_reason=f"approval::{reason_note}",
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_delete",
            strategy_id=strategy_id,
            previous_state=None,
            new_state=None,
            reason_code="MANUAL_DELETE",
            reason_detail=reason_note,
            payload=result,
        )
        return StrategyAllocationActionEnvelope(
            status="success",
            message=f"Approval sonrası strategy silindi: {strategy_id}",
            trace_id=str(result.get("trace_id") or request_row.get("request_id")),
            summary=StrategyAllocationSummaryResponse(**(result.get("summary") or {})),
        )

    if action_type == "bulk_update":
        result = bulk_update_strategy_allocations(
            db,
            payload.get("body") or {},
            actor_id=str(current_user.id),
            change_reason=f"approval::{reason_note}",
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_bulk_update",
            strategy_id="*",
            previous_state=None,
            new_state=None,
            reason_code="MANUAL_BULK_UPDATE",
            reason_detail=reason_note,
            payload=result,
        )
        return {
            "status": "success",
            "message": f"Approval sonrası bulk update tamamlandı ({result.get('updated_count', 0)} strategy)",
            "trace_id": str(result.get("trace_id") or request_row.get("request_id")),
            "updated_count": result.get("updated_count", 0),
            "updated_rows": [
                StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row, db=db)).model_dump()
                for row in (result.get("updated_rows") or [])
            ],
            "summary": result.get("summary") or {},
            "enforced_reduce_rows": result.get("enforced_reduce_rows") or [],
        }

    if action_type == "throttle_toggle":
        strategy_id = str(payload.get("strategy_id") or "")
        row = toggle_strategy_throttle(
            db,
            strategy_id,
            payload.get("body") or {},
            actor_id=str(current_user.id),
            change_reason=f"approval::{reason_note}",
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_throttle_toggle",
            strategy_id=strategy_id,
            previous_state=payload.get("previous_state"),
            new_state=row.state,
            reason_code="MANUAL_THROTTLE_TOGGLE",
            reason_detail=reason_note,
            payload=payload,
        )
        return StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row, db=db))

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Bilinmeyen approval action: {action_type}")


@router.get("/portfolio-risk/limits", response_model=PortfolioRiskLimitsResponse)
def get_portfolio_risk_limits(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    _ = db
    return PortfolioRiskLimitsResponse(**load_portfolio_risk_limits())


@router.put("/portfolio-risk/limits", response_model=PortfolioRiskLimitsResponse)
def update_portfolio_risk_limits(
    payload: PortfolioRiskLimitsUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    _ = db
    updated = save_portfolio_risk_limits(payload.model_dump())
    return PortfolioRiskLimitsResponse(**updated)


@router.get("/portfolio-risk/clusters", response_model=list[RiskClusterResponse])
def get_risk_clusters(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = list_risk_clusters(db)
    db.commit()
    return [RiskClusterResponse.model_validate(row) for row in rows]


@router.post("/portfolio-risk/clusters", response_model=RiskClusterResponse)
def create_or_update_risk_cluster(
    payload: RiskClusterUpsertRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    try:
        row = upsert_risk_cluster(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RiskClusterResponse.model_validate(row)


@router.put("/portfolio-risk/clusters/{cluster_id}", response_model=RiskClusterResponse)
def update_risk_cluster_by_id(
    cluster_id: str,
    payload: RiskClusterUpsertRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    data = payload.model_dump()
    data["cluster_id"] = cluster_id
    try:
        row = upsert_risk_cluster(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RiskClusterResponse.model_validate(row)


@router.get("/portfolio-risk")
def portfolio_risk_dashboard(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    lookback_from = _now() - timedelta(days=7)

    snapshots = (
        db.query(PortfolioExposureSnapshot)
        .filter(PortfolioExposureSnapshot.timestamp >= lookback_from)
        .order_by(PortfolioExposureSnapshot.timestamp.desc())
        .limit(1500)
        .all()
    )
    total_exposure = round(sum(float(item.notional or 0) for item in snapshots), 4)

    cluster_exposure: dict[str, float] = {}
    strategy_exposure: dict[str, float] = {}
    for item in snapshots:
        cluster_key = item.cluster_id or "UNCLUSTERED"
        strategy_key = item.strategy_id or "unknown_strategy"
        cluster_exposure[cluster_key] = round(cluster_exposure.get(cluster_key, 0.0) + float(item.notional or 0), 4)
        strategy_exposure[strategy_key] = round(strategy_exposure.get(strategy_key, 0.0) + float(item.notional or 0), 4)

    alerts_window = _now() - timedelta(hours=24)
    risk_alerts = (
        db.query(UserExecutionIntent.gate_decision, func.count(UserExecutionIntent.id))
        .filter(UserExecutionIntent.created_at >= alerts_window, UserExecutionIntent.gate_decision != "ALLOW")
        .group_by(UserExecutionIntent.gate_decision)
        .all()
    )

    return {
        "timestamp": _now(),
        "total_exposure": total_exposure,
        "cluster_exposure": cluster_exposure,
        "strategy_exposure": strategy_exposure,
        "drawdown_monitor": {
            "note": "Portfolio drawdown kontrolü preview gate sırasında aktif.",
            "lookback_days": 7,
        },
        "risk_alerts": [{"gate_decision": item[0], "count": int(item[1])} for item in risk_alerts],
    }


@router.get("/strategy-allocation", response_model=list[StrategyAllocationResponse])
def strategy_allocation_dashboard(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = list_strategy_allocation_dashboard_rows(db)
    return [StrategyAllocationResponse.model_validate(row) for row in rows]


@router.get("/strategy-allocation/summary", response_model=StrategyAllocationSummaryResponse)
def strategy_allocation_summary(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    summary = get_strategy_allocation_summary(db)
    return StrategyAllocationSummaryResponse(**summary)


@router.post("/strategy-allocation/snapshots", response_model=StrategyAllocationSnapshotCreateResponse | StrategyAllocationActionEnvelope)
def strategy_allocation_snapshot_create(
    payload: StrategyAllocationReasonNoteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    reason_note = _require_reason_note(payload.reason_note)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="snapshot_create",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump()},
            target_type="snapshot",
            target_id="new_snapshot",
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Snapshot isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    snapshot = _build_snapshot_payload(db, created_by=str(current_user.id), reason_note=reason_note)
    _write_allocation_log(
        db,
        admin_id=current_user.id,
        action_type="strategy_allocation_snapshot_create",
        strategy_id="*",
        previous_state=None,
        new_state=None,
        reason_code="SNAPSHOT_CREATED",
        reason_detail=reason_note,
        payload={"snapshot_id": snapshot.get("snapshot_id"), "strategy_count": snapshot.get("strategy_count")},
    )
    return StrategyAllocationSnapshotCreateResponse(
        status="success",
        message="Snapshot oluşturuldu",
        snapshot=snapshot,
        trace_id=snapshot.get("snapshot_id"),
    )


@router.get("/strategy-allocation/snapshots", response_model=StrategyAllocationSnapshotsResponse)
def strategy_allocation_snapshots(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = (
        db.query(StrategyAllocationSnapshot)
        .order_by(StrategyAllocationSnapshot.created_at.desc())
        .limit(100)
        .all()
    )
    mapped = [
        {
            "snapshot_id": row.snapshot_id,
            "created_at": row.created_at,
            "created_by": str(row.created_by),
            "reason_note": row.reason_note,
            "strategy_count": int(row.strategy_count or 0),
            "total_weight": float(row.total_weight or 0),
            "total_capital": float(row.total_capital or 0),
            "used_capital": float(row.used_capital or 0),
            "source_request_id": row.source_request_id,
            "restored_at": row.restored_at,
            "restored_by": str(row.restored_by) if row.restored_by else None,
        }
        for row in rows
    ]
    return StrategyAllocationSnapshotsResponse(rows=mapped)


@router.post("/strategy-allocation/snapshots/{snapshot_id}/restore", response_model=StrategyAllocationActionEnvelope)
def strategy_allocation_snapshot_restore(
    snapshot_id: str,
    payload: StrategyAllocationSnapshotRestoreRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    reason_note = _require_reason_note(payload.reason_note)
    expected_revisions = {str(k): _coerce_expected_revision(v, field_name=f"expected_revisions[{k}]") for k, v in (payload.expected_revisions or {}).items()}
    _validate_global_revision_scope(db, expected_revisions, action_type="snapshot_restore")

    snapshot_row = _get_snapshot_or_404(db, snapshot_id)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")

    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="snapshot_restore",
            current_user=current_user,
            reason_note=reason_note,
            payload={
                "snapshot_id": snapshot_id,
                "body": payload.model_dump(),
                "revision_context": {"expected_revisions": expected_revisions},
            },
            target_type="snapshot",
            target_id=snapshot_id,
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Restore isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    restore_result = _restore_snapshot_to_allocation(
        db,
        snapshot_row=snapshot_row,
        actor_id=str(current_user.id),
        reason_note=reason_note,
        related_request_id=None,
    )
    return StrategyAllocationActionEnvelope(
        status="success",
        message=(
            f"Snapshot restore tamamlandı: {snapshot_id} "
            f"(invalidated_pending_requests={restore_result.get('invalidated_pending_requests', 0)})"
        ),
        trace_id=str(restore_result.get("trace_id") or f"restore_{snapshot_id}"),
        summary=StrategyAllocationSummaryResponse(**(restore_result.get("summary") or {})),
    )


@router.get("/strategy-allocation/export")
def strategy_allocation_export(
    format: str = "json",
    reason_note: str | None = None,
    related_request_id: str | None = None,
    snapshot_id: str | None = None,
    selected_strategy_ids: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    selected_ids = [item.strip() for item in str(selected_strategy_ids or "").split(",") if item.strip()]
    rows = list_strategy_allocation_dashboard_rows(db, limit=500)
    if selected_ids:
        rows = [item for item in rows if str(item.get("strategy_id")) in set(selected_ids)]

    summary = get_strategy_allocation_summary(db)
    audit_meta = _resolve_export_meta(
        db,
        current_user=current_user,
        reason_note=reason_note,
        related_request_id=related_request_id,
        snapshot_id=snapshot_id,
        selected_strategy_ids=selected_ids,
    )

    export_payload = {
        "audit_meta": audit_meta,
        "summary": summary,
        "rows": rows,
    }

    fmt = str(format or "json").lower()
    trace_id = _write_allocation_log(
        db,
        admin_id=current_user.id,
        action_type="strategy_allocation_export",
        strategy_id="*",
        previous_state=None,
        new_state=None,
        reason_code=f"EXPORT_{fmt.upper()}",
        reason_detail=str(audit_meta.get("reason_note") or "manual_export"),
        payload={
            "format": fmt,
            "audit_meta": audit_meta,
            "row_count": len(rows),
        },
    )

    if fmt == "json":
        import json

        return Response(
            content=json.dumps(export_payload, default=str, ensure_ascii=False),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="strategy_allocation_export.json"',
                "X-Export-Trace-Id": trace_id,
            },
        )

    if fmt == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["exported_at", audit_meta.get("exported_at")])
        writer.writerow(["exported_by", audit_meta.get("exported_by")])
        writer.writerow(["config_version", audit_meta.get("config_version")])
        writer.writerow(["snapshot_id", audit_meta.get("snapshot_id")])
        writer.writerow(["related_request_id", audit_meta.get("related_request_id")])
        writer.writerow(["source_context", audit_meta.get("source_context")])
        writer.writerow(["reason_note", audit_meta.get("reason_note")])
        writer.writerow([])
        writer.writerow([
            "strategy_id",
            "capital_weight",
            "max_capital",
            "current_capital",
            "state",
            "confidence_score",
            "performance_score",
            "signal_decay",
            "execution_quality_score",
            "exposure_ratio_pct",
            "drawdown_pct",
            "state_reason_code",
        ])
        for row in rows:
            writer.writerow(
                [
                    row.get("strategy_id"),
                    row.get("capital_weight"),
                    row.get("max_capital"),
                    row.get("current_capital"),
                    row.get("state"),
                    row.get("confidence_score"),
                    row.get("performance_score"),
                    row.get("signal_decay"),
                    row.get("execution_quality_score"),
                    row.get("exposure_ratio_pct"),
                    row.get("drawdown_pct"),
                    row.get("state_reason_code"),
                ]
            )

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="strategy_allocation_export.csv"',
                "X-Export-Trace-Id": trace_id,
            },
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format should be json or csv")


@router.post("/strategy-allocation/what-if-simulation", response_model=StrategyAllocationWhatIfResponse)
def strategy_allocation_what_if_simulation(
    payload: StrategyAllocationWhatIfRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    result = _build_what_if_payload(db, strategy_ids=payload.strategy_ids)
    return StrategyAllocationWhatIfResponse(**result)


@router.post("/strategy-allocation/normalize", response_model=StrategyAllocationActionEnvelope)
def strategy_allocation_normalize(
    payload: StrategyAllocationNormalizeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    reason_note = _require_reason_note(payload.reason_note)
    expected_revisions = {str(k): _coerce_expected_revision(v, field_name=f"expected_revisions[{k}]") for k, v in (payload.expected_revisions or {}).items()}
    _validate_global_revision_scope(db, expected_revisions, action_type="normalize")

    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="normalize",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump()},
            target_type="allocation_set",
            target_id="global",
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Normalize isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    try:
        result = normalize_strategy_allocations(
            db,
            actor_id=str(current_user.id),
            change_reason=reason_note,
        )
        trace_id = _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_normalize",
            strategy_id="*",
            previous_state=None,
            new_state=None,
            reason_code="WEIGHT_NORMALIZED",
            reason_detail=reason_note,
            payload=result,
        )
        return StrategyAllocationActionEnvelope(
            status="success",
            message="Weight normalize tamamlandı",
            trace_id=trace_id,
            summary=StrategyAllocationSummaryResponse(**(result.get("summary") or {})),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strategy-allocation", response_model=StrategyAllocationResponse | StrategyAllocationActionEnvelope)
def strategy_allocation_create(
    payload: StrategyAllocationCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    reason_note = _require_reason_note(payload.reason_note)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="create",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump()},
            target_type="strategy",
            target_id=str(payload.strategy_id),
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Create isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    try:
        row = create_strategy_allocation(
            db,
            payload.model_dump(),
            actor_id=str(current_user.id),
            change_reason=reason_note,
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_create",
            strategy_id=row.strategy_id,
            previous_state=None,
            new_state=row.state,
            reason_code="MANUAL_CREATE",
            reason_detail=reason_note,
            payload=payload.model_dump(),
        )
        return StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row, db=db))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/strategy-allocation/{strategy_id}", response_model=StrategyAllocationActionEnvelope)
def strategy_allocation_remove(
    strategy_id: str,
    auto_normalize: bool = True,
    reason_note: str = "",
    expected_revision: int = 0,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    note = _require_reason_note(reason_note)
    revision = _coerce_expected_revision(expected_revision)

    existing = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Strategy bulunamadı: {strategy_id}")

    current_revision = int(getattr(existing, "revision_id", 1) or 1)
    if revision != current_revision:
        _raise_revision_conflict(
            action_type="delete",
            conflicts=[
                {
                    "strategy_id": strategy_id,
                    "expected_revision": revision,
                    "current_revision": current_revision,
                    "reason": "REVISION_MISMATCH",
                }
            ],
        )

    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="delete",
            current_user=current_user,
            reason_note=note,
            payload={
                "strategy_id": strategy_id,
                "auto_normalize": auto_normalize,
                "expected_revision": revision,
                "previous_state": existing.state,
            },
            target_type="strategy",
            target_id=strategy_id,
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Delete isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    try:
        result = delete_strategy_allocation(
            db,
            strategy_id,
            auto_normalize=auto_normalize,
            actor_id=str(current_user.id),
            change_reason=note,
        )
        trace_id = _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_delete",
            strategy_id=strategy_id,
            previous_state=None,
            new_state=None,
            reason_code="MANUAL_DELETE",
            reason_detail=note,
            payload=result,
        )
        return StrategyAllocationActionEnvelope(
            status="success",
            message=f"Strategy silindi: {strategy_id}",
            trace_id=trace_id,
            summary=StrategyAllocationSummaryResponse(**(result.get("summary") or {})),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strategy-allocation/bulk-update")
def strategy_allocation_bulk_update(
    payload: StrategyAllocationBulkUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    reason_note = _require_reason_note(payload.reason_note)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")

    expectations = {
        str(item.strategy_id): _coerce_expected_revision(item.expected_revision, field_name=f"expected_revision[{item.strategy_id}]")
        for item in payload.updates
    }
    conflicts = _validate_revision_expectations(db, expectations, action_type="bulk_update")
    if conflicts:
        _raise_revision_conflict(action_type="bulk_update", conflicts=conflicts)

    selected_rows = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id.in_(list(expectations.keys()))).all()
    target_weight_map: dict[str, float] = {}
    for item in payload.updates:
        if item.capital_weight is None:
            continue
        target_weight_map[str(item.strategy_id)] = float(item.capital_weight)
    projection_preview = build_projection_from_rows(selected_rows, target_weights=target_weight_map)

    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="bulk_update",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump(), "projection_preview": projection_preview},
            target_type="allocation_set",
            target_id="bulk",
        )
        return {
            "status": "pending_approval",
            "message": f"Bulk update isteği onaya gönderildi: {request_row['request_id']}",
            "trace_id": request_row["request_id"],
            "updated_count": 0,
            "updated_rows": [],
            "summary": {},
            "enforced_reduce_rows": [],
        }

    try:
        result = bulk_update_strategy_allocations(
            db,
            payload.model_dump(),
            actor_id=str(current_user.id),
            change_reason=reason_note,
        )
        trace_id = _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_bulk_update",
            strategy_id="*",
            previous_state=None,
            new_state=None,
            reason_code="MANUAL_BULK_UPDATE",
            reason_detail=reason_note,
            payload={
                "updated_count": result.get("updated_count", 0),
                "updated_ids": [row.strategy_id for row in (result.get("updated_rows") or [])],
                "auto_normalize": payload.auto_normalize,
                "enforced_reduce_rows": result.get("enforced_reduce_rows") or [],
                "projection_preview": result.get("projection_preview") or projection_preview,
            },
        )
        return {
            "status": "success",
            "message": f"Bulk update tamamlandı ({result.get('updated_count', 0)} strategy)",
            "trace_id": trace_id,
            "updated_count": result.get("updated_count", 0),
            "updated_rows": [
                StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row, db=db)).model_dump()
                for row in (result.get("updated_rows") or [])
            ],
            "summary": result.get("summary") or {},
            "enforced_reduce_rows": result.get("enforced_reduce_rows") or [],
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strategy-allocation/{strategy_id}/throttle-toggle", response_model=StrategyAllocationResponse | StrategyAllocationActionEnvelope)
def strategy_allocation_throttle_toggle(
    strategy_id: str,
    payload: StrategyAllocationThrottleToggleRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    reason_note = _require_reason_note(payload.reason_note)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")

    existing = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Strategy bulunamadı: {strategy_id}")

    expected_revision = _coerce_expected_revision(payload.expected_revision)
    current_revision = int(getattr(existing, "revision_id", 1) or 1)
    if expected_revision != current_revision:
        _raise_revision_conflict(
            action_type="throttle_toggle",
            conflicts=[
                {
                    "strategy_id": strategy_id,
                    "expected_revision": expected_revision,
                    "current_revision": current_revision,
                    "reason": "REVISION_MISMATCH",
                }
            ],
        )

    previous_state = existing.state if existing else None
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="throttle_toggle",
            current_user=current_user,
            reason_note=reason_note,
            payload={"strategy_id": strategy_id, "previous_state": previous_state, "body": payload.model_dump()},
            target_type="strategy",
            target_id=strategy_id,
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Throttle toggle isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    try:
        row = toggle_strategy_throttle(
            db,
            strategy_id,
            payload.model_dump(),
            actor_id=str(current_user.id),
            change_reason=reason_note,
        )
        _write_allocation_log(
            db,
            admin_id=current_user.id,
            action_type="strategy_allocation_throttle_toggle",
            strategy_id=strategy_id,
            previous_state=previous_state,
            new_state=row.state,
            reason_code="MANUAL_THROTTLE_TOGGLE",
            reason_detail=reason_note,
            payload=payload.model_dump(),
        )
        return StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row, db=db))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/strategy-allocation/state-history", response_model=StrategyAllocationStateHistoryResponse)
def strategy_allocation_state_history(
    limit: int = 100,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    safe_limit = max(min(limit, 200), 1)
    rows = (
        db.query(ManualOverrideLog)
        .filter(
            ManualOverrideLog.action_type.in_(
                [
                    "strategy_allocation_state_change",
                    "strategy_allocation_throttle_toggle",
                    "strategy_allocation_create",
                    "strategy_allocation_delete",
                    "strategy_allocation_bulk_update",
                    "strategy_allocation_normalize",
                    "strategy_allocation_drift_override",
                    "strategy_allocation_snapshot_create",
                    "strategy_allocation_snapshot_restore",
                    "strategy_allocation_export",
                ]
            )
        )
        .order_by(ManualOverrideLog.timestamp.desc())
        .limit(safe_limit)
        .all()
    )
    mapped = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        mapped.append(
            StrategyAllocationStateHistoryEntry(
                trace_id=row.override_id,
                strategy_id=str(payload.get("strategy_id") or "*"),
                action_type=str(row.action_type),
                previous_state=payload.get("previous_state"),
                new_state=payload.get("new_state"),
                reason_code=payload.get("reason_code"),
                reason_detail=payload.get("reason_detail"),
                admin_id=str(row.admin_id),
                timestamp=row.timestamp,
            )
        )

    return StrategyAllocationStateHistoryResponse(rows=mapped)


@router.get("/strategy-allocation/approval-requests", response_model=StrategyAllocationApprovalRequestsResponse)
def strategy_allocation_approval_requests(
    status_filter: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    query = db.query(StrategyAllocationApprovalRequest).filter(StrategyAllocationApprovalRequest.request_type.like(f"{ALLOCATION_REQUEST_PREFIX}:%"))
    if status_filter:
        query = query.filter(StrategyAllocationApprovalRequest.status == str(status_filter))
    rows = query.order_by(StrategyAllocationApprovalRequest.created_at.desc()).limit(200).all()
    mapped = [_map_decision_request_to_allocation_item(item) for item in rows]
    return StrategyAllocationApprovalRequestsResponse(rows=mapped)


@router.post("/strategy-allocation/approval-requests/{request_id}/approve")
def strategy_allocation_approval_approve(
    request_id: str,
    payload: StrategyAllocationReasonNoteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")

    request_model = (
        db.query(StrategyAllocationApprovalRequest)
        .filter(
            StrategyAllocationApprovalRequest.request_id == request_id,
            StrategyAllocationApprovalRequest.request_type.like(f"{ALLOCATION_REQUEST_PREFIX}:%"),
        )
        .first()
    )
    if not request_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found")
    if request_model.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval request already processed")
    if request_model.expires_at and request_model.expires_at < _now():
        request_model.status = "expired"
        request_model.reviewed_at = _now()
        db.add(request_model)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval request expired")

    review_note = _require_reason_note(payload.reason_note)
    request_row = _map_decision_request_to_allocation_item(request_model)
    action_type = str(request_row.get("action_type") or "")
    revision_expectations = _extract_revision_expectations_for_request(action_type, request_row.get("payload") or {})
    if revision_expectations:
        if action_type in {"normalize", "snapshot_restore"}:
            try:
                _validate_global_revision_scope(db, revision_expectations, action_type=action_type)
                conflicts = []
            except HTTPException as exc:
                if isinstance(exc.detail, dict):
                    conflicts = exc.detail.get("conflicts") or []
                else:
                    raise
        else:
            conflicts = _validate_revision_expectations(db, revision_expectations, action_type=action_type)

        if conflicts:
            payload_data = request_model.payload if isinstance(request_model.payload, dict) else {}
            payload_data["stale_state"] = "STALE"
            payload_data["stale_reason_code"] = "REVISION_MISMATCH"
            payload_data["stale_conflicts"] = conflicts
            request_model.payload = payload_data
            request_model.status = "requires_review"
            request_model.stale_state = "STALE"
            request_model.stale_reason_code = "REVISION_MISMATCH"
            request_model.stale_conflicts = conflicts
            request_model.review_note = review_note
            request_model.reviewed_at = _now()
            db.add(request_model)
            db.commit()
            _raise_revision_conflict(action_type=action_type, conflicts=conflicts, request_id=request_id)

    result = _execute_allocation_approval_request(db=db, current_user=current_user, request_row=request_row)
    request_model.status = "approved"
    request_model.approved_by = str(current_user.id)
    request_model.stale_state = None
    request_model.stale_reason_code = None
    request_model.stale_conflicts = []
    request_model.review_note = review_note
    request_model.reviewed_at = _now()
    db.add(request_model)
    db.commit()
    return result


@router.post("/strategy-allocation/approval-requests/{request_id}/reject", response_model=StrategyAllocationActionEnvelope)
def strategy_allocation_approval_reject(
    request_id: str,
    payload: StrategyAllocationReasonNoteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")

    request_model = (
        db.query(StrategyAllocationApprovalRequest)
        .filter(
            StrategyAllocationApprovalRequest.request_id == request_id,
            StrategyAllocationApprovalRequest.request_type.like(f"{ALLOCATION_REQUEST_PREFIX}:%"),
        )
        .first()
    )
    if not request_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found")
    if request_model.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval request already processed")

    request_model.status = "rejected"
    request_model.rejected_by = str(current_user.id)
    request_model.review_note = _require_reason_note(payload.reason_note)
    request_model.reviewed_at = _now()
    db.add(request_model)
    db.commit()
    return StrategyAllocationActionEnvelope(
        status="rejected",
        message=f"Approval request reddedildi: {request_id}",
        trace_id=request_id,
        summary=None,
    )


@router.put("/strategy-allocation/{strategy_id}", response_model=StrategyAllocationResponse | StrategyAllocationActionEnvelope)
def strategy_allocation_update(
    strategy_id: str,
    payload: StrategyAllocationUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    reason_note = _require_reason_note(payload.reason_note)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")

    existing = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Strategy bulunamadı: {strategy_id}")

    expected_revision = _coerce_expected_revision(payload.expected_revision)
    current_revision = int(getattr(existing, "revision_id", 1) or 1)
    if expected_revision != current_revision:
        _raise_revision_conflict(
            action_type="update",
            conflicts=[
                {
                    "strategy_id": strategy_id,
                    "expected_revision": expected_revision,
                    "current_revision": current_revision,
                    "reason": "REVISION_MISMATCH",
                }
            ],
        )

    previous_state = existing.state
    request_payload = payload.model_dump(exclude_none=True)
    request_payload_for_queue = dict(request_payload)
    request_payload.pop("expected_revision", None)
    projection_preview = build_projection_from_rows(
        [existing],
        target_weights={strategy_id: float(request_payload.get("capital_weight"))}
        if request_payload.get("capital_weight") is not None
        else {},
    )

    if role == "admin":
        request_row = _queue_allocation_approval_request(
            db=db,
            action_type="update",
            current_user=current_user,
            reason_note=reason_note,
            payload={
                "strategy_id": strategy_id,
                "previous_state": previous_state,
                "body": request_payload_for_queue,
                "projection_preview": projection_preview,
            },
            target_type="strategy",
            target_id=strategy_id,
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Update isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    try:
        row = update_strategy_allocation(
            db,
            strategy_id,
            request_payload,
            actor_id=str(current_user.id),
            change_reason=reason_note,
        )
        row_payload = build_strategy_allocation_row_payload(row, db=db, requested_state=request_payload.get("state"))
        if previous_state and previous_state != row.state:
            _write_allocation_log(
                db,
                admin_id=current_user.id,
                action_type="strategy_allocation_state_change",
                strategy_id=strategy_id,
                previous_state=previous_state,
                new_state=row.state,
                reason_code=row_payload.get("state_reason_code"),
                reason_detail=reason_note,
                payload={
                    **request_payload,
                    "projection_preview": projection_preview,
                },
            )
        if row_payload.get("is_drift_override"):
            _write_allocation_log(
                db,
                admin_id=current_user.id,
                action_type="strategy_allocation_drift_override",
                strategy_id=strategy_id,
                previous_state=request_payload.get("state"),
                new_state=row.state,
                reason_code=row_payload.get("state_reason_code"),
                reason_detail=reason_note,
                payload={"requested_state": request_payload.get("state"), "resolved_state": row.state},
            )

        return StrategyAllocationResponse.model_validate(row_payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strategy-allocation/rebalance-suggestions", response_model=StrategyAllocationRebalanceSuggestionResponse)
def strategy_allocation_rebalance_suggestions(
    payload: StrategyAllocationRebalanceSuggestRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    result = generate_rebalance_suggestions(db, strategy_ids=payload.strategy_ids)
    return StrategyAllocationRebalanceSuggestionResponse(**result)
