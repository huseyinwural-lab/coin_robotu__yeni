from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import get_current_user, is_admin_role
from models import AuditLog, BotProfile, PaperPosition, RiskPolicy, StrategyTemplate, SystemAlert, User
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    monitoring = pipeline_runtime.monitoring_snapshot(db)
    if is_admin_role(current_user.role):
        data = {
            "users": db.query(User).count(),
            "active_bots": db.query(BotProfile).filter(BotProfile.is_enabled.is_(True)).count(),
            "running_bots": db.query(BotProfile).filter(BotProfile.is_running.is_(True)).count(),
            "risk_policies": db.query(RiskPolicy).count(),
            "strategy_templates": db.query(StrategyTemplate).count(),
            "critical_audits": db.query(AuditLog).filter(AuditLog.severity == "critical").count(),
            "open_positions": monitoring["open_positions"],
            "signals_5m": monitoring["signal_rate_last_5m"],
            "paper_trades_5m": monitoring["paper_trades_last_5m"],
            "websocket_status": monitoring["websocket_status"],
        }
        alerts_rows = (
            db.query(SystemAlert)
            .filter(SystemAlert.status.in_(["open", "ack"]))
            .order_by(SystemAlert.last_triggered_at.desc())
            .limit(5)
            .all()
        )
        alerts_payload = [
            {
                "id": row.id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "message": row.message,
                "status": row.status,
                "occurrences": row.occurrences,
                "last_triggered_at": row.last_triggered_at,
                "details": row.details,
            }
            for row in alerts_rows
        ]
    else:
        data = {
            "bots": db.query(BotProfile).filter(BotProfile.user_id == current_user.id).count(),
            "active_bots": db.query(BotProfile)
            .filter(BotProfile.user_id == current_user.id, BotProfile.is_enabled.is_(True))
            .count(),
            "running_bots": db.query(BotProfile)
            .filter(BotProfile.user_id == current_user.id, BotProfile.is_running.is_(True))
            .count(),
            "risk_policies": db.query(RiskPolicy).filter(RiskPolicy.user_id == current_user.id).count(),
            "strategy_templates": db.query(StrategyTemplate).filter(StrategyTemplate.is_active.is_(True)).count(),
            "open_positions": db.query(PaperPosition)
            .filter(PaperPosition.user_id == current_user.id, PaperPosition.status == "open")
            .count(),
            "mode": "paper_execution",
        }
        alerts_payload = []

    heartbeat = datetime.now(timezone.utc).isoformat()
    redis_client.set(f"dashboard:heartbeat:{current_user.id}", heartbeat)
    return {"role": current_user.role.value, "metrics": data, "heartbeat": heartbeat, "alerts": alerts_payload}