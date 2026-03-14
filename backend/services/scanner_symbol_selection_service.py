from datetime import datetime, timezone

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models import UserScannerSymbolSelection


def _ensure_table(db: Session) -> None:
    inspector = inspect(db.bind)
    if UserScannerSymbolSelection.__table__.name not in set(inspector.get_table_names()):
        UserScannerSymbolSelection.__table__.create(bind=db.bind, checkfirst=True)


def get_user_scanner_symbol_selection(
    db: Session,
    *,
    user_id: str,
    scanner_id: str = "default",
) -> UserScannerSymbolSelection:
    _ensure_table(db)
    row = (
        db.query(UserScannerSymbolSelection)
        .filter(
            UserScannerSymbolSelection.user_id == user_id,
            UserScannerSymbolSelection.scanner_id == scanner_id,
        )
        .first()
    )
    if row is None:
        now = datetime.now(timezone.utc)
        row = UserScannerSymbolSelection(
            user_id=user_id,
            scanner_id=scanner_id,
            symbol_source="crypto",
            symbol_selection_mode="all_market_symbols",
            selected_symbols=[],
            saved_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def upsert_user_scanner_symbol_selection(
    db: Session,
    *,
    user_id: str,
    scanner_id: str,
    symbol_source: str,
    symbol_selection_mode: str,
    selected_symbols: list[str],
) -> UserScannerSymbolSelection:
    _ensure_table(db)
    row = (
        db.query(UserScannerSymbolSelection)
        .filter(
            UserScannerSymbolSelection.user_id == user_id,
            UserScannerSymbolSelection.scanner_id == scanner_id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    normalized_symbols = [str(item).upper() for item in selected_symbols if str(item).strip()]

    if row is None:
        row = UserScannerSymbolSelection(
            user_id=user_id,
            scanner_id=scanner_id,
            symbol_source=str(symbol_source or "crypto"),
            symbol_selection_mode=str(symbol_selection_mode or "all_market_symbols"),
            selected_symbols=normalized_symbols,
            saved_at=now,
        )
        db.add(row)
    else:
        row.symbol_source = str(symbol_source or row.symbol_source or "crypto")
        row.symbol_selection_mode = str(symbol_selection_mode or row.symbol_selection_mode or "all_market_symbols")
        row.selected_symbols = normalized_symbols
        row.saved_at = now

    db.commit()
    db.refresh(row)
    return row
