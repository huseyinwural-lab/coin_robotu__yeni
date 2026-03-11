from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import ArtifactManifestItemResponse, ArtifactVerifyResponse
from services.artifact_service import get_manifest_artifact, list_manifest_artifacts, resolve_artifact_path, verify_artifact
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
        },
    )
    return ArtifactVerifyResponse(**result)


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
