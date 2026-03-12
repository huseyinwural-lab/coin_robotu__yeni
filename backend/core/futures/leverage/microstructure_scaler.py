class MicrostructureScaler:
    def evaluate(
        self,
        *,
        microstructure_risk_score: float,
        execution_suitability: dict,
        spread_state: str,
        depth_state: str,
    ) -> dict:
        risk_score = max(0.0, min(1.0, float(microstructure_risk_score or 0.0)))
        spread_state = (spread_state or "NORMAL").upper()
        depth_state = (depth_state or "NORMAL").upper()
        suitability = execution_suitability or {}

        state_multiplier = {
            "BLOCKED": 0.2,
            "HIGH": 0.55,
            "MEDIUM": 0.8,
            "LOW": 1.0,
        }.get(str(suitability.get("severity") or "LOW").upper(), 1.0)

        spread_multiplier = {
            "SHOCK": 0.5,
            "ELEVATED": 0.8,
            "NORMAL": 1.0,
        }.get(spread_state, 1.0)
        depth_multiplier = {
            "CRITICAL": 0.55,
            "WARNING": 0.8,
            "NORMAL": 1.0,
        }.get(depth_state, 1.0)

        liquidity_adjusted_leverage = max(0.2, state_multiplier * spread_multiplier * depth_multiplier * (1 - risk_score * 0.35))
        size_clamp_ratio = float(suitability.get("max_allowed_size_ratio") or 1.0)
        size_clamp_ratio = max(0.0, min(size_clamp_ratio, 1.0))
        if spread_state == "SHOCK":
            size_clamp_ratio = min(size_clamp_ratio, 0.35)
        if depth_state == "CRITICAL":
            size_clamp_ratio = min(size_clamp_ratio, 0.4)

        return {
            "liquidity_adjusted_leverage": round(liquidity_adjusted_leverage, 4),
            "size_clamp_ratio": round(size_clamp_ratio, 4),
        }
