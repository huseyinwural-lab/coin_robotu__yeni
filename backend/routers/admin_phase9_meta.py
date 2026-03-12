from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import PortfolioExposureSnapshot, RiskCluster, User, UserExecutionIntent
from schemas import (
    PortfolioRiskLimitsResponse,
    PortfolioRiskLimitsUpdate,
    RiskClusterResponse,
    RiskClusterUpsertRequest,
    StrategyAllocationResponse,
    StrategyAllocationUpdateRequest,
)
from services.meta_strategy_engine_service import list_strategy_allocations, update_strategy_allocation
from services.portfolio_risk_service import list_risk_clusters, load_portfolio_risk_limits, save_portfolio_risk_limits, upsert_risk_cluster

router = APIRouter(prefix="/admin", tags=["admin_phase9_meta"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    rows = list_strategy_allocations(db)
    return [StrategyAllocationResponse.model_validate(row) for row in rows]


@router.put("/strategy-allocation/{strategy_id}", response_model=StrategyAllocationResponse)
def strategy_allocation_update(
    strategy_id: str,
    payload: StrategyAllocationUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    row = update_strategy_allocation(db, strategy_id, payload.model_dump(exclude_none=True))
    return StrategyAllocationResponse.model_validate(row)
