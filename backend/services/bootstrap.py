import logging

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
    UserOnboardingProfile,
    UserScannerAutomationConfig,
    UserScannerAutomationProfile,
    UserRole,
)
from services.audit_service import create_audit_log
from services.canonical_strategy_registry_service import seed_canonical_strategy_registry
from services.strategy_family_gate_service import seed_strategy_family_gates
from services.venue_service import seed_binance_venue_registry


logger = logging.getLogger(__name__)


def _seed_admin(db: Session):
    users_count = db.query(User).count()
    if users_count > 0:
        return

    bootstrap_email = (settings.bootstrap_admin_email or "").strip()
    bootstrap_password = (settings.bootstrap_admin_password or "").strip()
    if not bootstrap_email or not bootstrap_password:
        raise RuntimeError(
            "Missing ADMIN_BOOTSTRAP_EMAIL or ADMIN_BOOTSTRAP_PASSWORD. "
            "First admin must be created via secure bootstrap env values."
        )

    admin = User(
        email=bootstrap_email,
        password_hash=hash_password(bootstrap_password),
        role=UserRole.SUPER_ADMIN,
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


def _upsert_platform_account(
    db: Session,
    *,
    email: str,
    password: str,
    role: UserRole,
    audit_action: str,
) -> None:
    normalized_email = str(email or "").strip().lower()
    normalized_password = str(password or "").strip()
    if not normalized_email or not normalized_password:
        return

    now_ts = datetime.now(timezone.utc)
    user = db.query(User).filter(User.email == normalized_email).first()
    if user is None:
        user = User(
            email=normalized_email,
            password_hash=hash_password(normalized_password),
            role=role,
            is_active=True,
            approval_status="approved",
            approval_requested_at=now_ts,
            approved_at=now_ts,
        )
        db.add(user)
        db.flush()
    else:
        user.password_hash = hash_password(normalized_password)
        user.role = role
        user.is_active = True
        user.approval_status = "approved"
        if user.approval_requested_at is None:
            user.approval_requested_at = now_ts
        user.approved_at = now_ts
        user.disabled_at = None

    profile = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id == user.id).first()
    if profile is None:
        profile = UserOnboardingProfile(
            user_id=user.id,
            full_name=("Canary Admin" if role != UserRole.USER else "Review User"),
            email_verified=True,
            kyc_status="verified",
            leverage_permission=True,
            futures_capability=True,
            spot_capability=True,
            trading_eligibility=True,
            precheck_reasons=[],
        )
        db.add(profile)
    else:
        profile.email_verified = True
        profile.kyc_status = "verified"
        profile.leverage_permission = True
        profile.futures_capability = True
        profile.spot_capability = True
        profile.trading_eligibility = True
        profile.precheck_reasons = []

    db.flush()
    create_audit_log(
        db,
        action=audit_action,
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        details={"email": user.email},
        commit=False,
    )


def _seed_platform_test_accounts(db: Session):
    admin_email = (settings.bootstrap_admin_email or "").strip()
    admin_password = (settings.bootstrap_admin_password or "").strip()
    review_email = (settings.review_user_bootstrap_email or "").strip()
    review_password = (settings.review_user_bootstrap_password or "").strip()

    if admin_email.endswith("@platform.local") and admin_password:
        _upsert_platform_account(
            db,
            email=admin_email,
            password=admin_password,
            role=UserRole.SUPER_ADMIN,
            audit_action="platform_admin_seed_sync",
        )

    if review_email.endswith("@platform.local") and review_password:
        _upsert_platform_account(
            db,
            email=review_email,
            password=review_password,
            role=UserRole.USER,
            audit_action="platform_review_user_seed_sync",
        )

    db.commit()


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
        spot_universe=[],
        futures_universe=[],
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
            market_type="futures_live",
            safe_mode_enabled=False,
            live_mode_enabled=True,
            symbol_whitelist=[],
            max_position_pct=0.1,
            leverage_cap=1,
            max_trades_per_hour=6,
            max_notional_exposure=150,
            kill_switch_enabled=False,
            trading_enabled=True,
            canary_enabled=False,
            canary_symbols=["BTCUSDT"],
            canary_max_capital_usdt=50,
            canary_max_positions=1,
            disable_futures=False,
            ip_whitelist_ready=False,
            trading_permission_ready=False,
        )
    )
    db.commit()


def _migrate_universe_defaults(db: Session):
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control:
        control.whitelist = []
        control.blacklist = []
        control.spot_universe = list(control.spot_universe or [])
        control.futures_universe = list(control.futures_universe or [])
        if control.minimum_volume_usd is None:
            control.minimum_volume_usd = 1000000
        if control.max_spread_bps is None:
            control.max_spread_bps = 40

    live_config = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    if live_config and live_config.symbol_whitelist is None:
        live_config.symbol_whitelist = []

    for row in db.query(UserScannerAutomationConfig).all():
        row.symbol_selection_mode = "all_market_symbols"

    for row in db.query(UserScannerAutomationProfile).all():
        row.symbol_selection_mode = "all_market_symbols"

    db.commit()


def seed_default_admin():
    db = SessionLocal()
    try:
        seed_steps = [
            _seed_admin,
            _seed_platform_test_accounts,
            _seed_admin_control,
            _seed_execution_policies,
            _seed_exposure_groups,
            _seed_backtest_cards,
            _seed_live_activation_config,
            _seed_risk_orchestrator_policy,
            _migrate_universe_defaults,
            seed_canonical_strategy_registry,
            seed_strategy_family_gates,
            seed_binance_venue_registry,
        ]
        for step in seed_steps:
            try:
                step(db)
            except Exception:
                logger.exception("Bootstrap seed step failed: %s", step.__name__)
    finally:
        db.close()