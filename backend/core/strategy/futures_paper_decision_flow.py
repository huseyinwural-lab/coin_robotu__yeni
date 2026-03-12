from core.futures.decision.decision_attribution_engine import DecisionAttributionEngine
from core.futures.decision.decision_trace_model import build_decision_trace
from core.futures.decision.reason_codes import ReasonCode
from core.futures.leverage.leverage_engine import LeverageEngine
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
    strategy_id: str,
) -> dict:
    micro_gate = (microstructure_result or {}).get("gate", {})
    execution_suitability = (microstructure_result or {}).get("execution_suitability", {})

    signal_side = str(signal.get("side") or "NONE").upper()
    signal_valid = signal_side in {"LONG", "SHORT"}
    trace = [
        "signal",
        "microstructure_guard",
        "risk_engine",
        "liquidation_protection",
        "adl_shield",
        "dynamic_leverage_engine",
        "policy_engine",
        "hard_gate",
        "attribution",
        "decision_trace",
    ]

    risk = evaluate_futures_risk(position, portfolio_state)

    gate = LiquidationGate().evaluate(
        distance_to_liquidation=float(portfolio_state.get("distance_to_liquidation", 100.0)),
        margin_usage=float(portfolio_state.get("margin_usage", 0.0)),
        cascade_confirmed=policy_state.get("cascade_status") == "CASCADE_CONFIRMED",
        emergency_policy_active=policy_state.get("policy_action") == "FREEZE",
        leverage=float(getattr(position, "leverage", 1.0)),
    )

    adl_state = policy_state.get("adl_state") or {}
    adl_gate = ADLGate().evaluate(
        adl_risk_level=str(adl_state.get("risk_level") or "LOW"),
        adl_pressure_side=str(adl_state.get("dominant_side") or "NONE"),
        portfolio_adl_risk=float(adl_state.get("portfolio_adl_risk") or 0.0),
        trade_side=str(signal.get("side") or "NONE"),
    )

    micro_aggregate = (microstructure_result or {}).get("aggregate") or {}
    spread_state = ((microstructure_result or {}).get("spread") or {}).get("spread_state", "NORMAL")
    depth_state = ((microstructure_result or {}).get("thinning") or {}).get("thinning_state", "NORMAL")
    leverage_result = LeverageEngine().evaluate(
        symbol=str(signal.get("symbol") or "UNKNOWN"),
        strategy=strategy_id,
        side=signal_side,
        base_leverage=float(getattr(position, "leverage", 1.0)),
        confidence=float(signal.get("confidence") or 0.0),
        microstructure_risk_score=float(micro_aggregate.get("microstructure_risk_score") or 0.0),
        execution_suitability=execution_suitability,
        spread_state=str(spread_state),
        depth_state=str(depth_state),
        distance_to_liquidation=float(portfolio_state.get("distance_to_liquidation", 100.0)),
        funding_bias=funding_bias,
        portfolio_leverage=float(portfolio_state.get("portfolio_leverage", 0.0)),
    )
    leverage_decision = leverage_result["decision"]
    leverage_trace_extension = leverage_result["decision_trace_extension"]

    microstructure_pass = bool(micro_gate.get("gate_pass", True)) and bool(execution_suitability.get("execution_suitable", True))
    risk_pass = risk["risk_check_result"] != "reject"
    liquidation_pass = bool(gate.get("gate_pass", True))
    adl_pass = bool(adl_gate.get("adl_gate_pass", True))

    policy_state_label = str(policy_state.get("policy_state") or "SAFE").upper()
    policy_action = str(policy_state.get("policy_action") or "ALLOW").upper()
    policy_block = policy_state_label in {"CRITICAL", "EMERGENCY"} or policy_action in {"FREEZE", "FORCE_REDUCE"}

    funding_conflict = (
        funding_bias.get("funding_pressure_state") == "HIGH"
        and funding_bias.get("bias_direction") == "SHORT_BIAS"
        and signal_side == "LONG"
    )
    policy_pass = not policy_block and not funding_conflict
    hard_gate_pass = signal_valid and microstructure_pass and risk_pass and liquidation_pass and adl_pass and policy_pass

    attribution = DecisionAttributionEngine().evaluate(
        signal_valid=signal_valid,
        microstructure_pass=microstructure_pass,
        microstructure_reason=micro_gate.get("gate_reason", ""),
        risk_pass=risk_pass,
        risk_reason=(risk.get("risk_reason") or [""])[0],
        liquidation_pass=liquidation_pass,
        liquidation_reason=gate.get("gate_reason", ""),
        adl_pass=adl_pass,
        adl_reason=adl_gate.get("reason", ""),
        adl_pressure_side=str(adl_state.get("dominant_side") or "NONE"),
        policy_pass=policy_pass,
        gate_pass=hard_gate_pass,
    )

    reasons: list[str] = []
    if not signal_valid:
        reasons.append(ReasonCode.SIGNAL_WEAK.value)
    if not microstructure_pass:
        reasons.append(str(micro_gate.get("gate_reason") or ReasonCode.GATE_REJECT.value))
    if not risk_pass:
        reasons.extend(risk.get("risk_reason", []))
    if not liquidation_pass:
        reasons.extend(gate.get("all_reasons", []))
    if not adl_pass:
        reasons.extend(adl_gate.get("all_reasons", []))
    if funding_conflict:
        reasons.append(ReasonCode.POLICY_BLOCK.value)
    if policy_block:
        reasons.append(ReasonCode.POLICY_BLOCK.value)

    decision = attribution["decision"]
    reason_code = attribution["reason_code"]

    decision_trace = build_decision_trace(
        symbol=str(signal.get("symbol") or "UNKNOWN"),
        strategy=strategy_id,
        side=signal_side,
        signal_confidence=float(signal.get("confidence") or 0.0),
        regime=str(signal.get("regime") or "UNKNOWN"),
        microstructure_result="PASS" if microstructure_pass else "REJECT",
        risk_result="PASS" if risk_pass else "REJECT",
        liquidation_result="PASS" if liquidation_pass else "REJECT",
        adl_result="PASS" if adl_pass else "REJECT",
        leverage_decision=str(leverage_trace_extension.get("leverage_decision", "dynamic")),
        confidence_multiplier=float(leverage_trace_extension.get("confidence_multiplier", 1.0)),
        microstructure_multiplier=float(leverage_trace_extension.get("microstructure_multiplier", 1.0)),
        liquidation_multiplier=float(leverage_trace_extension.get("liquidation_multiplier", 1.0)),
        funding_multiplier=float(leverage_trace_extension.get("funding_multiplier", 1.0)),
        final_leverage=float(leverage_trace_extension.get("final_leverage", 1.0)),
        position_size_ratio=float(leverage_trace_extension.get("position_size_ratio", 1.0)),
        final_decision=decision,
        reason_code=reason_code,
        decision_layer=attribution["decision_layer"],
    )

    return {
        "decision": decision,
        "risk": risk,
        "gate": {
            "hard_gate_pass": hard_gate_pass,
            "microstructure_gate_pass": microstructure_pass,
            "liquidation_gate_pass": liquidation_pass,
            "policy_pass": policy_pass,
            "all_reasons": sorted(set(reasons)),
            "gate_reason": reason_code if decision == "REJECT" else "PASS",
            "risk_score": float(micro_gate.get("risk_score") or 0.0),
        },
        "liquidation_gate": gate,
        "adl_gate": adl_gate,
        "execution_suitability": execution_suitability,
        "leverage_decision": leverage_decision,
        "leverage_trace_extension": leverage_trace_extension,
        "decision_layer": attribution["decision_layer"],
        "decision_trace_model": decision_trace,
        "reason_code": reason_code,
        "reasons": sorted(set(reasons)),
        "trace": [*trace, "paper_execution" if decision == "ALLOW" else "decision_reject"],
    }
