from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class FuturesDecisionTrace:
    trace_id: str
    timestamp: str
    symbol: str
    strategy: str
    side: str
    signal_confidence: float
    regime: str
    microstructure_result: str
    risk_result: str
    liquidation_result: str
    adl_result: str
    final_decision: str
    reason_code: str
    decision_layer: str


def build_decision_trace(
    *,
    symbol: str,
    strategy: str,
    side: str,
    signal_confidence: float,
    regime: str,
    microstructure_result: str,
    risk_result: str,
    liquidation_result: str,
    adl_result: str,
    final_decision: str,
    reason_code: str,
    decision_layer: str,
) -> dict:
    payload = FuturesDecisionTrace(
        trace_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=symbol,
        strategy=strategy,
        side=side,
        signal_confidence=round(float(signal_confidence), 4),
        regime=regime,
        microstructure_result=microstructure_result,
        risk_result=risk_result,
        liquidation_result=liquidation_result,
        adl_result=adl_result,
        final_decision=final_decision,
        reason_code=reason_code,
        decision_layer=decision_layer,
    )
    return asdict(payload)
