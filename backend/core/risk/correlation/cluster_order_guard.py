from datetime import datetime, timezone


def _symbol_label(symbol: str) -> str:
    value = str(symbol or "").upper()
    return value[:-4] if value.endswith("USDT") else value


def evaluate_cluster_order_guard(
    *,
    order: dict,
    clusters: list[dict],
    cluster_exposures: list[dict],
    portfolio_equity: float,
    cluster_exposure_limit: float,
) -> dict:
    symbol = _symbol_label(order.get("symbol"))
    side = str(order.get("side") or "NONE").upper()
    order_notional = abs(float(order.get("position_notional") or 0.0))
    if order_notional <= 0:
        return {
            "action": "ALLOW",
            "reason": [],
            "adjusted_position_size_ratio": float(order.get("position_size_ratio") or 1.0),
            "event": None,
        }

    target_cluster = next((item for item in clusters if symbol in set(item.get("symbols") or [])), None)
    if not target_cluster:
        return {
            "action": "ALLOW",
            "reason": [],
            "adjusted_position_size_ratio": float(order.get("position_size_ratio") or 1.0),
            "event": None,
        }

    cluster_id = target_cluster.get("cluster_id")
    current = next((item for item in cluster_exposures if item.get("cluster_id") == cluster_id), None) or {}
    equity = max(float(portfolio_equity or 0.0), 1.0)
    current_notional = float(current.get("cluster_exposure_notional") or 0.0)
    projected_notional = current_notional + order_notional
    projected_exposure = projected_notional / equity

    if projected_exposure > cluster_exposure_limit:
        event = {
            "cluster_id": cluster_id,
            "event": "CLUSTER_TRADE_REJECTED",
            "symbols": target_cluster.get("symbols") or [],
            "exposure": round(projected_exposure, 6),
            "direction": side,
            "reason": ["CLUSTER_EXPOSURE_LIMIT"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "action": "REJECT",
            "reason": ["CLUSTER_EXPOSURE_LIMIT"],
            "adjusted_position_size_ratio": 0.0,
            "event": event,
        }

    near_limit = projected_exposure > cluster_exposure_limit * 0.9
    if near_limit:
        ratio = float(order.get("position_size_ratio") or 1.0)
        reduced_ratio = max(0.2, round(ratio * 0.65, 4))
        return {
            "action": "REDUCE_SIZE",
            "reason": ["CLUSTER_EXPOSURE_NEAR_LIMIT"],
            "adjusted_position_size_ratio": reduced_ratio,
            "event": None,
        }

    return {
        "action": "ALLOW",
        "reason": [],
        "adjusted_position_size_ratio": float(order.get("position_size_ratio") or 1.0),
        "event": None,
    }
