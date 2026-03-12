class LiquidationScaler:
    def evaluate(self, distance_to_liquidation: float) -> dict:
        distance = float(distance_to_liquidation or 0.0)
        if distance < 8:
            leverage_multiplier = 0.45
            size_clamp = 0.35
        elif distance < 12:
            leverage_multiplier = 0.65
            size_clamp = 0.6
        elif distance < 18:
            leverage_multiplier = 0.85
            size_clamp = 0.8
        else:
            leverage_multiplier = 1.0
            size_clamp = 1.0

        return {
            "distance_to_liquidation": round(distance, 4),
            "liquidation_adjustment": round(leverage_multiplier, 4),
            "liquidation_size_clamp_ratio": round(size_clamp, 4),
        }
