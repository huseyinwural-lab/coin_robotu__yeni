def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _symbol_label(symbol: str) -> str:
    value = str(symbol or "").upper()
    return value[:-4] if value.endswith("USDT") else value


def calculate_cluster_exposure(
    *,
    clusters: list[dict],
    positions: list[dict],
    portfolio_equity: float,
) -> dict:
    equity = max(_safe_float(portfolio_equity), 1.0)
    output: list[dict] = []

    for cluster in clusters:
        cluster_symbols = set(cluster.get("symbols") or [])
        cluster_positions = [
            position
            for position in positions
            if _symbol_label(position.get("symbol")) in cluster_symbols
        ]

        notional_sum = sum(abs(_safe_float(item.get("position_notional"))) for item in cluster_positions)
        long_notional = sum(abs(_safe_float(item.get("position_notional"))) for item in cluster_positions if str(item.get("side") or "").upper() == "LONG")
        short_notional = sum(abs(_safe_float(item.get("position_notional"))) for item in cluster_positions if str(item.get("side") or "").upper() == "SHORT")

        direction = "NEUTRAL"
        if long_notional > short_notional:
            direction = "LONG"
        elif short_notional > long_notional:
            direction = "SHORT"
        elif long_notional > 0 and short_notional > 0:
            direction = "MIXED"

        leverage_sum = sum(_safe_float(item.get("leverage"), 1.0) * abs(_safe_float(item.get("position_notional"))) for item in cluster_positions)
        avg_leverage = (leverage_sum / notional_sum) if notional_sum > 0 else 0.0

        output.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "symbols": cluster.get("symbols") or [],
                "cluster_exposure": round(notional_sum / equity, 6),
                "cluster_exposure_notional": round(notional_sum, 4),
                "cluster_direction": direction,
                "cluster_leverage": round(avg_leverage, 4),
                "cluster_position_count": len(cluster_positions),
                "positions": cluster_positions,
            }
        )

    return {
        "portfolio_equity": round(equity, 4),
        "cluster_exposures": output,
    }
