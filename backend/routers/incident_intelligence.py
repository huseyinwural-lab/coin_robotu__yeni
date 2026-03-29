from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.incident_intelligence_service import (
    build_correlation_graph,
    build_incident_kpis,
    build_incident_predictions,
    build_incident_timeline,
    build_weekly_incident_summary,
    list_intelligence_anomalies,
    list_intelligence_incidents,
    run_incident_intelligence_cycle,
    update_incident_intelligence_state,
)


router = APIRouter(prefix="/admin/incident-intelligence", tags=["incident_intelligence"])


class IncidentStateUpdateRequest(BaseModel):
    state: str = Field(min_length=2, max_length=40)
    owner: str | None = None
    note: str | None = None


@router.post("/engine/run")
def run_incident_engine(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    window_minutes: int = Query(default=60, ge=5, le=1440),
):
    _ = current_admin
    return run_incident_intelligence_cycle(db, window_minutes=window_minutes)


@router.get("/anomalies")
def get_anomalies(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=300),
    state: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    severity: str | None = Query(default=None),
):
    _ = current_admin
    return {"items": list_intelligence_anomalies(db, limit=limit, state=state, domain=domain, severity=severity)}


@router.get("/incidents")
def get_incidents(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=300),
    state: str | None = Query(default=None),
):
    _ = current_admin
    return {"items": list_intelligence_incidents(db, limit=limit, state=state)}


@router.get("/incidents/{incident_id}")
def get_incident_detail(incident_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    incidents = {item["incident_id"]: item for item in list_intelligence_incidents(db, limit=300)}
    incident = incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident_not_found")
    return {"incident": incident, "timeline": build_incident_timeline(db, incident_id)}


@router.patch("/incidents/{incident_id}")
def patch_incident_state(
    incident_id: str,
    payload: IncidentStateUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    try:
        incident = update_incident_intelligence_state(db, incident_id=incident_id, state=payload.state, owner=payload.owner, note=payload.note)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if detail == "incident_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"incident": incident}


@router.get("/kpis")
def get_incident_kpis(current_admin: User = Depends(require_admin), db: Session = Depends(get_db), days: int = Query(default=7, ge=1, le=90)):
    _ = current_admin
    return build_incident_kpis(db, days=days)


@router.get("/weekly-summary")
def get_weekly_summary(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return build_weekly_incident_summary(db)


@router.get("/graph")
def get_correlation_graph(current_admin: User = Depends(require_admin), db: Session = Depends(get_db), limit: int = Query(default=60, ge=10, le=300)):
    _ = current_admin
    return build_correlation_graph(db, limit=limit)


@router.get("/predictions")
def get_incident_predictions(current_admin: User = Depends(require_admin), db: Session = Depends(get_db), days: int = Query(default=14, ge=1, le=90)):
    _ = current_admin
    return build_incident_predictions(db, days=days)
