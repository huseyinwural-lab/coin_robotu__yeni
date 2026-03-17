from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import (
    exchange_connection_view,
    get_or_create_user_exchange_setting,
    upsert_user_exchange_connection,
)
from core.users.user_exchange_connections import (
    create_user_exchange_connection,
    delete_user_exchange_connection,
    get_user_exchange_connection,
    list_user_exchange_connections,
    set_default_user_exchange_connection,
    update_user_exchange_connection,
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
from services.live_mode_service import validate_exchange_credentials_for_user
from schemas import (
    UserDashboardResponse,
    UserExchangeConnectionPatchRequest,
    UserExchangeConnectionResponse,
    UserExchangeConnectionUpsertRequest,
    UserExchangeConnectRequest,
    UserExchangeConnectResponse,
    UserPerformanceSnapshotResponse,
    UserPortfolioMapRequest,
    UserPortfolioMapResponse,
    UserPortfolioSnapshotResponse,
    UserRiskSettingsResponse,
    UserRiskSettingsUpdate,
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


@router.get("/exchange-connections", response_model=list[UserExchangeConnectionResponse])
def get_user_exchange_connections(current_user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = list_user_exchange_connections(db, current_user.id)
    return [UserExchangeConnectionResponse(**row) for row in rows]


@router.post("/exchange-connections", response_model=UserExchangeConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_exchange_connection(
    payload: UserExchangeConnectionUpsertRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = create_user_exchange_connection(
            db,
            user_id=current_user.id,
            account_label=payload.account_label,
            exchange=payload.exchange,
            market_type=payload.market_type,
            environment=payload.environment,
            is_default=payload.is_default,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            permission_snapshot=payload.permission_snapshot,
            readiness_snapshot=payload.readiness_snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_exchange_connection_created",
        entity_type="user_exchange_connection",
        entity_id=row["id"],
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "account_label": row["account_label"],
            "exchange": row["exchange"],
            "market_type": row["market_type"],
            "environment": row["environment"],
            "is_default": row["is_default"],
        },
    )
    return UserExchangeConnectionResponse(**row)


@router.put("/exchange-connections/{connection_id}", response_model=UserExchangeConnectionResponse)
def update_exchange_connection(
    connection_id: str,
    payload: UserExchangeConnectionPatchRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = update_user_exchange_connection(
            db,
            user_id=current_user.id,
            connection_id=connection_id,
            account_label=payload.account_label,
            exchange=payload.exchange,
            market_type=payload.market_type,
            environment=payload.environment,
            is_default=payload.is_default,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            permission_snapshot=payload.permission_snapshot,
            readiness_snapshot=payload.readiness_snapshot,
        )
    except ValueError as exc:
        status_code = status.HTTP_404_NOT_FOUND if str(exc) == "connection_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_exchange_connection_updated",
        entity_type="user_exchange_connection",
        entity_id=row["id"],
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={
            "account_label": row["account_label"],
            "exchange": row["exchange"],
            "market_type": row["market_type"],
            "environment": row["environment"],
            "is_default": row["is_default"],
        },
    )
    return UserExchangeConnectionResponse(**row)


@router.post("/exchange-connections/{connection_id}/set-default", response_model=UserExchangeConnectionResponse)
def set_exchange_connection_default(
    connection_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = set_default_user_exchange_connection(db, user_id=current_user.id, connection_id=connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_exchange_connection_set_default",
        entity_type="user_exchange_connection",
        entity_id=row["id"],
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details={"account_label": row["account_label"]},
    )
    return UserExchangeConnectionResponse(**row)


@router.post("/exchange-connections/{connection_id}/revalidate", response_model=UserExchangeConnectionResponse)
def revalidate_exchange_connection(
    connection_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        connection = get_user_exchange_connection(db, user_id=current_user.id, connection_id=connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    payload, status_code = validate_exchange_credentials_for_user(
        db,
        current_user.id,
        exchange=connection["exchange"],
        market_type=connection["market_type"],
        environment=connection["environment"],
    )
    refreshed = get_user_exchange_connection(db, user_id=current_user.id, connection_id=connection_id)

    create_audit_log(
        db,
        action="user_exchange_connection_revalidated",
        entity_type="user_exchange_connection",
        entity_id=connection_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        severity="warning" if status_code >= 400 else "info",
        details={
            "exchange": connection["exchange"],
            "market_type": connection["market_type"],
            "environment": connection["environment"],
            "status_code": status_code,
            "reason_codes": payload.get("reason_codes", []),
            "is_valid": payload.get("is_valid"),
            "can_trade": payload.get("can_trade"),
        },
    )

    return UserExchangeConnectionResponse(**refreshed)


@router.delete("/exchange-connections/{connection_id}")
def remove_exchange_connection(
    connection_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        payload = delete_user_exchange_connection(db, user_id=current_user.id, connection_id=connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="user_exchange_connection_deleted",
        entity_type="user_exchange_connection",
        entity_id=connection_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        details=payload,
    )
    return payload


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
    bot_count = db.query(BotProfile).filter(BotProfile.user_id == current_user.id, BotProfile.is_deleted.is_(False)).count()
    running_bot_count = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == current_user.id, BotProfile.is_deleted.is_(False), BotProfile.is_enabled.is_(True), BotProfile.is_running.is_(True))
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

