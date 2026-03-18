from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from routers.dashboard import dashboard_summary

router = APIRouter(tags=["admin_dashboard"])


@router.get("/admin/dashboard")
def admin_dashboard_alias(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return dashboard_summary(current_user=current_admin, db=db)
