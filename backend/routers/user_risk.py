from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user
from models import User
from schemas import (
    UserPortfolioOverviewResponse,
    UserRiskPreviewResponse,
    UserRiskSettingsResponse,
    UserRiskSettingsUpdate,
)
from services.live_mode_service import (
    resolve_user_risk_settings_payload,
    update_user_risk_settings,
    user_portfolio_overview,
    user_risk_preview,
)

router = APIRouter(prefix="/user-risk", tags=["user_risk"])


@router.get("/settings", response_model=UserRiskSettingsResponse)
def get_risk_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = resolve_user_risk_settings_payload(db, current_user.id)
    return UserRiskSettingsResponse(**payload)


@router.put("/settings", response_model=UserRiskSettingsResponse)
def put_risk_settings(
    payload: UserRiskSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = update_user_risk_settings(
            db,
            user_id=current_user.id,
            allocation_pct=payload.allocation_pct,
            trade_risk_pct=payload.trade_risk_pct,
            daily_loss_limit_pct=payload.daily_loss_limit_pct,
            compounding_enabled=payload.compounding_enabled,
            reference_equity_usd=payload.reference_equity_usd,
            account_max_notional_pct=payload.account_max_notional_pct,
            symbol_max_notional_pct=payload.symbol_max_notional_pct,
            strategy_max_concurrent_positions=payload.strategy_max_concurrent_positions,
            strategy_cooldown_seconds=payload.strategy_cooldown_seconds,
            max_order_frequency_per_min=payload.max_order_frequency_per_min,
            max_order_burst_per_10s=payload.max_order_burst_per_10s,
            duplicate_suppression_window_seconds=payload.duplicate_suppression_window_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _ = row
    merged = resolve_user_risk_settings_payload(db, current_user.id)
    return UserRiskSettingsResponse(**merged)


@router.get("/preview", response_model=UserRiskPreviewResponse)
def get_risk_preview(
    market_type: str = "spot",
    leverage: int = 1,
    margin_mode: str = "cross",
    position_side: str = "BOTH",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return UserRiskPreviewResponse(
        **user_risk_preview(
            db,
            current_user.id,
            market_type=market_type,
            leverage=leverage,
            margin_mode=margin_mode,
            position_side=position_side,
        )
    )


@router.get("/overview", response_model=UserPortfolioOverviewResponse)
def get_portfolio_overview(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserPortfolioOverviewResponse(**user_portfolio_overview(db, current_user.id))