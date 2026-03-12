from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.audit_service import create_audit_log
from services.futures_correlation_service import (
    get_futures_cluster_risk,
    get_futures_correlation_clusters,
    get_futures_correlation_matrix,
)
from services.pipeline.runtime import pipeline_runtime

router = APIRouter(prefix="/admin/futures", tags=["admin_futures_correlation"])


@router.get("/correlation-matrix")
def futures_correlation_matrix(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_correlation_matrix(pipeline_runtime.cache, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_CORRELATION_MATRIX_VIEWED",
        entity_type="futures_correlation_matrix",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"symbol_count": len(payload.get("symbols") or [])},
    )
    return payload


@router.get("/correlation-clusters")
def futures_correlation_clusters(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_correlation_clusters(pipeline_runtime.cache, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_CORRELATION_CLUSTERS_VIEWED",
        entity_type="futures_correlation_clusters",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"cluster_count": len(payload.get("correlation_clusters") or [])},
    )
    return payload


@router.get("/cluster-risk")
def futures_cluster_risk(refresh: bool = False, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    payload = get_futures_cluster_risk(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_CLUSTER_RISK_VIEWED",
        entity_type="futures_cluster_risk",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if len(payload.get("cluster_risk_alerts") or []) > 0 else "info",
        details={
            "cluster_count": len(payload.get("correlation_clusters") or []),
            "alert_count": len(payload.get("cluster_risk_alerts") or []),
        },
    )
    return payload


@router.get("/correlation-cluster-snapshot")
def futures_correlation_cluster_snapshot(
    refresh: bool = False,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = get_futures_cluster_risk(db, pipeline_runtime.cache, current_admin.id, refresh=refresh)
    create_audit_log(
        db,
        action="FUTURES_CLUSTER_SNAPSHOT_VIEWED",
        entity_type="futures_cluster_snapshot",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "cluster_count": len(payload.get("correlation_clusters") or []),
            "risk_state": payload.get("risk_state", "NORMAL"),
        },
    )
    return payload
