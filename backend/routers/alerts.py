from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import SystemAlert, User
from schemas import SystemAlertResponse
from services.system_alert_service import list_system_alerts, update_system_alert_status

router = APIRouter(prefix="/admin/system-alerts", tags=["system_alerts"])


@router.get("", response_model=list[SystemAlertResponse])
def get_system_alerts(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default="open"),
    limit: int = 50,
):
    _ = current_admin
    status_value = status_filter if status_filter != "all" else None
    return list_system_alerts(db, status=status_value, limit=limit)


@router.post("/{alert_id}/ack", response_model=SystemAlertResponse)
def ack_system_alert(alert_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    alert = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")
    return update_system_alert_status(db, alert, status="ack")


@router.post("/{alert_id}/resolve", response_model=SystemAlertResponse)
def resolve_system_alert(alert_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    alert = db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")
    return update_system_alert_status(db, alert, status="resolved")
