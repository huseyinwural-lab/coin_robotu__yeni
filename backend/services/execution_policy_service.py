from sqlalchemy.orm import Session

from models import ExecutionPolicy

DEFAULT_POLICY_MAP = {
    "breakout": {
        "execution_style": "aggressive",
        "order_preference": "market_first",
        "timeout_seconds": 4,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 85,
        "execution_urgency": "high",
        "retry_limit": 1,
    },
    "mean_reversion": {
        "execution_style": "passive",
        "order_preference": "limit_first",
        "timeout_seconds": 12,
        "fallback_behavior": "cancel_no_fill",
        "partial_fill_tolerance_pct": 35,
        "execution_urgency": "low",
        "retry_limit": 3,
    },
    "trend_following": {
        "execution_style": "balanced",
        "order_preference": "limit_first",
        "timeout_seconds": 8,
        "fallback_behavior": "market_fallback",
        "partial_fill_tolerance_pct": 60,
        "execution_urgency": "medium",
        "retry_limit": 2,
    },
    "volatility_expansion": {
        "execution_style": "balanced",
        "order_preference": "market_first",
        "timeout_seconds": 6,
        "fallback_behavior": "limit_retry_then_market",
        "partial_fill_tolerance_pct": 70,
        "execution_urgency": "medium",
        "retry_limit": 2,
    },
}


def get_policy_for_strategy(db: Session, strategy_type: str) -> ExecutionPolicy:
    policy = (
        db.query(ExecutionPolicy)
        .filter(ExecutionPolicy.strategy_type == strategy_type, ExecutionPolicy.is_active.is_(True))
        .first()
    )
    if policy:
        return policy

    defaults = DEFAULT_POLICY_MAP.get(strategy_type, DEFAULT_POLICY_MAP["trend_following"])
    policy = ExecutionPolicy(strategy_type=strategy_type, **defaults, is_active=True)
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy
