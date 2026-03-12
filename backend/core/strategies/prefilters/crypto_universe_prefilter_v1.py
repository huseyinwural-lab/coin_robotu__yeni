from core.strategies.legacy.config import CryptoUniversePrefilterConfig


class CryptoUniversePrefilterV1:
    prefilter_type = "crypto_universe_prefilter_v1"

    def __init__(self, config: CryptoUniversePrefilterConfig | None = None):
        self.config = config or CryptoUniversePrefilterConfig()

    def filter_universe(self, market_rows: list[dict]) -> dict:
        selected: list[str] = []
        details: list[dict] = []
        rejected: list[dict] = []

        for row in market_rows:
            symbol = str(row.get("symbol", "")).upper()
            liquidity = float(row.get("liquidity_usd", 0.0))
            spread_bps = float(row.get("spread_bps", 999.0))
            volume_stability = float(row.get("volume_stability", 0.0))
            volatility = float(row.get("volatility", 0.0))
            futures_tradable = bool(row.get("futures_tradable", False))

            reasons: list[str] = []
            if liquidity < self.config.min_liquidity_usd:
                reasons.append("MIN_LIQUIDITY")
            if spread_bps > self.config.max_spread_bps:
                reasons.append("MAX_SPREAD")
            if volume_stability < self.config.min_volume_stability:
                reasons.append("VOLUME_STABILITY")
            if volatility < self.config.min_volatility or volatility > self.config.max_volatility:
                reasons.append("VOLATILITY_SUITABILITY")
            if not futures_tradable:
                reasons.append("FUTURES_TRADABILITY")

            diagnostics = {
                "symbol": symbol,
                "liquidity_usd": round(liquidity, 4),
                "spread_bps": round(spread_bps, 4),
                "volume_stability": round(volume_stability, 6),
                "volatility": round(volatility, 6),
                "futures_tradable": futures_tradable,
            }
            if reasons:
                rejected.append({**diagnostics, "reasons": reasons})
                continue

            selected.append(symbol)
            details.append({**diagnostics, "score": round(volume_stability + liquidity / max(self.config.min_liquidity_usd, 1.0), 6)})

        return {
            "prefilter": self.prefilter_type,
            "selected_symbols": sorted(set(selected)),
            "selected_details": details,
            "rejected": rejected,
            "filters": {
                "minimum_liquidity": self.config.min_liquidity_usd,
                "maximum_spread": self.config.max_spread_bps,
                "minimum_volume_stability": self.config.min_volume_stability,
                "volatility_band": [self.config.min_volatility, self.config.max_volatility],
                "futures_tradability": True,
            },
        }
