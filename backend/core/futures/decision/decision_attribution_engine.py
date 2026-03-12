from core.futures.decision.reason_codes import DecisionLayer, ReasonCode


def _map_microstructure_reason(raw_reason: str) -> ReasonCode:
    reason = (raw_reason or "").upper()
    if "SPREAD_SHOCK" in reason:
        return ReasonCode.MICROSTRUCTURE_SPREAD_SHOCK
    if "THINNING" in reason or "DEPTH" in reason:
        return ReasonCode.MICROSTRUCTURE_DEPTH_COLLAPSE
    if "SLIPPAGE" in reason:
        return ReasonCode.MICROSTRUCTURE_SLIPPAGE_ANOMALY
    return ReasonCode.GATE_REJECT


def _map_risk_reason(raw_reason: str) -> ReasonCode:
    reason = (raw_reason or "").upper()
    if "LEVERAGE" in reason:
        return ReasonCode.RISK_LEVERAGE_LIMIT
    if "MARGIN" in reason:
        return ReasonCode.RISK_MARGIN_USAGE
    if "LIQUIDATION" in reason:
        return ReasonCode.LIQUIDATION_DISTANCE_TOO_LOW
    return ReasonCode.GATE_REJECT


def _map_liquidation_reason(raw_reason: str) -> ReasonCode:
    reason = (raw_reason or "").upper()
    if "DISTANCE" in reason:
        return ReasonCode.LIQUIDATION_DISTANCE_TOO_LOW
    if "CASCADE" in reason:
        return ReasonCode.CASCADE_DETECTED
    if "MARGIN" in reason:
        return ReasonCode.RISK_MARGIN_USAGE
    if "LEVERAGE" in reason:
        return ReasonCode.RISK_LEVERAGE_LIMIT
    return ReasonCode.GATE_REJECT


def _map_adl_reason(raw_reason: str, adl_pressure_side: str) -> ReasonCode:
    reason = (raw_reason or "").upper()
    if "LONG" in reason:
        return ReasonCode.ADL_PRESSURE_LONG
    if "SHORT" in reason:
        return ReasonCode.ADL_PRESSURE_SHORT
    side = (adl_pressure_side or "NONE").upper()
    if side == "LONG":
        return ReasonCode.ADL_PRESSURE_LONG
    if side == "SHORT":
        return ReasonCode.ADL_PRESSURE_SHORT
    return ReasonCode.GATE_REJECT


class DecisionAttributionEngine:
    def evaluate(
        self,
        *,
        signal_valid: bool,
        microstructure_pass: bool,
        microstructure_reason: str,
        risk_pass: bool,
        risk_reason: str,
        liquidation_pass: bool,
        liquidation_reason: str,
        adl_pass: bool,
        adl_reason: str,
        adl_pressure_side: str = "NONE",
        policy_pass: bool,
        gate_pass: bool,
    ) -> dict:
        if not signal_valid:
            return {
                "decision": "REJECT",
                "reason_code": ReasonCode.SIGNAL_WEAK.value,
                "decision_layer": DecisionLayer.STRATEGY.value,
            }
        if not microstructure_pass:
            return {
                "decision": "REJECT",
                "reason_code": _map_microstructure_reason(microstructure_reason).value,
                "decision_layer": DecisionLayer.MICROSTRUCTURE.value,
            }
        if not risk_pass:
            return {
                "decision": "REJECT",
                "reason_code": _map_risk_reason(risk_reason).value,
                "decision_layer": DecisionLayer.RISK_ENGINE.value,
            }
        if not liquidation_pass:
            return {
                "decision": "REJECT",
                "reason_code": _map_liquidation_reason(liquidation_reason).value,
                "decision_layer": DecisionLayer.LIQUIDATION.value,
            }
        if not adl_pass:
            return {
                "decision": "REJECT",
                "reason_code": _map_adl_reason(adl_reason, adl_pressure_side).value,
                "decision_layer": DecisionLayer.ADL.value,
            }
        if not policy_pass:
            return {
                "decision": "REJECT",
                "reason_code": ReasonCode.POLICY_BLOCK.value,
                "decision_layer": DecisionLayer.POLICY.value,
            }
        if not gate_pass:
            return {
                "decision": "REJECT",
                "reason_code": ReasonCode.GATE_REJECT.value,
                "decision_layer": DecisionLayer.GATE.value,
            }
        return {
            "decision": "ALLOW",
            "reason_code": ReasonCode.ALLOW.value,
            "decision_layer": DecisionLayer.GATE.value,
        }
