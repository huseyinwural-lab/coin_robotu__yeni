from sqlalchemy.orm import Session

from models import AdminControl, PaperPosition, RiskExposureGroup, RiskPolicy, User
from services.pipeline.events import RiskDecision, SignalDecision


def _resolve_group(db: Session, symbol: str) -> RiskExposureGroup | None:
    groups = db.query(RiskExposureGroup).all()
    for group in groups:
        normalized = {item.upper() for item in group.symbols}
        if normalized and symbol.upper() in normalized:
            return group
    return db.query(RiskExposureGroup).filter(RiskExposureGroup.name == "all_symbols").first()


def evaluate_risk(
    db: Session,
    *,
    current_user: User,
    signal: SignalDecision,
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
    open_positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == current_user.id, PaperPosition.status == "open")
        .count()
    )
    open_positions_query = db.query(PaperPosition).filter(PaperPosition.user_id == current_user.id, PaperPosition.status == "open")
    open_positions_list = open_positions_query.all()

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

    group = _resolve_group(db, signal.symbol)
    if group:
        group_symbols = {symbol.upper() for symbol in group.symbols}
        group_positions = [
            position
            for position in open_positions_list
            if not group_symbols or position.symbol.upper() in group_symbols
        ]
        same_direction_positions = [
            position for position in group_positions if position.side == signal.direction
        ]
        if len(group_positions) >= group.max_group_open_positions:
            risk_tags.append("group_open_positions_limit")
        if len(same_direction_positions) >= group.max_group_directional_positions:
            risk_tags.append("directional_cluster_limit")

        theoretical_group_risk = sum(
            abs((position.entry_price - position.stop_loss) * position.quantity * position.leverage)
            for position in group_positions
        )
        if theoretical_group_risk >= (group.max_group_risk_pct * 10):
            risk_tags.append("group_total_risk_limit")

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
        risk_tags=["approved"],
    )