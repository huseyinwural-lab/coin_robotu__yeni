from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import ArtifactBatchVerifyResponse, ArtifactManifestItemResponse, ArtifactVerifyResponse
from services.artifact_service import (
    get_manifest_artifact,
    list_manifest_artifacts,
    resolve_artifact_path,
    verify_all_artifacts,
    verify_artifact,
)
from services.audit_service import create_audit_log


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/admin/proofs", response_model=list[ArtifactManifestItemResponse])
def admin_list_proofs(current_admin: User = Depends(require_admin)):
    _ = current_admin
    return [ArtifactManifestItemResponse(**item) for item in list_manifest_artifacts()]


@router.get("/artifacts/{artifact_id}/verify", response_model=ArtifactVerifyResponse)
def verify_artifact_integrity(
    artifact_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        result = verify_artifact(artifact_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="artifact_verify",
        entity_type="artifact",
        entity_id=artifact_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info" if result["verified"] else "warning",
        details={
            "artifact_id": artifact_id,
            "filename": result["filename"],
            "sha256_expected": result["sha256_expected"],
            "sha256_actual": result["sha256_actual"],
            "verified": result["verified"],
            "chain_valid": result["chain_valid"],
            "chain_broken": result["chain_broken"],
        },
    )
    return ArtifactVerifyResponse(**result)


@router.get("/artifacts/verify-all", response_model=ArtifactBatchVerifyResponse)
def verify_all_artifacts_integrity(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    artifact_type: str | None = None,
    status: str = Query(default="all"),
    date_from: str | None = None,
    date_to: str | None = None,
):
    _ = current_admin
    parsed_from = None
    parsed_to = None
    if date_from:
        try:
            parsed_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_from") from exc
    if date_to:
        try:
            parsed_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_to") from exc

    result = verify_all_artifacts(
        artifact_type=artifact_type,
        date_from=parsed_from,
        date_to=parsed_to,
        status_filter=status,
    )

    create_audit_log(
        db,
        action="artifact_verify_batch",
        entity_type="artifact_manifest",
        entity_id="manifest",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning" if result["mismatch"] or result["missing"] or result["chain_broken"] else "info",
        details={
            "total": result["total"],
            "verified": result["verified"],
            "mismatch": result["mismatch"],
            "missing": result["missing"],
            "chain_broken": result["chain_broken"],
        },
    )
    return ArtifactBatchVerifyResponse(**result)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, current_admin: User = Depends(require_admin)):
    _ = current_admin
    entry = get_manifest_artifact(artifact_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact_not_found")

    path = resolve_artifact_path(artifact_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact_file_missing")

    return FileResponse(path=str(path), filename=entry["filename"], media_type="application/json")
