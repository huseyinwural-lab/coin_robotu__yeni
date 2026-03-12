from core.strategies.legacy.config import VolatilityContractionPrefilterConfig


class VolatilityContractionPrefilter:
    prefilter_type = "volatility_contraction_prefilter"

    def __init__(self, config: VolatilityContractionPrefilterConfig | None = None):
        self.config = config or VolatilityContractionPrefilterConfig()

    def evaluate(self, market_state: dict) -> dict:
        symbol = str(market_state.get("symbol", "")).upper()
        relative_range = float(market_state.get("relative_range", 0.0))
        relative_volume = float(market_state.get("relative_volume", 0.0))
        compression = float(market_state.get("volatility_compression", 0.0))

        is_contracted = (
            relative_range <= self.config.max_relative_range
            and relative_volume <= self.config.max_relative_volume
            and compression >= self.config.min_compression_score
        )
        breakout_potential = max(0.0, min(1.0, compression * (1 - relative_range / max(self.config.max_relative_range, 1e-6))))

        return {
            "symbol": symbol,
            "is_contracted": is_contracted,
            "relative_range": round(relative_range, 6),
            "relative_volume": round(relative_volume, 6),
            "compression_score": round(compression, 6),
            "breakout_potential": round(breakout_potential, 6),
        }

    def scan(self, market_states: list[dict]) -> dict:
        rows = [self.evaluate(state) for state in market_states]
        selected = [row for row in rows if row["is_contracted"]]
        return {
            "prefilter": self.prefilter_type,
            "selected_symbols": [row["symbol"] for row in selected],
            "rows": rows,
        }
