def build_scaling_governance_actions(robustness_payload: dict) -> dict:
    score = float(robustness_payload.get("scaling_robustness_score") or 0.0)
    state = str(robustness_payload.get("robustness_state") or "unstable")

    capital_cap_recommendation = 1.0
    risk_downshift = False
    strategy_disable = False

    if state == "caution":
        capital_cap_recommendation = 0.8
        risk_downshift = True
    elif state == "unstable":
        capital_cap_recommendation = 0.55
        risk_downshift = True
        strategy_disable = score < 45

    return {
        "capital_cap_recommendation": capital_cap_recommendation,
        "risk_downshift": risk_downshift,
        "strategy_disable": strategy_disable,
    }
