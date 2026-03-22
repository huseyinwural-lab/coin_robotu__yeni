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

    mapped_rows = []
    total_return_delta = 0.0
    total_risk_delta = 0.0
    for row in rows:
        delta = float(row.get("delta") or 0)
        confidence = float(row.get("confidence") or 0)
        performance_norm = float(row.get("performance_norm") or 0)
        decay = float(row.get("decay") or 0)

        projected_return_delta_pct = round(delta * (performance_norm * 40 + confidence * 20), 4)
        projected_risk_delta_pct = round(delta * ((1 - confidence) * 25 + decay * 15), 4)

        total_return_delta += projected_return_delta_pct
        total_risk_delta += projected_risk_delta_pct

        mapped_rows.append(
            {
                "strategy_id": row.get("strategy_id"),
                "current_weight": float(row.get("current_weight") or 0),
                "suggested_weight": float(row.get("suggested_weight") or 0),
                "weight_delta": round(delta, 8),
                "confidence": confidence,
                "performance_norm": performance_norm,
                "decay": decay,
                "projected_return_delta_pct": projected_return_delta_pct,
                "projected_risk_delta_pct": projected_risk_delta_pct,
            }
        )

    return {
        "status": "success",
        "message": "What-if preview hazır (read-only)",
        "trace_id": suggestion.get("trace_id") or f"alloc_whatif_{uuid4().hex[:10]}",
        "read_only": True,
        "selection_count": int(suggestion.get("selection_count") or 0),
        "projected_portfolio_return_delta_pct": round(total_return_delta, 4),
        "projected_portfolio_risk_delta_pct": round(total_risk_delta, 4),
        "rows": mapped_rows,
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
        result = normalize_strategy_allocations(db)
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
        row = create_strategy_allocation(db, payload.get("body") or {})
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
        row = update_strategy_allocation(db, strategy_id, body)
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
            payload=body,
        )
        return StrategyAllocationResponse.model_validate(row_payload)

    if action_type == "delete":
        strategy_id = str(payload.get("strategy_id") or "")
        result = delete_strategy_allocation(db, strategy_id, auto_normalize=bool(payload.get("auto_normalize", True)))
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
        result = bulk_update_strategy_allocations(db, payload.get("body") or {})
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
        row = toggle_strategy_throttle(db, strategy_id, payload.get("body") or {})
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
        result = normalize_strategy_allocations(db)
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
        row = create_strategy_allocation(db, payload.model_dump())
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
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    note = _require_reason_note(reason_note)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role read-only")
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            action_type="delete",
            current_user=current_user,
            reason_note=note,
            payload={"strategy_id": strategy_id, "auto_normalize": auto_normalize},
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Delete isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    try:
        result = delete_strategy_allocation(db, strategy_id, auto_normalize=auto_normalize)
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
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            action_type="bulk_update",
            current_user=current_user,
            reason_note=reason_note,
            payload={"body": payload.model_dump()},
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
        result = bulk_update_strategy_allocations(db, payload.model_dump())
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
        row = toggle_strategy_throttle(db, strategy_id, payload.model_dump())
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

    request_row["status"] = "approved"
    request_row["approved_by"] = str(current_user.id)
    request_row["review_note"] = _require_reason_note(payload.reason_note)
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
    previous_state = existing.state if existing else None
    request_payload = payload.model_dump(exclude_none=True)
    if role == "admin":
        request_row = _queue_allocation_approval_request(
            action_type="update",
            current_user=current_user,
            reason_note=reason_note,
            payload={
                "strategy_id": strategy_id,
                "previous_state": previous_state,
                "body": request_payload,
            },
        )
        return StrategyAllocationActionEnvelope(
            status="pending_approval",
            message=f"Update isteği onaya gönderildi: {request_row['request_id']}",
            trace_id=request_row["request_id"],
            summary=None,
        )

    try:
        row = update_strategy_allocation(db, strategy_id, request_payload)
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
                payload=request_payload,
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
