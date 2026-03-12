class StrategyExposureTracker:
    def __init__(
        self,
        *,
        max_symbol_exposure: float = 6.0,
        max_strategy_exposure: float = 8.0,
        max_cluster_exposure: float = 12.0,
    ):
        self.max_symbol_exposure = float(max_symbol_exposure)
        self.max_strategy_exposure = float(max_strategy_exposure)
        self.max_cluster_exposure = float(max_cluster_exposure)

    @staticmethod
    def _cluster(symbol: str) -> str:
        s = symbol.upper()
        if any(token in s for token in ["BTC", "ETH", "SOL", "BNB"]):
            return "MAJOR_CLUSTER"
        if any(token in s for token in ["AVAX", "LINK", "ADA", "XRP", "DOGE"]):
            return "HIGH_BETA_CLUSTER"
        return "ALT_CLUSTER"

    @staticmethod
    def _exposure_size(row: dict) -> float:
        leverage = float((row.get("leverage_decision") or {}).get("final_leverage") or 1.0)
        size_ratio = float((row.get("leverage_decision") or {}).get("position_size_ratio") or 1.0)
        confidence = float(row.get("confidence") or 0.0)
        weighted = leverage * max(0.05, min(1.0, size_ratio)) * (0.55 + confidence * 0.45)
        return max(0.05, round(weighted, 6))

    def compute(self, decisions: list[dict]) -> dict:
        symbol_exposure: dict[str, float] = {}
        strategy_exposure: dict[str, float] = {}
        cluster_exposure: dict[str, float] = {}

        for row in decisions:
            if row.get("decision") != "ALLOW":
                continue
            symbol = str(row.get("symbol") or "UNKNOWN").upper()
            strategy = str(row.get("strategy") or row.get("strategy_id") or "unknown")
            cluster_key = self._cluster(symbol)
            exposure = self._exposure_size(row)

            symbol_exposure[symbol] = round(symbol_exposure.get(symbol, 0.0) + exposure, 4)
            strategy_exposure[strategy] = round(strategy_exposure.get(strategy, 0.0) + exposure, 4)
            cluster_exposure[cluster_key] = round(cluster_exposure.get(cluster_key, 0.0) + exposure, 4)

        return {
            "symbol_exposure": symbol_exposure,
            "strategy_exposure": strategy_exposure,
            "cluster_exposure": cluster_exposure,
            "exposure_limits": {
                "max_symbol_exposure": round(self.max_symbol_exposure, 4),
                "max_strategy_exposure": round(self.max_strategy_exposure, 4),
                "max_cluster_exposure": round(self.max_cluster_exposure, 4),
            },
        }

    def apply(self, decisions: list[dict]) -> tuple[list[dict], list[dict], dict]:
        ranked = sorted(
            [
                (index, row)
                for index, row in enumerate(decisions)
                if row.get("decision") == "ALLOW"
            ],
            key=lambda item: float(item[1].get("confidence") or 0.0),
            reverse=True,
        )

        accepted_indexes: set[int] = set()
        blocked_by_index: dict[int, dict] = {}
        symbol_exposure: dict[str, float] = {}
        strategy_exposure: dict[str, float] = {}
        cluster_exposure: dict[str, float] = {}

        for index, row in ranked:
            symbol = str(row.get("symbol") or "UNKNOWN").upper()
            strategy = str(row.get("strategy") or row.get("strategy_id") or "unknown")
            cluster = self._cluster(symbol)
            delta = self._exposure_size(row)

            next_symbol = symbol_exposure.get(symbol, 0.0) + delta
            next_strategy = strategy_exposure.get(strategy, 0.0) + delta
            next_cluster = cluster_exposure.get(cluster, 0.0) + delta

            exceeds = (
                next_symbol > self.max_symbol_exposure
                or next_strategy > self.max_strategy_exposure
                or next_cluster > self.max_cluster_exposure
            )
            if exceeds:
                blocked_by_index[index] = {
                    **row,
                    "decision": "REJECT",
                    "reason_code": "GATE_REJECT",
                    "decision_layer": "PORTFOLIO",
                    "reasons": sorted(set((row.get("reasons") or []) + ["STRATEGY_EXPOSURE_LIMIT"])),
                }
                continue

            accepted_indexes.add(index)
            symbol_exposure[symbol] = round(next_symbol, 6)
            strategy_exposure[strategy] = round(next_strategy, 6)
            cluster_exposure[cluster] = round(next_cluster, 6)

        output: list[dict] = []
        blocked: list[dict] = []
        for index, row in enumerate(decisions):
            if index in blocked_by_index:
                blocked_row = blocked_by_index[index]
                output.append(blocked_row)
                blocked.append(blocked_row)
                continue
            output.append(row)

        exposure_snapshot = self.compute([output[idx] for idx in range(len(output)) if output[idx].get("decision") == "ALLOW"])
        exposure_snapshot["blocked_total"] = len(blocked)
        return output, blocked, exposure_snapshot


def track_strategy_exposure(decisions: list[dict]) -> dict:
    return StrategyExposureTracker().compute(decisions)
