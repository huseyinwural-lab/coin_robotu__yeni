class MicrostructureRiskAggregator:
    def aggregate(
        self,
        *,
        snapshot: dict,
        spread_result: dict,
        thinning_result: dict,
        vacuum_result: dict,
        quote_result: dict,
        slippage_result: dict,
        disappearance_result: dict,
    ) -> dict:
        spread_score = {
            "NORMAL": 0.1,
            "ELEVATED": 0.55,
            "SHOCK": 1.0,
        }.get(str(spread_result.get("spread_state") or "NORMAL").upper(), 0.1)
        thinning_score = {
            "NORMAL": 0.1,
            "WARNING": 0.6,
            "CRITICAL": 1.0,
        }.get(str(thinning_result.get("thinning_state") or "NORMAL").upper(), 0.1)
        vacuum_score = float(vacuum_result.get("vacuum_score") or 0.0)
        quote_score = {
            "STABLE": 0.1,
            "UNSTABLE": 0.55,
            "CHAOTIC": 1.0,
        }.get(str(quote_result.get("quote_stability_state") or "STABLE").upper(), 0.1)
        slippage_score = float(slippage_result.get("anomaly_score") or 0.0)
        disappearance_score = float(disappearance_result.get("liquidity_disappearance_score") or 0.0)
        stale_penalty = 1.0 if bool(snapshot.get("stale_data", False)) else 0.0

        factor_scores = {
            "SPREAD_SHOCK": spread_score,
            "ORDERBOOK_THINNING": thinning_score,
            "LIQUIDITY_VACUUM": vacuum_score,
            "QUOTE_INSTABILITY": quote_score,
            "SLIPPAGE_ANOMALY": slippage_score,
            "LIQUIDITY_DISAPPEARANCE": disappearance_score,
            "STALE_DATA": stale_penalty,
        }
        risk_score = min(
            1.0,
            spread_score * 0.2
            + thinning_score * 0.2
            + vacuum_score * 0.15
            + quote_score * 0.15
            + slippage_score * 0.15
            + disappearance_score * 0.1
            + stale_penalty * 0.05,
        )

        if stale_penalty >= 1.0 or risk_score >= 0.85:
            level = "BLOCKED"
        elif risk_score >= 0.65:
            level = "CRITICAL"
        elif risk_score >= 0.4:
            level = "WARNING"
        else:
            level = "SAFE"

        side_risk = str(disappearance_result.get("affected_side") or "NONE").upper()
        return {
            "microstructure_risk_score": round(risk_score, 4),
            "risk_level": level,
            "dominant_factor": max(factor_scores, key=factor_scores.get),
            "side_risk": side_risk,
            "factor_scores": {key: round(value, 4) for key, value in factor_scores.items()},
        }
