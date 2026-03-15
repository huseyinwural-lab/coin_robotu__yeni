from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class DecisionFeedbackEvent:
    symbol: str
    decision: str
    strategy_attribution: str
    filter_attribution: str | None
    confidence: float
    decision_timestamp: str
    outcome_placeholder: str | None = None


def build_decision_feedback_event(
    *,
    symbol: str,
    decision: str,
    strategy_attribution: str,
    filter_attribution: str | None,
    confidence: float,
) -> DecisionFeedbackEvent:
    return DecisionFeedbackEvent(
        symbol=str(symbol or "").upper(),
        decision=str(decision or "PASS").upper(),
        strategy_attribution=str(strategy_attribution or "unknown"),
        filter_attribution=filter_attribution,
        confidence=float(confidence or 0.0),
        decision_timestamp=datetime.now(timezone.utc).isoformat(),
        outcome_placeholder=None,
    )
