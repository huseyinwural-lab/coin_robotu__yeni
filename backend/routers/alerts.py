from datetime import datetime, timezone
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import SystemAlert, User
from schemas import AlertChannelConfigUpdateRequest, SystemAlertResponse
from services.alert_channel_service import channel_status, get_alert_config_public, upsert_alert_channel_config
from services.audit_service import create_audit_log
from services.system_alert_service import build_alert_timeline, list_system_alerts, update_system_alert_status
from services.weekly_report_service import compute_next_run, generate_weekly_report, get_latest_report

router = APIRouter(prefix="/admin/system-alerts", tags=["system_alerts"])


@router.get("", response_model=list[SystemAlertResponse])
def get_system_alerts(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default="open"),
    severity: str | None = None,
    alert_type: str | None = None,
    entity_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
):
    _ = current_admin
    status_value = status_filter if status_filter != "all" else None
    parsed_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    parsed_to = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None
    return list_system_alerts(
        db,
        status=status_value,
        severity=severity,
        alert_type=alert_type,
        entity_key=entity_key,
        date_from=parsed_from,
        date_to=parsed_to,
        limit=limit,
    )


@router.get("/export.csv")
def export_system_alerts_csv(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default="all"),
    severity: str | None = None,
    alert_type: str | None = None,
    entity_key: str | None = None,
    limit: int = 2000,
):
    _ = current_admin
    status_value = status_filter if status_filter != "all" else None
    rows = list_system_alerts(
        db,
        status=status_value,
        severity=severity,
        alert_type=alert_type,
        entity_key=entity_key,
        limit=min(limit, 5000),
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "alert_type",
            "severity",
            "status",
            "entity_key",
            "occurrences",
            "message",
            "root_cause_code",
            "created_at",
            "updated_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.alert_type,
                row.severity,
                row.status,
                row.entity_key,
                row.occurrences,
                row.message,
                row.root_cause_code,
                row.created_at.isoformat() if row.created_at else "",
                row.updated_at.isoformat() if row.updated_at else "",
            ]
        )

    buffer.seek(0)
    filename = f"system_alerts_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/bulk-ack")
def bulk_ack(current_admin: User = Depends(require_admin), db: Session = Depends(get_db), payload: dict | None = None):
    payload = payload or {}
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ids_required")
    rows = db.query(SystemAlert).filter(SystemAlert.id.in_(ids)).all()
    for row in rows:
        row.status = "ack"
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    create_audit_log(
        db,
        action="SYSTEM_ALERTS_BULK_ACK",
        entity_type="system_alert",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"count": len(rows), "ids": [row.id for row in rows]},
    )
    return {"count": len(rows), "ids": [row.id for row in rows]}


@router.get("/timeline")
def alerts_timeline(current_admin: User = Depends(require_admin), db: Session = Depends(get_db), days: int = 14):
    _ = current_admin
    return {"days": days, "points": build_alert_timeline(db, days=days)}


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


@router.get("/config")
def get_alert_config(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    next_run = compute_next_run().isoformat()
    return {
        "channels": channel_status(db),
        "config": get_alert_config_public(db),
        "weekly_report_next_run": next_run,
        "timezone": "Europe/Berlin",
    }


@router.post("/config")
def refresh_alert_config(
    payload: AlertChannelConfigUpdateRequest | None = None,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = payload or AlertChannelConfigUpdateRequest()
    changed_fields = [key for key, value in payload.model_dump().items() if value is not None]
    if changed_fields:
        upsert_alert_channel_config(
            db,
            resend_api_key=payload.resend_api_key,
            alert_from=payload.alert_from,
            alert_to=payload.alert_to,
            slack_webhook_url=payload.slack_webhook_url,
        )
        create_audit_log(
            db,
            action="SYSTEM_ALERT_CONFIG_UPDATED",
            entity_type="system_alert_config",
            entity_id="global",
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            severity="info",
            details={"changed_fields": changed_fields},
        )

    next_run = compute_next_run().isoformat()
    return {
        "channels": channel_status(db),
        "config": get_alert_config_public(db),
        "weekly_report_next_run": next_run,
        "timezone": "Europe/Berlin",
    }


@router.post("/reports/run")
def run_weekly_report(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    result = generate_weekly_report(db, trigger_source="manual", generated_by=current_admin.id)
    report = result.get("report")
    return {"report_id": report.report_id, "status": report.status}


@router.get("/reports/latest")
def download_latest_report(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    report = get_latest_report(db)
    if not report or report.status != "generated":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report_not_found")
    return FileResponse(report.storage_path, filename=report.filename, media_type="text/csv")
