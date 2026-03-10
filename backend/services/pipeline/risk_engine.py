from sqlalchemy.orm import Session

from models import AdminControl, PaperPosition, RiskPolicy, User
from services.pipeline.events import RiskDecision, SignalDecision


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
    quantity = round(max((1000 * notional_risk) / max(market_price, 0.0001), 0.0001), 6)
    return RiskDecision(
        approved=True,
        size=quantity,
        leverage=allowed_leverage,
        stop=signal.proposed_stop,
        take_profit=signal.proposed_take_profit,
        risk_tags=["approved"],
    )