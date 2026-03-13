from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import User
from schemas import UserScannerSymbolSelectionResponse, UserScannerSymbolSelectionUpdateRequest
from services.audit_service import create_audit_log
from services.scanner_symbol_selection_service import (
    get_user_scanner_symbol_selection,
    upsert_user_scanner_symbol_selection,
)


router = APIRouter(prefix="/user/scanner/symbol-selection", tags=["user_scanner_symbol_selection"])


@router.get("", response_model=UserScannerSymbolSelectionResponse)
def get_symbol_selection(
    scanner_id: str = Query(default="default", min_length=1, max_length=60),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = get_user_scanner_symbol_selection(db, user_id=current_user.id, scanner_id=scanner_id)
    return UserScannerSymbolSelectionResponse(
        id=row.id,
        user_id=row.user_id,
        scanner_id=row.scanner_id,
        symbol_source=row.symbol_source,
        symbol_selection_mode=row.symbol_selection_mode,
        selected_symbols=list(row.selected_symbols or []),
        saved_at=row.saved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put("", response_model=UserScannerSymbolSelectionResponse)
def update_symbol_selection(
    payload: UserScannerSymbolSelectionUpdateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = upsert_user_scanner_symbol_selection(
        db,
        user_id=current_user.id,
        scanner_id=payload.scanner_id,
        symbol_source=payload.symbol_source,
        symbol_selection_mode=payload.symbol_selection_mode,
        selected_symbols=payload.selected_symbols,
    )
    create_audit_log(
        db,
        action="user_scanner_symbol_selection_saved",
        entity_type="user_scanner_symbol_selection",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "scanner_id": row.scanner_id,
            "symbol_source": row.symbol_source,
            "symbol_selection_mode": row.symbol_selection_mode,
            "selected_symbols_count": len(row.selected_symbols or []),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return UserScannerSymbolSelectionResponse(
        id=row.id,
        user_id=row.user_id,
        scanner_id=row.scanner_id,
        symbol_source=row.symbol_source,
        symbol_selection_mode=row.symbol_selection_mode,
        selected_symbols=list(row.selected_symbols or []),
        saved_at=row.saved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
