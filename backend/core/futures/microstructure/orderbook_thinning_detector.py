class OrderbookThinningDetector:
    def evaluate(self, snapshot: dict, baseline_depth: dict | None = None) -> dict:
        baseline_depth = baseline_depth or {}
        bid_depth = float(snapshot.get("bid_depth_top_n") or 0.0)
        ask_depth = float(snapshot.get("ask_depth_top_n") or 0.0)

        baseline_bid = float(baseline_depth.get("bid_depth_top_n") or bid_depth or 1.0)
        baseline_ask = float(baseline_depth.get("ask_depth_top_n") or ask_depth or 1.0)
        baseline_bid = max(baseline_bid, 0.0001)
        baseline_ask = max(baseline_ask, 0.0001)

        bid_depth_change = (bid_depth - baseline_bid) / baseline_bid
        ask_depth_change = (ask_depth - baseline_ask) / baseline_ask
        worst_drop = min(bid_depth_change, ask_depth_change)

        if worst_drop <= -0.6:
            state = "CRITICAL"
        elif worst_drop <= -0.35:
            state = "WARNING"
        else:
            state = "NORMAL"

        dominant_side = "NONE"
        if bid_depth_change < ask_depth_change:
            dominant_side = "BID"
        elif ask_depth_change < bid_depth_change:
            dominant_side = "ASK"

        return {
            "thinning_state": state,
            "bid_depth_change": round(bid_depth_change, 4),
            "ask_depth_change": round(ask_depth_change, 4),
            "dominant_thin_side": dominant_side,
        }
