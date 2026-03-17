from datetime import datetime, timedelta, timezone
import csv
import io
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import SystemAlert, User
from schemas import AlertChannelConfigUpdateRequest, SystemAlertResponse
from services.alert_channel_service import (
    channel_status,
    get_alert_config_public,
    send_email_alert,
    send_slack_alert,
    upsert_alert_channel_config,
)
from services.audit_service import create_audit_log
from services.system_alert_service import build_alert_timeline, list_system_alerts, update_system_alert_status
from services.weekly_report_service import compute_next_run, generate_weekly_report, get_latest_report
from pydantic import BaseModel

router = APIRouter(prefix="/admin/system-alerts", tags=["system_alerts"])


class AlertTestDeliveryRequest(BaseModel):
    channel: str = "slack"
    severity: str = "WARNING"


def _compute_slo_metrics(rows: list[SystemAlert]) -> dict:
    total = len(rows)
    critical_count = sum(1 for row in rows if (row.severity or "").upper() == "CRITICAL")
    warning_count = sum(1 for row in rows if (row.severity or "").upper() == "WARNING")
    error_rate = round(((critical_count + warning_count) / total), 4) if total else 0.0

    resolved_rows = [row for row in rows if (row.status or "").lower() == "resolved"]
    mttr_minutes = 0.0
    if resolved_rows:
        mttr_minutes = round(
            sum(max((row.updated_at - row.created_at).total_seconds() / 60, 0) for row in resolved_rows)
            / len(resolved_rows),
            2,
        )

    availability_pct = round(max(0.0, 100.0 - (error_rate * 100.0)), 2)
    sla_target_pct = 99.5
    sla_breached = availability_pct < sla_target_pct

    return {
        "total_alerts": total,
        "critical_alerts": critical_count,
        "warning_alerts": warning_count,
        "resolved_alerts": len(resolved_rows),
        "error_rate": error_rate,
        "mttr_minutes": mttr_minutes,
        "availability_pct": availability_pct,
        "sla_target_pct": sla_target_pct,
        "sla_breached": sla_breached,
    }


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


@router.get("/burn-in")
def burn_in_summary(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=30),
):
    _ = current_admin
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(SystemAlert)
        .filter(SystemAlert.created_at >= since)
        .order_by(SystemAlert.created_at.desc())
        .limit(5000)
        .all()
    )

    severity_counter = Counter((row.severity or "INFO").upper() for row in rows)
    status_counter = Counter((row.status or "open").lower() for row in rows)
    type_counter = Counter((row.alert_type or "unknown") for row in rows)

    delivery_email_sent = 0
    delivery_email_failed = 0
    delivery_slack_sent = 0
    delivery_slack_failed = 0
    for row in rows:
        delivery = row.delivery_status or {}
        email_status = ((delivery.get("email") or {}).get("status") or "").upper()
        slack_status = ((delivery.get("slack") or {}).get("status") or "").upper()
        if email_status == "SENT":
            delivery_email_sent += 1
        if email_status in {"FAILED", "RATE_LIMITED", "CONFIG_MISSING", "LIB_MISSING"}:
            delivery_email_failed += 1
        if slack_status == "SENT":
            delivery_slack_sent += 1
        if slack_status in {"FAILED", "RATE_LIMITED", "CONFIG_MISSING", "LIB_MISSING"}:
            delivery_slack_failed += 1

    total = len(rows)
    warning_plus = severity_counter.get("WARNING", 0) + severity_counter.get("CRITICAL", 0)
    critical_ratio = round((severity_counter.get("CRITICAL", 0) / total), 4) if total else 0.0
    ack_rate = round(((status_counter.get("ack", 0) + status_counter.get("resolved", 0)) / total), 4) if total else 0.0

    return {
        "window_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_alerts": total,
        "severity_breakdown": dict(severity_counter),
        "status_breakdown": dict(status_counter),
        "top_alert_types": type_counter.most_common(10),
        "warning_plus_count": warning_plus,
        "critical_ratio": critical_ratio,
        "ack_rate": ack_rate,
        "delivery": {
            "email_sent": delivery_email_sent,
            "email_failed": delivery_email_failed,
            "slack_sent": delivery_slack_sent,
            "slack_failed": delivery_slack_failed,
        },
        "recommendation": (
            "threshold_tuning_required" if critical_ratio > 0.2 else "thresholds_stable"
        ),
    }


@router.get("/slo-sla")
def slo_sla_summary(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=90),
):
    _ = current_admin
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(SystemAlert)
        .filter(SystemAlert.created_at >= since)
        .order_by(SystemAlert.created_at.desc())
        .limit(10000)
        .all()
    )

    metrics = _compute_slo_metrics(rows)

    return {
        "window_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "slo_status": "AT_RISK" if metrics["sla_breached"] else "HEALTHY",
    }


@router.get("/slo-sla-trend")
def slo_sla_trend(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    now = datetime.now(timezone.utc)
    windows = [7, 30, 90]
    trend_points: list[dict] = []
    for window in windows:
        since = now - timedelta(days=window)
        rows = (
            db.query(SystemAlert)
            .filter(SystemAlert.created_at >= since)
            .order_by(SystemAlert.created_at.desc())
            .limit(10000)
            .all()
        )
        metrics = _compute_slo_metrics(rows)
        trend_points.append(
            {
                "window_days": window,
                "availability_pct": metrics["availability_pct"],
                "error_rate": metrics["error_rate"],
                "mttr_minutes": metrics["mttr_minutes"],
                "total_alerts": metrics["total_alerts"],
            }
        )

    return {
        "generated_at": now.isoformat(),
        "points": trend_points,
        "window_labels": ["7d", "30d", "90d"],
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


@router.post("/test-delivery")
def test_delivery(
    payload: AlertTestDeliveryRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    channel = payload.channel.strip().lower()
    severity = payload.severity.strip().upper()
    if channel not in {"email", "slack", "both"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_channel")
    if severity not in {"INFO", "WARNING", "CRITICAL"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_severity")

    subject = f"[TEST] {severity} delivery"
    html = "<p>Test delivery from admin system alerts panel.</p>"
    slack_text = f"*{subject}*\nTest delivery from admin system alerts panel."

    result = {
        "email": {"status": "CHANNEL_DISABLED"},
        "slack": {"status": "CHANNEL_DISABLED"},
    }
    if channel in {"email", "both"}:
        result["email"] = send_email_alert(subject=subject, html_content=html, severity=severity, db=db)
    if channel in {"slack", "both"}:
        result["slack"] = send_slack_alert(message=slack_text, severity=severity, db=db)

    create_audit_log(
        db,
        action="SYSTEM_ALERT_DELIVERY_TEST",
        entity_type="system_alert_delivery",
        entity_id="manual_test",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"channel": channel, "severity": severity, "result": result},
    )

    return {
        "channel": channel,
        "severity": severity,
        "result": result,
        "channel_status": channel_status(db),
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
