from core.futures.liquidation_protection.liquidation_gate import evaluate_liquidation_gate
from core.risk.futures_risk_engine import evaluate_futures_risk


def run_futures_paper_decision_flow(*, signal: dict, position: object, portfolio_state: dict, policy_state: dict, funding_bias: dict) -> dict:
    risk = evaluate_futures_risk(position, portfolio_state)
    gate = evaluate_liquidation_gate(
        distance_to_liquidation=float(portfolio_state.get("distance_to_liquidation", 100.0)),
        margin_usage=float(portfolio_state.get("margin_usage", 0.0)),
        cascade_confirmed=policy_state.get("cascade_status") == "CASCADE_CONFIRMED",
        emergency_policy_active=policy_state.get("policy_action") == "FREEZE",
        leverage=float(getattr(position, "leverage", 1.0)),
    )

    decision = "ALLOW"
    reasons: list[str] = []
    if risk["risk_check_result"] == "reject":
        decision = "REJECT"
        reasons.extend(risk["risk_reason"])
    if not gate["gate_pass"]:
        decision = "REJECT"
        reasons.extend(gate["all_reasons"])
    if funding_bias.get("funding_pressure_state") == "HIGH" and funding_bias.get("bias_direction") == "SHORT_BIAS" and signal.get("side") == "LONG":
        decision = "REJECT"
        reasons.append("funding_bias_conflict")

    return {
        "decision": decision,
        "risk": risk,
        "gate": gate,
        "reasons": sorted(set(reasons)),
        "trace": ["signal", "risk", "gate", "funding_bias", "decision"],
    }
