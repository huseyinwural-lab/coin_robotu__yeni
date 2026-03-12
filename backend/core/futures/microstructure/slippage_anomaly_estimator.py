class SlippageAnomalyEstimator:
    def evaluate(self, snapshot: dict, spread_result: dict, vacuum_result: dict) -> dict:
        spread_bps = float(spread_result.get("spread_bps") or snapshot.get("spread_bps") or 0.0)
        shock_ratio = float(spread_result.get("shock_ratio") or 1.0)
        vacuum_score = float(vacuum_result.get("vacuum_score") or 0.0)

        expected_slippage_bps = spread_bps * (0.8 + shock_ratio * 0.4 + vacuum_score * 0.9)
        anomaly_score = min(1.0, expected_slippage_bps / 40)

        if anomaly_score >= 0.75:
            state = "ANOMALY"
        elif anomaly_score >= 0.45:
            state = "ELEVATED"
        else:
            state = "NORMAL"

        return {
            "expected_slippage_bps": round(expected_slippage_bps, 4),
            "slippage_state": state,
            "anomaly_score": round(anomaly_score, 4),
        }
