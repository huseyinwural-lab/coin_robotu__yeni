from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.pipeline.runtime import pipeline_runtime
from services.pipeline.spot_risk_capital_service import risk_capital_snapshot

router = APIRouter(prefix="/admin/strategy/risk-capital", tags=["admin_strategy_risk_capital"])


@router.get("/status")
def strategy_risk_capital_status(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return risk_capital_snapshot(db, pipeline_runtime.cache, current_admin.id)
