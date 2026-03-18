from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from db import get_db
from schemas import BrandSettingsResponse
from services.brand_settings_service import get_brand_logo_blob, get_brand_settings_payload

router = APIRouter(tags=["branding"])


@router.get("/branding/settings", response_model=BrandSettingsResponse)
def get_branding_settings(db: Session = Depends(get_db)):
    return BrandSettingsResponse(**get_brand_settings_payload(db))


@router.get("/branding/logo")
def get_branding_logo(db: Session = Depends(get_db)):
    blob, mime = get_brand_logo_blob(db)
    return Response(content=blob, media_type=mime)
