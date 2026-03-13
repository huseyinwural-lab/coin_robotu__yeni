from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import RiskPolicy


def get_user_default_risk_policy(db: Session, user_id: str) -> RiskPolicy | None:
    return (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == user_id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )


def ensure_user_safe_default_risk_policy(
    db: Session,
    user_id: str,
    *,
    commit: bool = False,
    policy_name: str = "Starter Safe (Auto)",
) -> tuple[RiskPolicy, bool]:
    existing = get_user_default_risk_policy(db, user_id)
    if existing is not None:
        return existing, False

    now = datetime.now(timezone.utc)
    row = RiskPolicy(
        user_id=user_id,
        name=policy_name,
        position_size_pct=1.0,
        atr_stop_multiplier=1.8,
        risk_reward_ratio=1.8,
        daily_loss_cutoff_pct=3.0,
        max_open_positions=2,
        max_leverage=2,
        spread_limit_bps=25,
        slippage_limit_bps=35,
        min_liquidity_usdt=150000,
        created_at=now,
        updated_at=now,
    )
    db.add(row)

    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()

    return row, True
