from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from services.unified_control_room_service import build_unified_control_room


router = APIRouter(prefix="/admin/unified-control-room", tags=["unified_control_room"])


@router.get("/overview")
def unified_control_room_overview(
    window: str = Query(default="7d", pattern="^(7d|30d)$"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return build_unified_control_room(db, user_id=current_admin.id, window=window)
