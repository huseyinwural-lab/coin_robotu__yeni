from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import (
    exchange_connection_view,
    get_or_create_user_exchange_setting,
    upsert_user_exchange_connection,
)
from core.users.user_portfolio_engine import (
    build_user_performance_snapshot,
    build_user_portfolio_snapshot,
    build_user_trade_history,
)
from core.users.user_portfolio_mapper import map_user_portfolio
from core.users.user_risk_settings import (
    apply_user_risk_settings,
    get_or_create_user_risk_settings,
    serialize_user_risk_settings,
)
from db import get_db, redis_client
from deps import require_user
from models import BotProfile, PendingSignal, RiskPolicy, User
from schemas import (
    UserDashboardResponse,
    UserExchangeConnectRequest,
    UserExchangeConnectResponse,
    UserPerformanceSnapshotResponse,
    UserPortfolioMapRequest,
    UserPortfolioMapResponse,
    UserPortfolioSnapshotResponse,
    UserRiskSettingsResponse,
    UserRiskSettingsUpdate,
    UserWeeklyReportStubResponse,
    UserTradeResponse,
)
from services.audit_service import create_audit_log

router = APIRouter(prefix="/user", tags=["user_platform"])


@router.post("/exchange/connect", response_model=UserExchangeConnectResponse)
def connect_user_exchange(
    payload: UserExchangeConnectRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    settings_row = upsert_user_exchange_connection(
        db,
        user_id=current_user.id,
        exchange=payload.exchange,
        mode=payload.mode,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
    )
    response_payload = exchange_connection_view(settings_row)
    create_audit_log(
        db,
        action="user_exchange_connected",
        entity_type="user_exchange_settings",
        entity_id=settings_row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "exchange": response_payload["exchange"],
            "mode": response_payload["mode"],
            "masked_api_key": response_payload["masked_api_key"],
            "credential_fingerprint": response_payload["credential_fingerprint"],
        },
    )
    return UserExchangeConnectResponse(**response_payload)


@router.get("/exchange", response_model=UserExchangeConnectResponse)
def get_user_exchange(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    settings_row = get_or_create_user_exchange_setting(db, current_user.id)
    return UserExchangeConnectResponse(**exchange_connection_view(settings_row))


@router.put("/exchange", response_model=UserExchangeConnectResponse)
def update_user_exchange(
    payload: UserExchangeConnectRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return connect_user_exchange(payload=payload, current_user=current_user, db=db)


@router.post("/portfolio/map", response_model=UserPortfolioMapResponse)
def map_portfolio(
    payload: UserPortfolioMapRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    mapped = map_user_portfolio(
        db,
        user_id=current_user.id,
        market_type=payload.market_type,
        leverage=payload.leverage,
        margin_mode=payload.margin_mode,
        position_side=payload.position_side,
    )
    return UserPortfolioMapResponse(**mapped)


@router.get("/risk-settings", response_model=UserRiskSettingsResponse)
def get_risk_settings(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    row = get_or_create_user_risk_settings(db, current_user.id)
    return UserRiskSettingsResponse(**serialize_user_risk_settings(row))


@router.put("/risk-settings", response_model=UserRiskSettingsResponse)
def apply_risk_settings(
    payload: UserRiskSettingsUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = apply_user_risk_settings(
            db,
            user_id=current_user.id,
            allocation_pct=payload.allocation_pct,
            trade_risk_pct=payload.trade_risk_pct,
            daily_loss_limit_pct=payload.daily_loss_limit_pct,
            compounding_enabled=payload.compounding_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_risk_settings_updated",
        entity_type="user_risk_settings",
        entity_id=row.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details=serialize_user_risk_settings(row),
    )
    return UserRiskSettingsResponse(**serialize_user_risk_settings(row))


@router.get("/portfolio", response_model=UserPortfolioSnapshotResponse)
def get_portfolio(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    snapshot = build_user_portfolio_snapshot(db, current_user.id)
    return UserPortfolioSnapshotResponse(**snapshot)


@router.get("/performance", response_model=UserPerformanceSnapshotResponse)
def get_performance(
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    snapshot = build_user_performance_snapshot(db, current_user.id, lookback_days=lookback_days)
    return UserPerformanceSnapshotResponse(**snapshot)


@router.get("/trades", response_model=list[UserTradeResponse])
def get_trades(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    rows = build_user_trade_history(db, current_user.id, limit=limit)
    return [UserTradeResponse(**row) for row in rows]


@router.get("/dashboard", response_model=UserDashboardResponse)
def get_user_dashboard(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    portfolio = build_user_portfolio_snapshot(db, current_user.id)
    bot_count = db.query(BotProfile).filter(BotProfile.user_id == current_user.id).count()
    running_bot_count = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == current_user.id, BotProfile.is_enabled.is_(True), BotProfile.is_running.is_(True))
        .count()
    )
    risk_policy_count = db.query(RiskPolicy).filter(RiskPolicy.user_id == current_user.id).count()
    pending_signals_count = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == current_user.id, PendingSignal.status == "pending")
        .count()
    )
    heartbeat_raw = redis_client.get("heartbeat:market-data")
    heartbeat = heartbeat_raw.decode("utf-8") if isinstance(heartbeat_raw, bytes) else heartbeat_raw

    return UserDashboardResponse(
        bot_count=bot_count,
        running_bot_count=running_bot_count,
        risk_policy_count=risk_policy_count,
        current_capital=portfolio["current_capital"],
        available_balance=portfolio["available_balance"],
        open_positions_count=portfolio["open_positions_count"],
        pending_signals_count=pending_signals_count,
        heartbeat=heartbeat,
    )


@router.get("/reports/weekly", response_model=UserWeeklyReportStubResponse)
def get_weekly_report_stub(current_user: User = Depends(require_user)):
    payload = UserWeeklyReportStubResponse(
        status="not_implemented",
        report_id=None,
        week=None,
        pnl=None,
        win_rate=None,
        download_links={},
        detail="weekly reporting engine not implemented in this iteration",
    )
    return JSONResponse(status_code=501, content=payload.model_dump())