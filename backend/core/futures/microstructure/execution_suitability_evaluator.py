class ExecutionSuitabilityEvaluator:
    def evaluate(self, aggregate_result: dict, gate_result: dict) -> dict:
        risk_level = str(aggregate_result.get("risk_level") or "SAFE").upper()
        side_risk = str(aggregate_result.get("side_risk") or "NONE").upper()
        risk_score = float(aggregate_result.get("microstructure_risk_score") or 0.0)
        gate_pass = bool(gate_result.get("gate_pass", False))

        if not gate_pass or risk_level == "BLOCKED":
            return {
                "execution_suitable": False,
                "severity": "BLOCKED",
                "max_allowed_size_ratio": 0.0,
                "leverage_cap_override": 1,
                "side_risk": side_risk,
            }
        if risk_level == "CRITICAL":
            return {
                "execution_suitable": True,
                "severity": "HIGH",
                "max_allowed_size_ratio": 0.35,
                "leverage_cap_override": 2,
                "side_risk": side_risk,
            }
        if risk_level == "WARNING":
            return {
                "execution_suitable": True,
                "severity": "MEDIUM",
                "max_allowed_size_ratio": 0.65,
                "leverage_cap_override": 3,
                "side_risk": side_risk,
            }
        size_ratio = max(0.7, 1 - risk_score * 0.3)
        return {
            "execution_suitable": True,
            "severity": "LOW",
            "max_allowed_size_ratio": round(size_ratio, 4),
            "leverage_cap_override": 5,
            "side_risk": side_risk,
        }
