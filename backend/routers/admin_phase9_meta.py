import csv
from io import StringIO
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import ManualOverrideLog, PortfolioExposureSnapshot, StrategyAllocation, User, UserExecutionIntent, UserRole
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
    toggle_strategy_throttle,
    update_strategy_allocation,
)
from services.portfolio_risk_service import list_risk_clusters, load_portfolio_risk_limits, save_portfolio_risk_limits, upsert_risk_cluster

router = APIRouter(prefix="/admin", tags=["admin_phase9_meta"])
_ALLOCATION_APPROVAL_REQUESTS: dict[str, dict] = {}
_ALLOCATION_SNAPSHOTS: dict[str, dict] = {}


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

    if action_type == "normalize":
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


def _mark_request_requires_review(request_row: dict, *, review_note: str, conflicts: list[dict]) -> None:
    request_row["status"] = "requires_review"
    request_row["stale_state"] = "STALE"
    request_row["stale_reason_code"] = "REVISION_MISMATCH"
    request_row["stale_conflicts"] = conflicts
    request_row["review_note"] = review_note
    request_row["reviewed_at"] = _now()


def _queue_allocation_approval_request(
    *,
    action_type: str,
    current_user: User,
    reason_note: str,
    payload: dict,
) -> dict:
    request_id = f"alloc_req_{uuid4().hex[:12]}"
    now = _now()
    row = {
        "request_id": request_id,
        "action_type": action_type,
        "status": "pending",
        "requested_by": str(current_user.id),
        "requested_role": _role_name(current_user),
        "reason_note": reason_note,
        "created_at": now,
        "expires_at": now + timedelta(hours=24),
        "payload": payload,
        "approved_by": None,
        "rejected_by": None,
        "review_note": None,
    }
    _ALLOCATION_APPROVAL_REQUESTS[request_id] = row
    return row


def _build_snapshot_payload(db: Session, *, created_by: str, reason_note: str) -> dict:
    rows = list_strategy_allocation_dashboard_rows(db, limit=500)
    summary = get_strategy_allocation_summary(db)
    snapshot_id = f"alloc_snapshot_{uuid4().hex[:12]}"
    payload = {
        "snapshot_id": snapshot_id,
        "created_at": _now(),
        "created_by": created_by,
        "reason_note": reason_note,
        "strategy_count": len(rows),
        "total_weight": float(summary.get("total_weight") or 0),
        "total_capital": float(summary.get("total_capital") or 0),
        "used_capital": float(summary.get("used_capital") or 0),
        "summary": summary,
        "rows": rows,
    }
    _ALLOCATION_SNAPSHOTS[snapshot_id] = payload
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
            message="Approval sonrası snapshot oluşturuldu",
            snapshot=snapshot,
            trace_id=snapshot.get("snapshot_id"),
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
            action_type="snapshot_create",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump()},
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
    _ = db
    rows = sorted(_ALLOCATION_SNAPSHOTS.values(), key=lambda item: item.get("created_at"), reverse=True)
    return StrategyAllocationSnapshotsResponse(rows=rows)


@router.get("/strategy-allocation/export")
def strategy_allocation_export(
    format: str = "json",
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = list_strategy_allocation_dashboard_rows(db, limit=500)
    summary = get_strategy_allocation_summary(db)
    export_payload = {
        "exported_at": _now().isoformat(),
        "summary": summary,
        "rows": rows,
    }

    fmt = str(format or "json").lower()
    if fmt == "json":
        import json

        return Response(
            content=json.dumps(export_payload, default=str, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="strategy_allocation_export.json"'},
        )

    if fmt == "csv":
        output = StringIO()
        writer = csv.writer(output)
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
            headers={"Content-Disposition": 'attachment; filename="strategy_allocation_export.csv"'},
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
                "action_type": "normalize",
            }
        )
    for strategy_id in sorted(expected_ids - current_ids):
        scope_conflicts.append(
            {
                "strategy_id": strategy_id,
                "expected_revision": expected_revisions.get(strategy_id),
                "current_revision": None,
                "reason": "UNKNOWN_STRATEGY",
                "action_type": "normalize",
            }
        )
    if scope_conflicts:
        _raise_revision_conflict(action_type="normalize", conflicts=scope_conflicts)

    conflicts = _validate_revision_expectations(db, expected_revisions, action_type="normalize")
    if conflicts:
        _raise_revision_conflict(action_type="normalize", conflicts=conflicts)

    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            action_type="normalize",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump()},
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
            action_type="create",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump()},
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
            action_type="delete",
            current_user=current_user,
            reason_note=note,
            payload={
                "strategy_id": strategy_id,
                "auto_normalize": auto_normalize,
                "expected_revision": revision,
                "previous_state": existing.state,
            },
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
            action_type="bulk_update",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump(), "projection_preview": projection_preview},
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
            action_type="throttle_toggle",
            current_user=current_user,
            reason_note=reason_note,
            payload={"strategy_id": strategy_id, "previous_state": previous_state, "body": payload.model_dump()},
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
    _ = db
    rows = list(_ALLOCATION_APPROVAL_REQUESTS.values())
    if status_filter:
        rows = [item for item in rows if str(item.get("status")) == str(status_filter)]
    rows = sorted(rows, key=lambda item: item.get("created_at"), reverse=True)
    return StrategyAllocationApprovalRequestsResponse(rows=rows)


@router.post("/strategy-allocation/approval-requests/{request_id}/approve")
def strategy_allocation_approval_approve(
    request_id: str,
    payload: StrategyAllocationReasonNoteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")

    request_row = _ALLOCATION_APPROVAL_REQUESTS.get(request_id)
    if not request_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found")
    if request_row.get("status") != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval request already processed")
    if request_row.get("expires_at") and request_row.get("expires_at") < _now():
        request_row["status"] = "expired"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval request expired")

    review_note = _require_reason_note(payload.reason_note)
    action_type = str(request_row.get("action_type") or "")
    revision_expectations = _extract_revision_expectations_for_request(action_type, request_row.get("payload") or {})
    if revision_expectations:
        conflicts = _validate_revision_expectations(db, revision_expectations, action_type=action_type)
        if conflicts:
            _mark_request_requires_review(request_row, review_note=review_note, conflicts=conflicts)
            _raise_revision_conflict(action_type=action_type, conflicts=conflicts, request_id=request_id)

    request_row["status"] = "approved"
    request_row["approved_by"] = str(current_user.id)
    request_row["review_note"] = review_note
    request_row["reviewed_at"] = _now()
    return _execute_allocation_approval_request(db=db, current_user=current_user, request_row=request_row)


@router.post("/strategy-allocation/approval-requests/{request_id}/reject", response_model=StrategyAllocationActionEnvelope)
def strategy_allocation_approval_reject(
    request_id: str,
    payload: StrategyAllocationReasonNoteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = db
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")

    request_row = _ALLOCATION_APPROVAL_REQUESTS.get(request_id)
    if not request_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found")
    if request_row.get("status") != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval request already processed")

    request_row["status"] = "rejected"
    request_row["rejected_by"] = str(current_user.id)
    request_row["review_note"] = _require_reason_note(payload.reason_note)
    request_row["reviewed_at"] = _now()
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
            action_type="update",
            current_user=current_user,
            reason_note=reason_note,
            payload={
                "strategy_id": strategy_id,
                "previous_state": previous_state,
                "body": request_payload_for_queue,
                "projection_preview": projection_preview,
            },
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
