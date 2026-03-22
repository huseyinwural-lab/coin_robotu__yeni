from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import ManualOverrideLog, PortfolioExposureSnapshot, StrategyAllocation, User, UserExecutionIntent
from schemas import (
    PortfolioRiskLimitsResponse,
    PortfolioRiskLimitsUpdate,
    RiskClusterResponse,
    RiskClusterUpsertRequest,
    StrategyAllocationActionEnvelope,
    StrategyAllocationBulkUpdateRequest,
    StrategyAllocationCreateRequest,
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
    get_strategy_allocation_summary,
    list_strategy_allocation_dashboard_rows,
    normalize_strategy_allocations,
    toggle_strategy_throttle,
    update_strategy_allocation,
)
from services.portfolio_risk_service import list_risk_clusters, load_portfolio_risk_limits, save_portfolio_risk_limits, upsert_risk_cluster

router = APIRouter(prefix="/admin", tags=["admin_phase9_meta"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


@router.post("/strategy-allocation/normalize", response_model=StrategyAllocationActionEnvelope)
def strategy_allocation_normalize(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
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
            reason_detail="Toplam weight otomatik normalize edildi",
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


@router.post("/strategy-allocation", response_model=StrategyAllocationResponse)
def strategy_allocation_create(
    payload: StrategyAllocationCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
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
            reason_detail="Strategy allocation satırı manuel oluşturuldu",
            payload=payload.model_dump(),
        )
        return StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/strategy-allocation/{strategy_id}", response_model=StrategyAllocationActionEnvelope)
def strategy_allocation_remove(
    strategy_id: str,
    auto_normalize: bool = True,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
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
            reason_detail="Strategy allocation satırı manuel silindi",
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
            reason_detail="Bulk update ile birden fazla strategy güncellendi",
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
                StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row)).model_dump()
                for row in (result.get("updated_rows") or [])
            ],
            "summary": result.get("summary") or {},
            "enforced_reduce_rows": result.get("enforced_reduce_rows") or [],
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/strategy-allocation/{strategy_id}/throttle-toggle", response_model=StrategyAllocationResponse)
def strategy_allocation_throttle_toggle(
    strategy_id: str,
    payload: StrategyAllocationThrottleToggleRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
    previous_state = existing.state if existing else None
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
            reason_detail="Throttle toggle endpointi ile state değiştirildi",
            payload=payload.model_dump(),
        )
        return StrategyAllocationResponse.model_validate(build_strategy_allocation_row_payload(row))
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


@router.put("/strategy-allocation/{strategy_id}", response_model=StrategyAllocationResponse)
def strategy_allocation_update(
    strategy_id: str,
    payload: StrategyAllocationUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(StrategyAllocation).filter(StrategyAllocation.strategy_id == strategy_id).first()
    previous_state = existing.state if existing else None
    request_payload = payload.model_dump(exclude_none=True)
    try:
        row = update_strategy_allocation(db, strategy_id, request_payload)
        row_payload = build_strategy_allocation_row_payload(row, requested_state=request_payload.get("state"))
        if previous_state and previous_state != row.state:
            _write_allocation_log(
                db,
                admin_id=current_user.id,
                action_type="strategy_allocation_state_change",
                strategy_id=strategy_id,
                previous_state=previous_state,
                new_state=row.state,
                reason_code=row_payload.get("state_reason_code"),
                reason_detail=row_payload.get("state_reason_detail"),
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
                reason_detail=row_payload.get("state_reason_detail"),
                payload={"requested_state": request_payload.get("state"), "resolved_state": row.state},
            )

        return StrategyAllocationResponse.model_validate(row_payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
