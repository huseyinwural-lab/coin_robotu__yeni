from collections import defaultdict

from core.strategies.legacy.config import RelativeStrengthScannerConfig


class RelativeStrengthClusterScannerV2:
    prefilter_type = "relative_strength_cluster_scanner_v2"

    def __init__(self, config: RelativeStrengthScannerConfig | None = None):
        self.config = config or RelativeStrengthScannerConfig()

    def _benchmark_map(self, market_states: list[dict], benchmark_mode: str) -> tuple[str, dict[str, float]]:
        mode = str(benchmark_mode or "cluster").lower()
        if mode == "market":
            returns = [float(row.get("return_20", 0.0)) for row in market_states]
            market_mean = (sum(returns) / len(returns)) if returns else 0.0
            return "market", {str(row.get("symbol", "")).upper(): market_mean for row in market_states}

        resolved_mode = "cluster"

        cluster_returns: dict[str, list[float]] = defaultdict(list)
        for row in market_states:
            cluster_returns[str(row.get("cluster", "default"))].append(float(row.get("return_20", 0.0)))
        cluster_mean = {cluster: (sum(values) / len(values) if values else 0.0) for cluster, values in cluster_returns.items()}
        return (
            resolved_mode,
            {
                str(row.get("symbol", "")).upper(): cluster_mean.get(str(row.get("cluster", "default")), 0.0)
                for row in market_states
            },
        )

    def scan(self, market_states: list[dict], benchmark_mode: str = "cluster") -> dict:
        resolved_mode, benchmark = self._benchmark_map(market_states, benchmark_mode)
        candidates: list[dict] = []

        for row in market_states:
            symbol = str(row.get("symbol", "")).upper()
            liquidity = float(row.get("liquidity_usd", 0.0))
            spread_bps = float(row.get("spread_bps", 999.0))
            if liquidity < self.config.min_liquidity_usd or spread_bps > 40:
                continue

            asset_return = float(row.get("return_20", 0.0))
            benchmark_return = float(benchmark.get(symbol, 0.0))
            relative_strength = asset_return - benchmark_return
            if relative_strength < self.config.min_rs_edge:
                continue

            candidates.append(
                {
                    "symbol": symbol,
                    "cluster": str(row.get("cluster", "default")),
                    "relative_strength": round(relative_strength, 6),
                    "asset_return": round(asset_return, 6),
                    "benchmark_return": round(benchmark_return, 6),
                }
            )

        ranked = sorted(candidates, key=lambda item: item["relative_strength"], reverse=True)[: self.config.top_n]
        return {
            "prefilter": self.prefilter_type,
            "benchmark_mode": resolved_mode,
            "benchmark_mode_requested": benchmark_mode,
            "selected_symbols": [item["symbol"] for item in ranked],
            "candidates": ranked,
        }
