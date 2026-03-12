class LiquidityDisappearanceHeuristic:
    def evaluate(self, snapshot: dict, thinning_result: dict, quote_result: dict) -> dict:
        liquidity_gap_score = float(snapshot.get("liquidity_gap_score") or 0.0)
        quote_update_rate = float(quote_result.get("quote_update_rate") or snapshot.get("quote_update_rate") or 0.0)
        thinning_state = str(thinning_result.get("thinning_state") or "NORMAL").upper()
        dominant_side = str(thinning_result.get("dominant_thin_side") or "NONE").upper()

        thinning_component = {"NORMAL": 0.1, "WARNING": 0.6, "CRITICAL": 0.95}.get(thinning_state, 0.1)
        quote_component = min(1.0, abs(quote_update_rate - 4) / 8)
        gap_component = min(1.0, liquidity_gap_score / 70)

        score = min(1.0, thinning_component * 0.5 + quote_component * 0.25 + gap_component * 0.25)
        if score >= 0.75:
            state = "STRONG"
        elif score >= 0.45:
            state = "SUSPECTED"
        else:
            state = "NONE"

        affected_side = "NONE"
        if dominant_side == "BID":
            affected_side = "LONG"
        elif dominant_side == "ASK":
            affected_side = "SHORT"

        return {
            "liquidity_disappearance_score": round(score, 4),
            "heuristic_state": state,
            "affected_side": affected_side,
        }
