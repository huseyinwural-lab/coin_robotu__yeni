from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import CanonicalStrategyRegistry, PendingSignal


CANONICAL_STRATEGIES: list[dict] = [
    {"strategy_id": "ichimoku_trend_continuation", "strategy_family": "trend", "market_regime": "trend", "enabled": True, "priority": 10},
    {"strategy_id": "golden_cross_regime", "strategy_family": "trend", "market_regime": "trend", "enabled": False, "priority": 20},
    {"strategy_id": "supertrend_flip", "strategy_family": "trend", "market_regime": "trend", "enabled": True, "priority": 15},
    {"strategy_id": "vortex_directional_cross", "strategy_family": "trend", "market_regime": "trend", "enabled": False, "priority": 30},
    {"strategy_id": "bollinger_squeeze_breakout", "strategy_family": "breakout", "market_regime": "breakout", "enabled": True, "priority": 12},
    {"strategy_id": "moving_momentum", "strategy_family": "trend", "market_regime": "trend", "enabled": False, "priority": 25},
    {"strategy_id": "fibonacci_pullback_continuation", "strategy_family": "pullback", "market_regime": "pullback", "enabled": False, "priority": 35},
    {"strategy_id": "macd_impulse", "strategy_family": "momentum", "market_regime": "trend", "enabled": True, "priority": 18},
    {"strategy_id": "fisher_reversal", "strategy_family": "reversal", "market_regime": "reversal", "enabled": False, "priority": 50},
    {"strategy_id": "divergence_reversal_suite", "strategy_family": "reversal", "market_regime": "reversal", "enabled": False, "priority": 55},
    {"strategy_id": "structure_breakout", "strategy_family": "breakout", "market_regime": "breakout", "enabled": False, "priority": 22},
    {"strategy_id": "stochastic_exhaustion_reentry", "strategy_family": "reversal", "market_regime": "reversal", "enabled": False, "priority": 60},
]

LEGACY_CANDIDATES: list[str] = [
    "legacy_ichimoku_variants",
    "legacy_macd_variants",
    "legacy_rsi_variants",
    "legacy_fibonacci_variants",
    "legacy_vortex_variants",
    "legacy_moving_average_variants",
    "legacy_pattern_scanners",
    "legacy_statistical_explorers",
    "legacy_buy_sell_duplications",
]

ALLOWED_DIRECTIONS = {"long", "short", "both"}


def _cooldown_seconds(policy: str) -> int:
    value = str(policy or "").strip().lower()
    if value.endswith("s"):
        try:
            return max(1, int(value[:-1].split(":")[-1]))
        except ValueError:
            return 180
    return 180


def seed_canonical_strategy_registry(db: Session) -> None:
    existing = {row.strategy_id: row for row in db.query(CanonicalStrategyRegistry).all()}

    for item in CANONICAL_STRATEGIES:
        strategy_id = item["strategy_id"]
        if strategy_id in existing:
            continue
        db.add(
            CanonicalStrategyRegistry(
                strategy_id=strategy_id,
                strategy_family=item["strategy_family"],
                direction="both",
                market_regime=item["market_regime"],
                entry_logic_version="v1",
                exit_logic_version="v1",
                risk_profile="balanced",
                is_enabled=bool(item["enabled"]),
                priority=int(item["priority"]),
                cooldown_policy="symbol:180s",
                weight=1.0,
                entry_long={"contract": "entry_long", "version": "v1"},
                entry_short={"contract": "entry_short", "version": "v1"},
                exit_long={"contract": "exit_long", "version": "v1"},
                exit_short={"contract": "exit_short", "version": "v1"},
                invalid_state_rules=["double_intent_conflict", "symbol_direction_conflict"],
                cooldown_rules={"policy": "symbol", "seconds": 180},
                risk_rules={"single_symbol_single_direction": True, "atr_stop_required": True, "rr_target_required": True},
                is_legacy_candidate=False,
                in_production_path=True,
            )
        )

    for legacy_id in LEGACY_CANDIDATES:
        if legacy_id in existing:
            continue
        db.add(
            CanonicalStrategyRegistry(
                strategy_id=legacy_id,
                strategy_family="legacy",
                direction="both",
                market_regime="any",
                entry_logic_version="legacy",
                exit_logic_version="legacy",
                risk_profile="legacy",
                is_enabled=False,
                priority=999,
                cooldown_policy="symbol:300s",
                weight=0.0,
                entry_long={},
                entry_short={},
                exit_long={},
                exit_short={},
                invalid_state_rules=["legacy_blocked"],
                cooldown_rules={"policy": "none"},
                risk_rules={"mode": "legacy_candidate"},
                is_legacy_candidate=True,
                in_production_path=False,
                forced_disable_reason="legacy_candidate_removed_from_production",
            )
        )

    db.commit()


def list_registry(db: Session, *, include_legacy: bool) -> list[CanonicalStrategyRegistry]:
    query = db.query(CanonicalStrategyRegistry)
    if not include_legacy:
        query = query.filter(CanonicalStrategyRegistry.is_legacy_candidate.is_(False))
    return query.order_by(CanonicalStrategyRegistry.priority.asc(), CanonicalStrategyRegistry.strategy_id.asc()).all()


def update_registry_entry(
    db: Session,
    strategy_id: str,
    *,
    direction: str | None,
    market_regime: str | None,
    is_enabled: bool | None,
    priority: int | None,
    cooldown_policy: str | None,
    weight: float | None,
    risk_profile: str | None,
    forced_disable_reason: str | None,
) -> CanonicalStrategyRegistry | None:
    row = db.query(CanonicalStrategyRegistry).filter(CanonicalStrategyRegistry.strategy_id == strategy_id).first()
    if row is None:
        return None

    if direction is not None:
        candidate = str(direction).strip().lower()
        if candidate in ALLOWED_DIRECTIONS:
            row.direction = candidate
    if market_regime is not None:
        row.market_regime = str(market_regime).strip().lower() or row.market_regime
    if is_enabled is not None:
        row.is_enabled = bool(is_enabled)
    if priority is not None:
        row.priority = int(priority)
    if cooldown_policy is not None:
        row.cooldown_policy = str(cooldown_policy).strip() or row.cooldown_policy
    if weight is not None:
        row.weight = float(weight)
    if risk_profile is not None:
        row.risk_profile = str(risk_profile).strip() or row.risk_profile
    if forced_disable_reason is not None:
        row.forced_disable_reason = str(forced_disable_reason).strip() or None

    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def refresh_registry_metrics(db: Session) -> list[CanonicalStrategyRegistry]:
    rows = db.query(CanonicalStrategyRegistry).all()
    for row in rows:
        signals = (
            db.query(PendingSignal)
            .filter(PendingSignal.strategy_code == row.strategy_id)
            .order_by(PendingSignal.created_at.desc())
            .limit(50)
            .all()
        )

        total = len(signals)
        filled = sum(1 for item in signals if str(item.status or "").lower() == "filled")
        rejected = sum(1 for item in signals if str(item.status or "").lower() in {"rejected", "blocked", "risk_blocked"})
        allow_like = sum(1 for item in signals if str(item.status or "").lower() in {"pending", "sent", "approved", "filled"})

        row.last_50_signal_quality = round((filled / total) * 100, 2) if total else 0.0
        row.false_allow_rate = round((rejected / allow_like) * 100, 2) if allow_like else 0.0
        row.false_reject_rate = round((rejected / total) * 100, 2) if total else 0.0
        row.risk_block_reason = next((item.blocked_reason_code for item in signals if item.blocked_reason_code), None)

        latest_created = signals[0].created_at if signals else None
        if latest_created is not None:
            base = latest_created if latest_created.tzinfo else latest_created.replace(tzinfo=timezone.utc)
            cooldown_until = base + timedelta(seconds=_cooldown_seconds(row.cooldown_policy))
            row.cooldown_state = "cooldown" if datetime.now(timezone.utc) < cooldown_until else "ready"
        else:
            row.cooldown_state = "ready"

        row.updated_at = datetime.now(timezone.utc)

    db.commit()
    return rows


def enabled_production_strategies(db: Session) -> list[CanonicalStrategyRegistry]:
    return (
        db.query(CanonicalStrategyRegistry)
        .filter(
            CanonicalStrategyRegistry.is_enabled.is_(True),
            CanonicalStrategyRegistry.in_production_path.is_(True),
            CanonicalStrategyRegistry.is_legacy_candidate.is_(False),
        )
        .order_by(CanonicalStrategyRegistry.priority.asc(), CanonicalStrategyRegistry.strategy_id.asc())
        .all()
    )
