from sqlalchemy.orm import Session

from core.config import settings
from core.security import hash_password
from db import SessionLocal
from models import (
    AdminControl,
    BacktestResultCard,
    ExecutionPolicy,
    RiskExposureGroup,
    User,
    UserRole,
)
from services.audit_service import create_audit_log


def _seed_admin(db: Session):
    if not settings.default_admin_email or not settings.default_admin_password:
        return

    existing_admin = db.query(User).filter(User.email == settings.default_admin_email).first()
    if existing_admin:
        return

    admin = User(
        email=settings.default_admin_email,
        password_hash=hash_password(settings.default_admin_password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    create_audit_log(
        db,
        action="bootstrap_admin_created",
        entity_type="user",
        entity_id=admin.id,
        actor_user_id=admin.id,
        actor_role=admin.role.value,
        details={"email": admin.email},
    )


def _seed_admin_control(db: Session):
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control:
        return

    default_control = AdminControl(
        id="global",
        max_leverage_cap=5,
        max_open_positions_cap=10,
        minimum_volume_usd=1000000,
        max_spread_bps=40,
        spot_universe=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        futures_universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        whitelist=[],
        blacklist=[],
        emergency_mode=False,
        disable_futures=False,
    )
    db.add(default_control)
    db.commit()


def _seed_execution_policies(db: Session):
    defaults = [
        {
            "strategy_type": "breakout",
            "execution_style": "aggressive",
            "order_preference": "market_first",
            "timeout_seconds": 4,
            "fallback_behavior": "market_fallback",
            "partial_fill_tolerance_pct": 85,
            "execution_urgency": "high",
            "retry_limit": 1,
        },
        {
            "strategy_type": "mean_reversion",
            "execution_style": "passive",
            "order_preference": "limit_first",
            "timeout_seconds": 12,
            "fallback_behavior": "cancel_no_fill",
            "partial_fill_tolerance_pct": 35,
            "execution_urgency": "low",
            "retry_limit": 3,
        },
        {
            "strategy_type": "trend_following",
            "execution_style": "balanced",
            "order_preference": "limit_first",
            "timeout_seconds": 8,
            "fallback_behavior": "market_fallback",
            "partial_fill_tolerance_pct": 60,
            "execution_urgency": "medium",
            "retry_limit": 2,
        },
        {
            "strategy_type": "volatility_expansion",
            "execution_style": "balanced",
            "order_preference": "market_first",
            "timeout_seconds": 6,
            "fallback_behavior": "limit_retry_then_market",
            "partial_fill_tolerance_pct": 70,
            "execution_urgency": "medium",
            "retry_limit": 2,
        },
    ]

    for payload in defaults:
        exists = db.query(ExecutionPolicy).filter(ExecutionPolicy.strategy_type == payload["strategy_type"]).first()
        if exists:
            continue
        db.add(ExecutionPolicy(**payload, is_active=True))
    db.commit()


def _seed_exposure_groups(db: Session):
    existing = db.query(RiskExposureGroup).count()
    if existing:
        return

    db.add(
        RiskExposureGroup(
            name="all_symbols",
            label="All Symbols Unified Exposure Group",
            symbols=[],
            max_group_open_positions=12,
            max_group_directional_positions=8,
            max_group_risk_pct=35,
        )
    )
    db.commit()


def _seed_backtest_cards(db: Session):
    if db.query(BacktestResultCard).count() > 0:
        return
    samples = [
        {
            "strategy_type": "trend_following",
            "market_type": "spot",
            "timeframe": "15m",
            "sample_size": 240,
            "win_rate": 54.2,
            "max_drawdown": 9.8,
            "profit_factor": 1.34,
            "sharpe_like_score": 0.88,
            "performance_summary": "Stable trend capture with moderate drawdown.",
            "risk_label": "medium",
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
        },
        {
            "strategy_type": "mean_reversion",
            "market_type": "spot",
            "timeframe": "15m",
            "sample_size": 260,
            "win_rate": 61.1,
            "max_drawdown": 12.4,
            "profit_factor": 1.21,
            "sharpe_like_score": 0.73,
            "performance_summary": "Higher win rate but lower payoff consistency.",
            "risk_label": "medium-high",
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
        },
    ]
    for sample in samples:
        db.add(BacktestResultCard(**sample))
    db.commit()


def seed_default_admin():
    db = SessionLocal()
    try:
        _seed_admin(db)
        _seed_admin_control(db)
        _seed_execution_policies(db)
        _seed_exposure_groups(db)
        _seed_backtest_cards(db)
    finally:
        db.close()