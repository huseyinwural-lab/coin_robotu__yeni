SCENARIO_MULTIPLIERS = {
    "high_volatility": {"volatility_multiplier": 1.6, "liquidity_multiplier": 0.75, "spread_multiplier": 1.4},
    "low_liquidity": {"volatility_multiplier": 1.2, "liquidity_multiplier": 0.55, "spread_multiplier": 1.6},
    "flash_crash": {"volatility_multiplier": 2.2, "liquidity_multiplier": 0.4, "spread_multiplier": 2.0},
    "liquidation_cascade": {"volatility_multiplier": 1.9, "liquidity_multiplier": 0.5, "spread_multiplier": 1.8},
}


def run_stress_replay(base_metrics: dict, scenario: str) -> dict:
    key = str(scenario or "high_volatility")
    multipliers = SCENARIO_MULTIPLIERS.get(key, SCENARIO_MULTIPLIERS["high_volatility"])
    return {
        "scenario": key,
        "volatility_multiplier": multipliers["volatility_multiplier"],
        "liquidity_multiplier": multipliers["liquidity_multiplier"],
        "spread_multiplier": multipliers["spread_multiplier"],
        "replayed_metrics": {
            "volatility": round(float(base_metrics.get("volatility") or 1.0) * multipliers["volatility_multiplier"], 6),
            "liquidity": round(float(base_metrics.get("liquidity") or 1.0) * multipliers["liquidity_multiplier"], 6),
            "spread_bps": round(float(base_metrics.get("spread_bps") or 1.0) * multipliers["spread_multiplier"], 6),
        },
    }
