from sqlalchemy.orm import Session

from models import AdminControl, PaperPosition, RiskExposureGroup, RiskPolicy, User
from services.pipeline.events import RiskDecision, SignalDecision


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
    signal: SignalDecision,
    market_type: str,
    market_price: float,
    spread_bps: float,
    atr_pct: float,
) -> RiskDecision:
    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    policy = (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == current_user.id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )

    if control is None or policy is None:
        return RiskDecision(approved=False, size=0, leverage=1, stop=0, take_profit=0, risk_tags=["missing_policy"])

    risk_tags: list[str] = []
    open_positions_list = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == current_user.id, PaperPosition.status == "open")
        .all()
    )
    open_positions = len(open_positions_list)

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

    same_direction_global = [position for position in open_positions_list if position.side == signal.direction]
    direction_limit = int(min(control.max_open_positions_cap, policy.max_open_positions) * 0.8)
    if direction_limit > 0 and len(same_direction_global) >= direction_limit:
        risk_tags.append("global_directional_crowding")

    if market_type == "futures" and atr_pct > 0.05:
        risk_tags.append("futures_liquidation_distance_too_low")

    allowed_leverage = min(control.max_leverage_cap, policy.max_leverage)
    if signal.signal in {"long", "short"} and allowed_leverage < 1:
        risk_tags.append("invalid_leverage_cap")

    if risk_tags:
        return RiskDecision(
            approved=False,
            size=0,
            leverage=allowed_leverage,
            stop=signal.proposed_stop,
            take_profit=signal.proposed_take_profit,
            risk_tags=risk_tags,
        )

    notional_risk = max(policy.position_size_pct, 0.1) / 100
    if atr_pct > 0.04:
        notional_risk *= 0.7
    if atr_pct > 0.06:
        notional_risk *= 0.5
    quantity = round(max((1000 * notional_risk) / max(market_price, 0.0001), 0.0001), 6)
    return RiskDecision(
        approved=True,
        size=quantity,
        leverage=allowed_leverage,
        stop=signal.proposed_stop,
        take_profit=signal.proposed_take_profit,
        risk_tags=["approved", "cluster_checked"],
    )