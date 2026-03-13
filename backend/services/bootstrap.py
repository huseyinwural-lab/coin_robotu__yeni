from sqlalchemy.orm import Session
from datetime import datetime, timezone

from core.config import settings
from core.security import hash_password
from db import SessionLocal
from models import (
    AdminControl,
    BacktestResultCard,
    ExecutionPolicy,
    LiveActivationConfig,
    RiskExposureGroup,
    RiskOrchestratorPolicy,
    User,
    UserRole,
)
from services.audit_service import create_audit_log
from services.canonical_strategy_registry_service import seed_canonical_strategy_registry
from services.venue_service import seed_binance_venue_registry


def _seed_admin(db: Session):
    if not settings.default_admin_email or not settings.default_admin_password:
        return

    if db.query(User).count() > 0:
        return

    existing_admin = db.query(User).filter(User.email == settings.default_admin_email).first()
    if existing_admin:
        existing_admin.is_active = True
        existing_admin.approval_status = "approved"
        existing_admin.approval_requested_at = existing_admin.approval_requested_at or datetime.now(timezone.utc)
        existing_admin.approved_at = existing_admin.approved_at or datetime.now(timezone.utc)
        db.commit()
        return

    admin = User(
        email=settings.default_admin_email,
        password_hash=hash_password(settings.default_admin_password),
        role=UserRole.ADMIN,
        is_active=True,
        approval_status="approved",
        approval_requested_at=datetime.now(timezone.utc),
        approved_at=datetime.now(timezone.utc),
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


def _seed_risk_orchestrator_policy(db: Session):
    policy = db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()
    if policy:
        return
    db.add(RiskOrchestratorPolicy(id="global"))
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
        {
            "strategy_type": "spot_pullback_v1",
            "execution_style": "balanced",
            "order_preference": "limit_first",
            "timeout_seconds": 8,
            "fallback_behavior": "market_fallback",
            "partial_fill_tolerance_pct": 60,
            "execution_urgency": "medium",
            "retry_limit": 1,
        },
        {
            "strategy_type": "spot_range_reversion_v1",
            "execution_style": "balanced",
            "order_preference": "limit_first",
            "timeout_seconds": 10,
            "fallback_behavior": "market_fallback",
            "partial_fill_tolerance_pct": 55,
            "execution_urgency": "low",
            "retry_limit": 1,
        },
        {
            "strategy_type": "spot_volatility_breakout_v1",
            "execution_style": "aggressive",
            "order_preference": "market_first",
            "timeout_seconds": 6,
            "fallback_behavior": "market_fallback",
            "partial_fill_tolerance_pct": 70,
            "execution_urgency": "high",
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
    defaults = [
        {
            "name": "majors",
            "label": "Majors Cluster (BTC, ETH)",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "max_group_open_positions": 6,
            "max_group_directional_positions": 4,
            "max_group_risk_pct": 22,
        },
        {
            "name": "high_beta_alts",
            "label": "High Beta Alts (SOL, AVAX, LINK)",
            "symbols": ["SOLUSDT", "AVAXUSDT", "LINKUSDT"],
            "max_group_open_positions": 5,
            "max_group_directional_positions": 3,
            "max_group_risk_pct": 18,
        },
        {
            "name": "mid_cap",
            "label": "Mid Cap & Others (Fallback Group)",
            "symbols": [],
            "max_group_open_positions": 8,
            "max_group_directional_positions": 5,
            "max_group_risk_pct": 20,
        },
    ]

    for payload in defaults:
        existing = db.query(RiskExposureGroup).filter(RiskExposureGroup.name == payload["name"]).first()
        if existing:
            existing.label = payload["label"]
            existing.symbols = payload["symbols"]
            existing.max_group_open_positions = payload["max_group_open_positions"]
            existing.max_group_directional_positions = payload["max_group_directional_positions"]
            existing.max_group_risk_pct = payload["max_group_risk_pct"]
            continue
        db.add(RiskExposureGroup(**payload))

    legacy = db.query(RiskExposureGroup).filter(RiskExposureGroup.name == "all_symbols").first()
    if legacy:
        legacy.label = "Legacy Unified Group (deprecated)"

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


def _seed_live_activation_config(db: Session):
    config = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    if config:
        return
    db.add(
        LiveActivationConfig(
            id="global",
            exchange="binance",
            market_type="futures_testnet",
            safe_mode_enabled=True,
            live_mode_enabled=False,
            symbol_whitelist=["BTCUSDT"],
            max_position_pct=0.1,
            leverage_cap=1,
            max_trades_per_hour=6,
            max_notional_exposure=150,
            kill_switch_enabled=False,
            disable_futures=False,
            ip_whitelist_ready=False,
            trading_permission_ready=False,
        )
    )
    db.commit()


def seed_default_admin():
    db = SessionLocal()
    try:
        _seed_admin(db)
        _seed_admin_control(db)
        _seed_execution_policies(db)
        _seed_exposure_groups(db)
        _seed_backtest_cards(db)
        _seed_live_activation_config(db)
        _seed_risk_orchestrator_policy(db)
        seed_canonical_strategy_registry(db)
        seed_binance_venue_registry(db)
    finally:
        db.close()