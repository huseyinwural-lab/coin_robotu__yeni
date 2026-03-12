def futures_capital_recommendation(*, total_equity: float, futures_notional: float) -> dict:
    recommended_spot_ratio = 0.70
    recommended_futures_ratio = 0.30
    current_futures_ratio = (futures_notional / total_equity) if total_equity > 0 else 0.0
    deviation = current_futures_ratio - recommended_futures_ratio
    return {
        "recommended": {
            "spot_capital_ratio": recommended_spot_ratio,
            "futures_capital_ratio": recommended_futures_ratio,
        },
        "current": {
            "futures_capital_ratio": round(current_futures_ratio, 4),
            "spot_capital_ratio": round(max(1 - current_futures_ratio, 0.0), 4),
        },
        "deviation": round(deviation, 4),
    }
