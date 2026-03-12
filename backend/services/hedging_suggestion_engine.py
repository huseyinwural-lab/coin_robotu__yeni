def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def detect_hedge_opportunity(
    *,
    portfolio_exposure: dict,
    cluster_risk: dict,
    market_correlation: dict,
    volatility: float,
) -> dict:
    total_notional = _safe_float(portfolio_exposure.get("total_notional"), 0)
    cluster_exposure = portfolio_exposure.get("cluster_exposure") or {}

    if total_notional <= 0 or not cluster_exposure:
        return {
            "hedge_symbol": None,
            "hedge_size": 0.0,
            "hedge_direction": None,
            "risk_reduction_score": 0.0,
            "correlation_basis": "insufficient_exposure",
            "recommended_action": "no_hedge_needed",
        }

    dominant_cluster, dominant_notional = max(cluster_exposure.items(), key=lambda item: _safe_float(item[1], 0))
    dominant_ratio = _safe_float(dominant_notional, 0) / max(total_notional, 1)
    cluster_risk_score = _safe_float(cluster_risk.get(dominant_cluster), dominant_ratio)
    volatility_factor = max(_safe_float(volatility, 0) / 10, 0)

    if dominant_ratio < 0.2 and cluster_risk_score < 0.35:
        return {
            "hedge_symbol": None,
            "hedge_size": 0.0,
            "hedge_direction": None,
            "risk_reduction_score": round(min(1.0, dominant_ratio), 4),
            "correlation_basis": "cluster_concentration_below_threshold",
            "recommended_action": "no_hedge_needed",
        }

    hedge_symbol_map = {
        "L1": "BTCUSDT",
        "L2": "ETHUSDT",
        "UNCLUSTERED": "BTCUSDT",
    }
    hedge_symbol = hedge_symbol_map.get(str(dominant_cluster), "BTCUSDT")

    corr = _safe_float(market_correlation.get(dominant_cluster), 0.72)
    hedge_size = round(max(total_notional * dominant_ratio * 0.25 * max(corr, 0.25), 0), 4)
    hedge_direction = "sell"
    risk_reduction_score = round(min(1.0, (dominant_ratio * 0.6) + (cluster_risk_score * 0.25) + (volatility_factor * 0.15)), 4)

    correlation_basis = f"cluster={dominant_cluster}; corr={round(corr, 4)}; vol={round(_safe_float(volatility, 0), 4)}"
    recommended_action = "open_hedge" if hedge_size > 0 else "monitor"
    return {
        "hedge_symbol": hedge_symbol,
        "hedge_size": hedge_size,
        "hedge_direction": hedge_direction,
        "risk_reduction_score": risk_reduction_score,
        "correlation_basis": correlation_basis,
        "recommended_action": recommended_action,
        "dominant_cluster": dominant_cluster,
    }
