class MicrostructureGate:
    def evaluate(
        self,
        *,
        spread_result: dict,
        thinning_result: dict,
        vacuum_result: dict,
        quote_result: dict,
        slippage_result: dict,
        aggregate_result: dict,
        stale_data: bool,
    ) -> dict:
        reasons: list[str] = []

        if stale_data:
            reasons.append("MICROSTRUCTURE_STALE_DATA")
        if str(spread_result.get("spread_state") or "NORMAL").upper() == "SHOCK":
            reasons.append("MICROSTRUCTURE_SPREAD_SHOCK")
        if str(thinning_result.get("thinning_state") or "NORMAL").upper() == "CRITICAL":
            reasons.append("MICROSTRUCTURE_DEPTH_COLLAPSE")
        if str(vacuum_result.get("vacuum_state") or "LOW").upper() == "HIGH":
            reasons.append("MICROSTRUCTURE_LIQUIDITY_VACUUM_HIGH")
        if str(quote_result.get("quote_stability_state") or "STABLE").upper() == "CHAOTIC":
            reasons.append("MICROSTRUCTURE_QUOTE_CHAOTIC")
        if str(slippage_result.get("slippage_state") or "NORMAL").upper() == "ANOMALY":
            reasons.append("MICROSTRUCTURE_SLIPPAGE_ANOMALY")
        if str(aggregate_result.get("risk_level") or "SAFE").upper() == "BLOCKED":
            reasons.append("MICROSTRUCTURE_RISK_BLOCKED")

        return {
            "gate_pass": len(reasons) == 0,
            "gate_reason": reasons[0] if reasons else "PASS",
            "all_reasons": reasons,
            "risk_score": float(aggregate_result.get("microstructure_risk_score") or 0.0),
        }
