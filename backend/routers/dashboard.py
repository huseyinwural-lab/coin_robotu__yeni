from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import get_current_user
from models import AuditLog, BotProfile, RiskPolicy, StrategyTemplate, User, UserRole

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        data = {
            "users": db.query(User).count(),
            "active_bots": db.query(BotProfile).filter(BotProfile.is_enabled.is_(True)).count(),
            "risk_policies": db.query(RiskPolicy).count(),
            "strategy_templates": db.query(StrategyTemplate).count(),
            "critical_audits": db.query(AuditLog).filter(AuditLog.severity == "critical").count(),
        }
    else:
        data = {
            "bots": db.query(BotProfile).filter(BotProfile.user_id == current_user.id).count(),
            "active_bots": db.query(BotProfile)
            .filter(BotProfile.user_id == current_user.id, BotProfile.is_enabled.is_(True))
            .count(),
            "risk_policies": db.query(RiskPolicy).filter(RiskPolicy.user_id == current_user.id).count(),
            "strategy_templates": db.query(StrategyTemplate).filter(StrategyTemplate.is_active.is_(True)).count(),
            "mode": "mock_execution",
        }

    heartbeat = datetime.now(timezone.utc).isoformat()
    redis_client.set(f"dashboard:heartbeat:{current_user.id}", heartbeat)
    return {"role": current_user.role.value, "metrics": data, "heartbeat": heartbeat}