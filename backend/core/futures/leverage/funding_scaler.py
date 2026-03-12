class FundingScaler:
    def evaluate(self, *, side: str, funding_bias: dict) -> dict:
        direction = str((funding_bias or {}).get("bias_direction") or "NEUTRAL").upper()
        pressure = str((funding_bias or {}).get("funding_pressure_state") or "LOW").upper()
        trade_side = str(side or "NONE").upper()

        multiplier = 1.0
        if trade_side == "LONG":
            if direction == "LONG_BIAS" and pressure in {"MEDIUM", "HIGH"}:
                multiplier = 0.85 if pressure == "MEDIUM" else 0.7
            elif direction == "SHORT_BIAS":
                multiplier = 1.08
        elif trade_side == "SHORT":
            if direction == "SHORT_BIAS" and pressure in {"MEDIUM", "HIGH"}:
                multiplier = 0.85 if pressure == "MEDIUM" else 0.7
            elif direction == "LONG_BIAS":
                multiplier = 1.08

        return {
            "funding_adjustment_factor": round(multiplier, 4),
            "funding_direction": direction,
            "funding_pressure": pressure,
        }
