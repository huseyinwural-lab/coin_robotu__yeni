from sqlalchemy.orm import Session

from models import AdminControl, PaperPosition, RiskExposureGroup, RiskPolicy, User
from services.pipeline.events import RiskDecision, SignalDecision
from services.pipeline.correlation_service import pair_correlation
from services.pipeline.position_sizing_engine import compute_position_sizing, consecutive_losses, daily_loss_usage

MAX_CONSECUTIVE_LOSS_LIMIT = 3


def _evaluate_spot_pullback_risk(
    db: Session,
    *,
    current_user: User,
    signal: SignalDecision,
    market_price: float,
) -> RiskDecision:
    open_positions_list = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == current_user.id, PaperPosition.status == "open")
        .all()
    )

    risk_tags: list[str] = []
    if signal.signal == "none":
        risk_tags.append("no_signal")
    if signal.direction != "long":
        risk_tags.append("spot_long_only")
    if len(open_positions_list) >= 3:
        risk_tags.append("max_open_positions_reached")
    if any(position.symbol.upper() == signal.symbol.upper() for position in open_positions_list):
        risk_tags.append("max_position_per_symbol_reached")

    sizing = compute_position_sizing(db, current_user.id, market_price)
    equity = float(sizing["equity"])
    entry = float(signal.proposed_entry or market_price)
    stop = float(signal.proposed_stop or (entry * 0.99))
    take_profit = float(signal.proposed_take_profit or (entry * 1.02))
    stop_distance = max(abs(entry - stop), entry * 0.01, 0.0001)
    risk_amount_usdt = equity * 0.01
    quantity = round(max(risk_amount_usdt / stop_distance, 0.0001), 6)
    trade_allocation_usdt = quantity * entry

    if risk_tags:
        return RiskDecision(
            approved=False,
            size=0,
            leverage=1,
            stop=stop,
            take_profit=take_profit,
            risk_tags=risk_tags,
            equity=equity,
            trade_allocation_usdt=trade_allocation_usdt,
            risk_amount_usdt=risk_amount_usdt,
        )

    return RiskDecision(
        approved=True,
        size=quantity,
        leverage=1,
        stop=stop,
        take_profit=take_profit,
        risk_tags=["approved", "spot_strategy_1pct_risk", "position_control_3x1"],
        equity=equity,
        trade_allocation_usdt=trade_allocation_usdt,
        risk_amount_usdt=risk_amount_usdt,
    )


def _symbol_in_group(symbol: str, group: RiskExposureGroup) -> bool:
    normalized = {item.upper() for item in group.symbols}
    return bool(normalized) and symbol.upper() in normalized


def _resolve_group_from_list(symbol: str, groups: list[RiskExposureGroup]) -> RiskExposureGroup | None:
    for group in groups:
        if _symbol_in_group(symbol, group):
            return group

    for fallback in ["mid_cap", "all_symbols"]:
        for group in groups:
            if group.name == fallback:
                return group
    return groups[0] if groups else None


def evaluate_risk(
    db: Session,
    *,
    current_user: User,
    cache,
    signal: SignalDecision,
    market_type: str,
    market_price: float,
    spread_bps: float,
    atr_pct: float,
) -> RiskDecision:
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()

    if signal.strategy_id in {"spot_pullback", "spot_pullback_v1", "spot_range_reversion", "spot_range_reversion_v1"}:
        if control is None:
            return RiskDecision(
                approved=False,
                size=0,
                leverage=1,
                stop=signal.proposed_stop,
                take_profit=signal.proposed_take_profit,
                risk_tags=["missing_policy"],
            )
        return _evaluate_spot_pullback_risk(
            db,
            current_user=current_user,
            signal=signal,
            market_price=market_price,
        )

    policy = (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == current_user.id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )

    if control is None or policy is None:
        return RiskDecision(
            approved=False,
            size=0,
            leverage=1,
            stop=0,
            take_profit=0,
            risk_tags=["missing_policy"],
        )

    risk_tags: list[str] = []
    open_positions_list = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == current_user.id, PaperPosition.status == "open")
        .all()
    )
    open_positions = len(open_positions_list)

    sizing = compute_position_sizing(db, current_user.id, market_price)
    daily_loss = daily_loss_usage(db, current_user.id)
    loss_streak = consecutive_losses(db, current_user.id)

    if control.emergency_mode:
        risk_tags.append("emergency_mode_enabled")
    if signal.signal == "none":
        risk_tags.append("no_signal")
    if spread_bps > min(control.max_spread_bps, policy.spread_limit_bps):
        risk_tags.append("spread_too_wide")
    if atr_pct > 0.07:
        risk_tags.append("volatility_rejection")
    if open_positions >= min(control.max_open_positions_cap, policy.max_open_positions):
        risk_tags.append("max_open_positions_reached")
    if daily_loss["limit_exceeded"]:
        risk_tags.append("daily_loss_limit_exceeded")
    if loss_streak >= MAX_CONSECUTIVE_LOSS_LIMIT:
        risk_tags.append("consecutive_loss_limit_exceeded")

    groups = db.query(RiskExposureGroup).all()
    target_group = _resolve_group_from_list(signal.symbol, groups)
    if target_group:
        target_group_symbols = {item.upper() for item in target_group.symbols}

        group_positions = []
        for position in open_positions_list:
            is_in_group = (
                (not target_group_symbols and target_group.name in {"mid_cap", "all_symbols"})
                or (target_group_symbols and position.symbol.upper() in target_group_symbols)
            )
            if is_in_group:
                group_positions.append(position)

        same_direction_positions = [position for position in group_positions if position.side == signal.direction]
        if len(group_positions) >= target_group.max_group_open_positions:
            risk_tags.append("group_open_positions_limit")
        if len(same_direction_positions) >= target_group.max_group_directional_positions:
            risk_tags.append("directional_cluster_limit")

        theoretical_group_risk = sum(
            abs((position.entry_price - position.stop_loss) * position.quantity * position.leverage)
            for position in group_positions
        )
        proposed_risk = abs(signal.proposed_entry - signal.proposed_stop) * max(market_price, 0.0001)
        if theoretical_group_risk + proposed_risk >= (target_group.max_group_risk_pct * 10):
            risk_tags.append("group_total_risk_limit")

        high_corr_same_direction = 0
        max_corr = 0.0
        for position in open_positions_list:
            if position.side != signal.direction:
                continue
            corr = abs(pair_correlation(cache, signal.symbol, position.symbol, window=200))
            max_corr = max(max_corr, corr)
            if corr >= 0.75:
                high_corr_same_direction += 1

        if high_corr_same_direction >= 2:
            risk_tags.append("correlated_cluster_overload")
        elif high_corr_same_direction == 1 and max_corr >= 0.9:
            risk_tags.append("high_pair_correlation")

    same_direction_global = [position for position in open_positions_list if position.side == signal.direction]
    direction_limit = int(min(control.max_open_positions_cap, policy.max_open_positions) * 0.8)
    if direction_limit > 0 and len(same_direction_global) >= direction_limit:
        risk_tags.append("global_directional_crowding")

    if market_type == "futures" and atr_pct > 0.05:
        risk_tags.append("futures_liquidation_distance_too_low")

    allowed_leverage = min(control.max_leverage_cap, policy.max_leverage)
    if signal.signal in {"long", "short"} and allowed_leverage < 1:
        risk_tags.append("invalid_leverage_cap")

    projected_total_notional = sum(float(position.entry_price) * float(position.quantity) for position in open_positions_list)
    projected_total_notional += float(sizing["trade_allocation_usdt"])
    max_portfolio_exposure_pct = min(90.0, float(policy.position_size_pct) * float(policy.max_open_positions))
    max_portfolio_notional = float(sizing["equity"]) * (max_portfolio_exposure_pct / 100)
    if projected_total_notional > max_portfolio_notional:
        risk_tags.append("max_portfolio_exposure_exceeded")

    account_risk_pct = (float(sizing["risk_amount_usdt"]) / max(float(sizing["equity"]), 0.01)) * 100
    if account_risk_pct > min(float(policy.daily_loss_cutoff_pct), 5.0):
        risk_tags.append("max_risk_per_trade_exceeded")

    if risk_tags:
        return RiskDecision(
            approved=False,
            size=0,
            leverage=allowed_leverage,
            stop=signal.proposed_stop,
            take_profit=signal.proposed_take_profit,
            risk_tags=risk_tags,
            equity=float(sizing["equity"]),
            trade_allocation_usdt=float(sizing["trade_allocation_usdt"]),
            risk_amount_usdt=float(sizing["risk_amount_usdt"]),
        )

    quantity = float(sizing["quantity"])
    if atr_pct > 0.04:
        quantity = round(quantity * 0.7, 6)
    if atr_pct > 0.06:
        quantity = round(quantity * 0.5, 6)
    quantity = max(quantity, 0.0001)

    effective_leverage = 1 if market_type == "spot" else allowed_leverage
    return RiskDecision(
        approved=True,
        size=quantity,
        leverage=effective_leverage,
        stop=signal.proposed_stop,
        take_profit=signal.proposed_take_profit,
        risk_tags=["approved", "cluster_checked", "hard_veto_compliant", "position_sizing_engine"],
        equity=float(sizing["equity"]),
        trade_allocation_usdt=float(sizing["trade_allocation_usdt"]),
        risk_amount_usdt=float(sizing["risk_amount_usdt"]),
    )