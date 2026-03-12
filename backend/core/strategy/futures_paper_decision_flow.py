from core.futures.adl.adl_gate import ADLGate
from core.futures.liquidation_protection.liquidation_gate import LiquidationGate
from core.risk.futures_risk_engine import evaluate_futures_risk


def run_futures_paper_decision_flow(
    *,
    signal: dict,
    position: object,
    portfolio_state: dict,
    policy_state: dict,
    funding_bias: dict,
    microstructure_result: dict,
) -> dict:
    micro_gate = (microstructure_result or {}).get("gate", {})
    execution_suitability = (microstructure_result or {}).get("execution_suitability", {})

    trace = ["signal", "microstructure_guard"]
    if not micro_gate.get("gate_pass", True):
        return {
            "decision": "REJECT",
            "risk": {},
            "gate": micro_gate,
            "adl_gate": {},
            "execution_suitability": execution_suitability,
            "reasons": [micro_gate.get("gate_reason", "MICROSTRUCTURE_REJECT")],
            "reason_code": micro_gate.get("gate_reason", "MICROSTRUCTURE_REJECT"),
            "trace": [*trace, "decision_reject"],
        }
    if not execution_suitability.get("execution_suitable", True):
        return {
            "decision": "REJECT",
            "risk": {},
            "gate": micro_gate,
            "adl_gate": {},
            "execution_suitability": execution_suitability,
            "reasons": ["EXECUTION_NOT_SUITABLE"],
            "reason_code": "EXECUTION_NOT_SUITABLE",
            "trace": [*trace, "execution_suitability", "decision_reject"],
        }

    risk = evaluate_futures_risk(position, portfolio_state)
    trace.append("risk_engine")

    gate = LiquidationGate().evaluate(
        distance_to_liquidation=float(portfolio_state.get("distance_to_liquidation", 100.0)),
        margin_usage=float(portfolio_state.get("margin_usage", 0.0)),
        cascade_confirmed=policy_state.get("cascade_status") == "CASCADE_CONFIRMED",
        emergency_policy_active=policy_state.get("policy_action") == "FREEZE",
        leverage=float(getattr(position, "leverage", 1.0)),
    )
    trace.append("liquidation_gate")

    adl_state = policy_state.get("adl_state") or {}
    adl_gate = ADLGate().evaluate(
        adl_risk_level=str(adl_state.get("risk_level") or "LOW"),
        adl_pressure_side=str(adl_state.get("dominant_side") or "NONE"),
        portfolio_adl_risk=float(adl_state.get("portfolio_adl_risk") or 0.0),
        trade_side=str(signal.get("side") or "NONE"),
    )
    trace.append("adl_gate")

    decision = "ALLOW"
    reasons: list[str] = []
    if risk["risk_check_result"] == "reject":
        decision = "REJECT"
        reasons.extend(risk["risk_reason"])
    if not gate["gate_pass"]:
        decision = "REJECT"
        reasons.extend(gate["all_reasons"])
    if not adl_gate["adl_gate_pass"]:
        decision = "REJECT"
        reasons.extend(adl_gate["all_reasons"])
    if funding_bias.get("funding_pressure_state") == "HIGH" and funding_bias.get("bias_direction") == "SHORT_BIAS" and signal.get("side") == "LONG":
        decision = "REJECT"
        reasons.append("funding_bias_conflict")
    if str(policy_state.get("policy_state") or "SAFE").upper() in {"CRITICAL", "EMERGENCY"}:
        decision = "REJECT"
        reasons.append(f"POLICY_{str(policy_state.get('policy_state')).upper()}")

    reason_code = "ALLOW"
    if reasons:
        reason_code = sorted(set(reasons))[0]

    return {
        "decision": decision,
        "risk": risk,
        "gate": gate,
        "adl_gate": adl_gate,
        "execution_suitability": execution_suitability,
        "reason_code": reason_code,
        "reasons": sorted(set(reasons)),
        "trace": [*trace, "policy_engine", "paper_decision_allow" if decision == "ALLOW" else "decision_reject"],
    }
