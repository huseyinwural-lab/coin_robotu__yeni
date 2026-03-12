class ADLGate:
    def evaluate(
        self,
        *,
        adl_risk_level: str,
        adl_pressure_side: str,
        portfolio_adl_risk: float,
        trade_side: str,
        portfolio_threshold: float = 0.65,
    ) -> dict:
        level = str(adl_risk_level or "LOW").upper()
        pressure_side = str(adl_pressure_side or "NONE").upper()
        side = str(trade_side or "NONE").upper()

        reasons: list[str] = []
        if level == "EXTREME":
            reasons.append("ADL_RISK_EXTREME")
        if float(portfolio_adl_risk) > portfolio_threshold:
            reasons.append("ADL_PORTFOLIO_RISK_HIGH")
        if pressure_side in {"LONG", "SHORT"} and pressure_side == side and level in {"HIGH", "EXTREME"}:
            reasons.append(f"ADL_PRESSURE_{pressure_side}")

        return {
            "adl_gate_pass": len(reasons) == 0,
            "reason": reasons[0] if reasons else "PASS",
            "all_reasons": reasons,
        }
