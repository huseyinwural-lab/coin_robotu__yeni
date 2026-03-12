class QuoteStabilityDetector:
    def evaluate(self, snapshot: dict) -> dict:
        quote_update_rate = float(snapshot.get("quote_update_rate") or 0.0)
        price_jump_score = float(snapshot.get("price_jump_score") or 0.0)
        spread_bps = float(snapshot.get("spread_bps") or 0.0)

        flicker_score = min(100.0, price_jump_score * 0.7 + spread_bps * 0.8 + max(quote_update_rate - 8, 0) * 3)

        if quote_update_rate > 10 or flicker_score >= 75:
            state = "CHAOTIC"
        elif quote_update_rate > 5 or flicker_score >= 40:
            state = "UNSTABLE"
        else:
            state = "STABLE"

        return {
            "quote_stability_state": state,
            "quote_update_rate": round(quote_update_rate, 4),
            "mid_price_flicker_score": round(flicker_score, 4),
        }
