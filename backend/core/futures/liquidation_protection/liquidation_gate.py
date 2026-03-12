class LiquidationGate:
    def evaluate(
        self,
        *,
        distance_to_liquidation: float,
        margin_usage: float,
        cascade_confirmed: bool,
        emergency_policy_active: bool,
        leverage: float,
        leverage_cap: float = 5.0,
    ) -> dict:
        reasons: list[str] = []
        if distance_to_liquidation < 10:
            reasons.append("LIQUIDATION_DISTANCE_TOO_LOW")
        if margin_usage >= 72:
            reasons.append("MARGIN_USAGE_CRITICAL")
        if cascade_confirmed:
            reasons.append("CASCADE_CONFIRMED")
        if emergency_policy_active:
            reasons.append("EMERGENCY_POLICY_ACTIVE")
        if leverage > leverage_cap:
            reasons.append("LEVERAGE_ABOVE_CAP")
        return {
            "gate_pass": len(reasons) == 0,
            "gate_reason": reasons[0] if reasons else "PASS",
            "all_reasons": reasons,
        }


def evaluate_liquidation_gate(
    *,
    distance_to_liquidation: float,
    margin_usage: float,
    cascade_confirmed: bool,
    emergency_policy_active: bool,
    leverage: float,
    leverage_cap: float = 5.0,
) -> dict:
    gate = LiquidationGate()
    return gate.evaluate(
        distance_to_liquidation=distance_to_liquidation,
        margin_usage=margin_usage,
        cascade_confirmed=cascade_confirmed,
        emergency_policy_active=emergency_policy_active,
        leverage=leverage,
        leverage_cap=leverage_cap,
    )
