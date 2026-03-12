import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import UserRiskSetting

DEFAULT_ALLOCATION_PCT = 20.0
DEFAULT_TRADE_RISK_PCT = 10.0
DEFAULT_DAILY_LOSS_LIMIT_PCT = 3.0
DEFAULT_BASE_CAPITAL = 10000.0


def get_or_create_user_risk_settings(db: Session, user_id: str) -> UserRiskSetting:
    row = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
    if row:
        return row

    row = UserRiskSetting(
        id=str(uuid.uuid4()),
        user_id=user_id,
        allocation_pct=DEFAULT_ALLOCATION_PCT,
        trade_risk_pct=DEFAULT_TRADE_RISK_PCT,
        daily_loss_limit_pct=DEFAULT_DAILY_LOSS_LIMIT_PCT,
        compounding_enabled=True,
        base_capital=DEFAULT_BASE_CAPITAL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def apply_user_risk_settings(
    db: Session,
    *,
    user_id: str,
    allocation_pct: float,
    trade_risk_pct: float,
    daily_loss_limit_pct: float,
    compounding_enabled: bool,
) -> UserRiskSetting:
    if not 1 <= allocation_pct <= 50:
        raise ValueError("İşleme ayrılan ana para 1-50 aralığında olmalı")
    if not 1 <= trade_risk_pct <= 25:
        raise ValueError("İşlemdeki paranın risk oranı 1-25 aralığında olmalı")
    if not 1 <= daily_loss_limit_pct <= 10:
        raise ValueError("Günlük zarar limiti 1-10 aralığında olmalı")

    row = get_or_create_user_risk_settings(db, user_id)
    row.allocation_pct = float(allocation_pct)
    row.trade_risk_pct = float(trade_risk_pct)
    row.daily_loss_limit_pct = float(daily_loss_limit_pct)
    row.compounding_enabled = bool(compounding_enabled)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def serialize_user_risk_settings(row: UserRiskSetting) -> dict:
    return {
        "allocation_pct": float(row.allocation_pct),
        "trade_risk_pct": float(row.trade_risk_pct),
        "daily_loss_limit_pct": float(row.daily_loss_limit_pct),
        "compounding_enabled": bool(row.compounding_enabled),
        "base_capital": float(row.base_capital),
    }