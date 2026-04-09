from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import CanonicalStrategyRegistry, PendingSignal


GLOBAL_RISK_POLICY = {
    "max_positions": 5,
    "risk_per_trade_pct": 1.5,
    "cooldown_symbol_seconds": 21600,
    "stop_policy": "atr_based",
    "take_profit_policy": "rr_based",
    "exit_policy": "trend_flip_or_opposite_signal",
}


def _contract(
    *,
    family: str,
    regime: str,
    enabled: bool,
    priority: int,
    weight: float,
    entry_long: list[str],
    entry_short: list[str],
    exit_long: list[str],
    exit_short: list[str],
    stop_loss: dict,
    take_profit: dict,
    invalidation: list[str],
    signal_score: dict,
) -> dict:
    return {
        "strategy_family": family,
        "market_regime": regime,
        "enabled": enabled,
        "priority": priority,
        "weight": weight,
        "entry_long": {"rules": entry_long, "version": "v2"},
        "entry_short": {"rules": entry_short, "version": "v2"},
        "exit_long": {"rules": exit_long, "version": "v2"},
        "exit_short": {"rules": exit_short, "version": "v2"},
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "invalidation": {"rules": invalidation, "version": "v2"},
        "signal_score": signal_score,
    }


CANONICAL_STRATEGIES: dict[str, dict] = {
    "ichimoku_trend_continuation": _contract(
        family="trend",
        regime="trend",
        enabled=True,
        priority=10,
        weight=3,
        entry_long=["tenkan_cross_up_kijun", "price_above_kumo", "senkou_a_above_senkou_b", "chikou_above_price"],
        entry_short=["tenkan_cross_down_kijun", "price_below_kumo", "senkou_a_below_senkou_b", "chikou_below_price"],
        exit_long=["tenkan_below_kijun", "price_below_kijun"],
        exit_short=["tenkan_above_kijun", "price_above_kijun"],
        stop_loss={"type": "atr", "multiplier": 2.0},
        take_profit={"type": "rr", "ratio": 2.5},
        invalidation=["price_returns_into_kumo"],
        signal_score={"strong": 3, "medium": 2},
    ),
    "golden_cross_regime": _contract(
        family="trend",
        regime="trend",
        enabled=False,
        priority=20,
        weight=2,
        entry_long=["ma50_above_ma200", "price_above_ma50", "ma50_slope_positive"],
        entry_short=["ma50_below_ma200", "price_below_ma50", "ma50_slope_negative"],
        exit_long=["ma50_below_ma200"],
        exit_short=["ma50_above_ma200"],
        stop_loss={"type": "atr", "multiplier": 1.8},
        take_profit={"type": "rr", "ratio": 3.0},
        invalidation=["price_inside_ma_cluster"],
        signal_score={"base": 2},
    ),
    "supertrend_flip": _contract(
        family="trend",
        regime="trend",
        enabled=True,
        priority=15,
        weight=2,
        entry_long=["price_crosses_above_supertrend"],
        entry_short=["price_crosses_below_supertrend"],
        exit_long=["supertrend_flip_bearish"],
        exit_short=["supertrend_flip_bullish"],
        stop_loss={"type": "supertrend_band"},
        take_profit={"type": "trailing_stop"},
        invalidation=["price_sideways_inside_atr_band"],
        signal_score={"base": 2},
    ),
    "vortex_directional_cross": _contract(
        family="trend",
        regime="trend",
        enabled=False,
        priority=30,
        weight=2,
        entry_long=["vortex_plus_crosses_above_minus"],
        entry_short=["vortex_minus_crosses_above_plus"],
        exit_long=["opposite_vortex_cross"],
        exit_short=["opposite_vortex_cross"],
        stop_loss={"type": "atr", "multiplier": 1.5},
        take_profit={"type": "rr", "ratio": 2.0},
        invalidation=["vortex_lines_converge"],
        signal_score={"base": 2},
    ),
    "bollinger_squeeze_breakout": _contract(
        family="breakout",
        regime="breakout",
        enabled=True,
        priority=12,
        weight=3,
        entry_long=["bandwidth_below_percentile", "price_breaks_upper_band", "volume_spike"],
        entry_short=["bandwidth_below_percentile", "price_breaks_lower_band", "volume_spike"],
        exit_long=["price_returns_inside_bands"],
        exit_short=["price_returns_inside_bands"],
        stop_loss={"type": "atr", "multiplier": 1.5},
        take_profit={"type": "rr", "ratio": 2.5},
        invalidation=["breakout_fails_next_3_bars"],
        signal_score={"breakout": 3},
    ),
    "moving_momentum": _contract(
        family="trend",
        regime="trend",
        enabled=False,
        priority=25,
        weight=2,
        entry_long=["ma20_above_ma150", "macd_bullish_cross", "stoch_oversold_recovery"],
        entry_short=["ma20_below_ma150", "macd_bearish_cross", "stoch_overbought_rejection"],
        exit_long=["macd_cross_down"],
        exit_short=["macd_cross_up"],
        stop_loss={"type": "atr", "multiplier": 1.7},
        take_profit={"type": "rr", "ratio": 2.0},
        invalidation=["ma_slope_flat"],
        signal_score={"base": 2},
    ),
    "fibonacci_pullback_continuation": _contract(
        family="pullback",
        regime="pullback",
        enabled=False,
        priority=35,
        weight=2,
        entry_long=["price_above_ma200", "pullback_in_38_61_zone", "bullish_trigger_candle"],
        entry_short=["price_below_ma200", "pullback_in_38_61_zone", "bearish_trigger_candle"],
        exit_long=["price_breaks_previous_swing_low"],
        exit_short=["price_breaks_previous_swing_high"],
        stop_loss={"type": "swing_below_above"},
        take_profit={"type": "previous_swing_target"},
        invalidation=["fib_zone_breaks"],
        signal_score={"base": 2},
    ),
    "macd_impulse": _contract(
        family="trend",
        regime="trend",
        enabled=True,
        priority=18,
        weight=2,
        entry_long=["macd_above_signal", "histogram_positive", "close_above_recent_high"],
        entry_short=["macd_below_signal", "histogram_negative", "close_below_recent_low"],
        exit_long=["histogram_turns_negative"],
        exit_short=["histogram_turns_positive"],
        stop_loss={"type": "atr", "multiplier": 1.5},
        take_profit={"type": "rr", "ratio": 2.0},
        invalidation=["macd_flat"],
        signal_score={"base": 2},
    ),
    "fisher_reversal": _contract(
        family="reversal",
        regime="reversal",
        enabled=False,
        priority=50,
        weight=1,
        entry_long=["fisher_crosses_up_previous", "fisher_extreme_negative_zone"],
        entry_short=["fisher_crosses_down_previous", "fisher_extreme_positive_zone"],
        exit_long=["fisher_peak"],
        exit_short=["fisher_trough"],
        stop_loss={"type": "recent_swing"},
        take_profit={"type": "rr", "ratio": 1.8},
        invalidation=["fisher_stays_flat"],
        signal_score={"base": 1},
    ),
    "divergence_reversal_suite": _contract(
        family="reversal",
        regime="reversal",
        enabled=False,
        priority=55,
        weight=1,
        entry_long=["price_lower_low", "indicator_higher_low"],
        entry_short=["price_higher_high", "indicator_lower_high"],
        exit_long=["trend_continuation_resumes"],
        exit_short=["trend_continuation_resumes"],
        stop_loss={"type": "swing_low_high"},
        take_profit={"type": "mid_range"},
        invalidation=["divergence_disappears"],
        signal_score={"base": 1},
    ),
    "structure_breakout": _contract(
        family="breakout",
        regime="breakout",
        enabled=False,
        priority=22,
        weight=2,
        entry_long=["descending_trendline_break", "triangle_breakout", "double_bottom_neckline_break"],
        entry_short=["ascending_trendline_break", "triangle_breakdown", "double_top_neckline_break"],
        exit_long=["return_inside_structure"],
        exit_short=["return_inside_structure"],
        stop_loss={"type": "atr", "multiplier": 1.6},
        take_profit={"type": "pattern_projection"},
        invalidation=["false_breakout"],
        signal_score={"base": 2},
    ),
    "stochastic_exhaustion_reentry": _contract(
        family="reversal",
        regime="reversal",
        enabled=False,
        priority=60,
        weight=1,
        entry_long=["stochastic_below_20", "price_breaks_trigger_high"],
        entry_short=["stochastic_above_80", "price_breaks_trigger_low"],
        exit_long=["stochastic_above_70"],
        exit_short=["stochastic_below_30"],
        stop_loss={"type": "atr", "multiplier": 1.4},
        take_profit={"type": "rr", "ratio": 1.5},
        invalidation=["oscillator_stays_extreme"],
        signal_score={"base": 1},
    ),
}


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

    for strategy_id, item in CANONICAL_STRATEGIES.items():
        if strategy_id in existing:
            row = existing[strategy_id]
            row.strategy_family = item["strategy_family"]
            row.entry_logic_version = "v2"
            row.exit_logic_version = "v2"
            row.market_regime = item["market_regime"]
            row.risk_profile = "global_standardized"
            row.priority = int(item["priority"])
            row.cooldown_policy = "symbol:21600s"
            row.weight = float(item["weight"])
            row.entry_long = item["entry_long"]
            row.entry_short = item["entry_short"]
            row.exit_long = item["exit_long"]
            row.exit_short = item["exit_short"]
            row.stop_loss = item["stop_loss"]
            row.take_profit = item["take_profit"]
            row.invalidation = item["invalidation"]
            row.signal_score = item["signal_score"]
            row.invalid_state_rules = ["double_intent_conflict", "symbol_direction_conflict"]
            row.cooldown_rules = {"policy": "symbol", "seconds": 21600}
            row.risk_rules = {
                "single_symbol_single_direction": True,
                "atr_stop_required": True,
                "rr_target_required": True,
                "max_positions": GLOBAL_RISK_POLICY["max_positions"],
                "risk_per_trade_pct": GLOBAL_RISK_POLICY["risk_per_trade_pct"],
            }
            row.is_legacy_candidate = False
            row.in_production_path = True
            continue

        db.add(
            CanonicalStrategyRegistry(
                strategy_id=strategy_id,
                strategy_family=item["strategy_family"],
                direction="both",
                market_regime=item["market_regime"],
                entry_logic_version="v2",
                exit_logic_version="v2",
                risk_profile="global_standardized",
                is_enabled=bool(item["enabled"]),
                priority=int(item["priority"]),
                cooldown_policy="symbol:21600s",
                weight=float(item["weight"]),
                entry_long=item["entry_long"],
                entry_short=item["entry_short"],
                exit_long=item["exit_long"],
                exit_short=item["exit_short"],
                stop_loss=item["stop_loss"],
                take_profit=item["take_profit"],
                invalidation=item["invalidation"],
                signal_score=item["signal_score"],
                invalid_state_rules=["double_intent_conflict", "symbol_direction_conflict"],
                cooldown_rules={"policy": "symbol", "seconds": 21600},
                risk_rules={
                    "single_symbol_single_direction": True,
                    "atr_stop_required": True,
                    "rr_target_required": True,
                    "max_positions": GLOBAL_RISK_POLICY["max_positions"],
                    "risk_per_trade_pct": GLOBAL_RISK_POLICY["risk_per_trade_pct"],
                },
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
                stop_loss={},
                take_profit={},
                invalidation={},
                signal_score={},
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


def tracked_core_canonical_strategies(db: Session) -> list[CanonicalStrategyRegistry]:
    tracked_ids = list(CANONICAL_STRATEGIES.keys())
    rows = (
        db.query(CanonicalStrategyRegistry)
        .filter(
            CanonicalStrategyRegistry.strategy_id.in_(tracked_ids),
            CanonicalStrategyRegistry.is_legacy_candidate.is_(False),
            CanonicalStrategyRegistry.in_production_path.is_(True),
        )
        .all()
    )
    by_id = {row.strategy_id: row for row in rows}
    ordered = [by_id[sid] for sid in tracked_ids if sid in by_id]
    return ordered
