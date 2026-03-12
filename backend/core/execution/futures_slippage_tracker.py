class FuturesSlippageTracker:
    def evaluate(
        self,
        *,
        symbol: str,
        order_type: str,
        expected_price: float,
        realized_price: float,
    ) -> dict:
        expected = float(expected_price or 0.0)
        realized = float(realized_price or 0.0)
        if expected <= 0:
            slippage_bps = 0.0
        else:
            slippage_bps = ((realized - expected) / expected) * 10_000
        delta = realized - expected
        return {
            "symbol": symbol,
            "order_type": str(order_type or "MARKET").upper(),
            "expected_slippage": round(abs(slippage_bps), 4),
            "realized_slippage": round(slippage_bps, 4),
            "slippage_delta": round(delta, 8),
        }
