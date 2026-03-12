class SpreadShockDetector:
    def evaluate(self, snapshot: dict, baseline_spread_bps: float | None = None) -> dict:
        spread_bps = float(snapshot.get("spread_bps") or 0.0)
        baseline = float(baseline_spread_bps or snapshot.get("baseline_spread_bps") or 8.0)
        baseline = max(baseline, 0.1)
        shock_ratio = spread_bps / baseline

        if shock_ratio >= 2.5:
            state = "SHOCK"
        elif shock_ratio >= 1.5:
            state = "ELEVATED"
        else:
            state = "NORMAL"

        return {
            "spread_state": state,
            "spread_bps": round(spread_bps, 4),
            "baseline_spread_bps": round(baseline, 4),
            "shock_ratio": round(shock_ratio, 4),
        }
