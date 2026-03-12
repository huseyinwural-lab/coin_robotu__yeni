def track_strategy_exposure(decisions: list[dict]) -> dict:
    symbol_exposure: dict[str, float] = {}
    strategy_exposure: dict[str, float] = {}
    cluster_exposure: dict[str, float] = {}

    def _cluster(symbol: str) -> str:
        s = symbol.upper()
        if any(token in s for token in ["BTC", "ETH", "SOL"]):
            return "MAJOR_CLUSTER"
        return "ALT_CLUSTER"

    for row in decisions:
        if row.get("decision") != "ALLOW":
            continue
        symbol = str(row.get("symbol") or "UNKNOWN").upper()
        strategy = str(row.get("strategy") or row.get("strategy_id") or "unknown")
        leverage = float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        size_ratio = float((row.get("leverage_decision") or {}).get("position_size_ratio") or 1.0)
        exposure = leverage * size_ratio

        symbol_exposure[symbol] = round(symbol_exposure.get(symbol, 0.0) + exposure, 4)
        strategy_exposure[strategy] = round(strategy_exposure.get(strategy, 0.0) + exposure, 4)
        cluster_key = _cluster(symbol)
        cluster_exposure[cluster_key] = round(cluster_exposure.get(cluster_key, 0.0) + exposure, 4)

    return {
        "symbol_exposure": symbol_exposure,
        "strategy_exposure": strategy_exposure,
        "cluster_exposure": cluster_exposure,
    }
