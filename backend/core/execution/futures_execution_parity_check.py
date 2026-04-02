class FuturesExecutionParityCheck:
    def evaluate(self, *, paper_fill_price: float, live_fill_price: float, tolerance_bps: float = 20.0) -> dict:
        paper = float(paper_fill_price or 0.0)
        live = float(live_fill_price or 0.0)
        if paper <= 0:
            drift_bps = 0.0
        else:
            drift_bps = abs((live - paper) / paper) * 10_000

        status = "PASS" if drift_bps <= tolerance_bps else "WARN"
        return {
            "paper_fill_price": round(paper, 8),
            "live_fill_price": round(live, 8),
            "drift_bps": round(drift_bps, 4),
            "tolerance_bps": round(float(tolerance_bps), 4),
            "status": status,
        }
