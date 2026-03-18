from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import BrandSettingsResponse, BrandSettingsUpdateRequest
from services.audit_service import create_audit_log
from services.brand_settings_service import (
    get_brand_settings_payload,
    save_brand_logo_upload,
    update_brand_settings,
)

router = APIRouter(tags=["admin_brand_settings"])


@router.get("/admin/brand-settings", response_model=BrandSettingsResponse)
def get_admin_brand_settings(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return BrandSettingsResponse(**get_brand_settings_payload(db))


@router.put("/admin/brand-settings", response_model=BrandSettingsResponse)
def put_admin_brand_settings(
    payload: BrandSettingsUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = update_brand_settings(db, app_name=payload.app_name, updated_by_user_id=current_admin.id)
    create_audit_log(
        db,
        action="brand_settings_updated",
        entity_type="brand_settings",
        entity_id="default",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"app_name": payload.app_name},
    )
    return BrandSettingsResponse(**result)


@router.post("/admin/brand-settings/logo-upload", response_model=BrandSettingsResponse)
def post_admin_brand_logo_upload(
    file: UploadFile = File(...),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = save_brand_logo_upload(db, upload=file, updated_by_user_id=current_admin.id)
    create_audit_log(
        db,
        action="brand_logo_uploaded",
        entity_type="brand_settings",
        entity_id="default",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"filename": file.filename, "content_type": file.content_type},
    )
    return BrandSettingsResponse(**result)
