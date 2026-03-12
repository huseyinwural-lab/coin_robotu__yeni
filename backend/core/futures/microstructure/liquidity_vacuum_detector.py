class LiquidityVacuumDetector:
    def evaluate(self, snapshot: dict, thinning_result: dict) -> dict:
        top_of_book_size = float(snapshot.get("top_of_book_size") or 0.0)
        depth_imbalance = abs(float(snapshot.get("depth_imbalance") or 0.0))
        liquidity_gap_score = float(snapshot.get("liquidity_gap_score") or 0.0)
        thinning_state = str(thinning_result.get("thinning_state") or "NORMAL").upper()

        top_book_component = min(1.0, 1 / max(top_of_book_size, 0.25))
        imbalance_component = min(1.0, depth_imbalance / 0.6)
        gap_component = min(1.0, liquidity_gap_score / 60)
        thinning_component = {
            "NORMAL": 0.1,
            "WARNING": 0.5,
            "CRITICAL": 0.95,
        }.get(thinning_state, 0.1)

        vacuum_score = min(
            1.0,
            top_book_component * 0.35 + imbalance_component * 0.2 + gap_component * 0.3 + thinning_component * 0.15,
        )
        expected_slippage_risk = min(100.0, vacuum_score * 100)

        if vacuum_score >= 0.75:
            vacuum_state = "HIGH"
        elif vacuum_score >= 0.45:
            vacuum_state = "MEDIUM"
        else:
            vacuum_state = "LOW"

        return {
            "vacuum_score": round(vacuum_score, 4),
            "vacuum_state": vacuum_state,
            "expected_slippage_risk": round(expected_slippage_risk, 4),
        }
