from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import AdminPositionsMonitorResponse, PositionStateResponse
from services.position_management_service import calculate_forced_liquidation_risk, list_all_open_positions

router = APIRouter(prefix="/admin", tags=["admin_positions_monitor"])


@router.get("/positions-monitor", response_model=AdminPositionsMonitorResponse)
def positions_monitor(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = list_all_open_positions(db)

    cluster_exposure: dict[str, float] = {}
    forced_risk_values: list[float] = []
    payload_rows: list[PositionStateResponse] = []
    for row in rows:
        exposure = abs(float(row.size or 0) * float(row.current_price or 0) * max(int(row.leverage or 1), 1))
        key = row.cluster_id or "UNCLUSTERED"
        cluster_exposure[key] = round(cluster_exposure.get(key, 0.0) + exposure, 4)
        forced_risk_values.append(calculate_forced_liquidation_risk(row))
        payload_rows.append(
            PositionStateResponse(
                position_id=row.position_id,
                symbol=row.symbol,
                size=float(row.size or 0),
                entry_price=float(row.entry_price or 0),
                current_price=float(row.current_price or 0),
                unrealized_pnl=float(row.unrealized_pnl or 0),
                leverage=int(row.leverage or 1),
                strategy_id=row.strategy_id,
                cluster_id=row.cluster_id,
                status=row.status,
                updated_at=row.updated_at,
            )
        )

    forced_liquidation_risk = round(sum(forced_risk_values) / len(forced_risk_values), 4) if forced_risk_values else 0.0
    if forced_liquidation_risk >= 70:
        risk_level = "HIGH"
    elif forced_liquidation_risk >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return AdminPositionsMonitorResponse(
        generated_at=datetime.now(timezone.utc),
        open_positions=payload_rows,
        cluster_exposure=cluster_exposure,
        risk_level=risk_level,
        forced_liquidation_risk=forced_liquidation_risk,
    )
