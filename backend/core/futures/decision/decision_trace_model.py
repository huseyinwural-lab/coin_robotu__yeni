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
    leverage_decision: str
    confidence_multiplier: float
    microstructure_multiplier: float
    liquidation_multiplier: float
    funding_multiplier: float
    final_leverage: float
    position_size_ratio: float
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
    leverage_decision: str = "static",
    confidence_multiplier: float = 1.0,
    microstructure_multiplier: float = 1.0,
    liquidation_multiplier: float = 1.0,
    funding_multiplier: float = 1.0,
    final_leverage: float = 1.0,
    position_size_ratio: float = 1.0,
    final_decision: str = "REJECT",
    reason_code: str = "GATE_REJECT",
    decision_layer: str = "GATE",
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
        leverage_decision=leverage_decision,
        confidence_multiplier=round(float(confidence_multiplier), 4),
        microstructure_multiplier=round(float(microstructure_multiplier), 4),
        liquidation_multiplier=round(float(liquidation_multiplier), 4),
        funding_multiplier=round(float(funding_multiplier), 4),
        final_leverage=round(float(final_leverage), 4),
        position_size_ratio=round(float(position_size_ratio), 4),
        final_decision=final_decision,
        reason_code=reason_code,
        decision_layer=decision_layer,
    )
    return asdict(payload)
