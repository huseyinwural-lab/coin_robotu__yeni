from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from models import BrandSetting

DEFAULT_APP_NAME = "XILO User Trading Engine"


def _ensure_brand_table(db: Session):
    try:
        BrandSetting.__table__.create(bind=db.bind, checkfirst=True)
    except Exception:
        return


def get_or_create_brand_setting(db: Session) -> BrandSetting:
    _ensure_brand_table(db)
    row = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if row is not None:
        return row
    row = BrandSetting(id="default", app_name=DEFAULT_APP_NAME)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_brand_settings_payload(db: Session) -> dict:
    row = get_or_create_brand_setting(db)
    return {
        "app_name": row.app_name,
        "logo_url": "/api/branding/logo" if row.logo_blob else None,
        "has_logo": bool(row.logo_blob),
        "updated_at": row.updated_at,
    }


def update_brand_settings(db: Session, *, app_name: str, updated_by_user_id: str | None = None) -> dict:
    row = get_or_create_brand_setting(db)
    normalized_name = str(app_name or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="app_name_required")
    row.app_name = normalized_name[:120]
    row.updated_by_user_id = updated_by_user_id
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return get_brand_settings_payload(db)


def save_brand_logo_upload(
    db: Session,
    *,
    upload: UploadFile,
    updated_by_user_id: str | None = None,
) -> dict:
    row = get_or_create_brand_setting(db)
    content_type = str(upload.content_type or "").strip().lower()
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_logo_type")

    raw = upload.file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_logo_file")
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="logo_file_too_large")

    row.logo_blob = raw
    row.logo_mime_type = content_type
    row.logo_filename = str(upload.filename or "brand-logo")[:255]
    row.updated_by_user_id = updated_by_user_id
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return get_brand_settings_payload(db)


def get_brand_logo_blob(db: Session) -> tuple[bytes, str]:
    row = get_or_create_brand_setting(db)
    if not row.logo_blob:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="brand_logo_not_found")
    mime = str(row.logo_mime_type or "image/png")
    return bytes(row.logo_blob), mime
