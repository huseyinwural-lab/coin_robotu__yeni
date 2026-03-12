from dataclasses import asdict, dataclass


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class ADLRiskResult:
    adl_risk_score: float
    adl_risk_level: str
    adl_pressure_side: str


class ADLRiskDetector:
    def evaluate_symbol(self, market_data: dict) -> ADLRiskResult:
        exchange_adl_indicator = _clamp(float(market_data.get("exchange_adl_indicator") or 0.0))
        funding_rate = float(market_data.get("funding_rate") or 0.0)
        funding_skew = float(market_data.get("funding_skew") or 0.0)
        open_interest_change = float(market_data.get("open_interest_change") or 0.0)
        long_short_ratio = float(market_data.get("long_short_ratio") or 1.0)
        liquidation_volume = float(market_data.get("liquidation_volume") or 0.0)
        volatility_regime = str(market_data.get("volatility_regime") or "NORMAL").upper()

        funding_component = _clamp(abs(funding_rate) * 100)
        skew_component = _clamp(abs(funding_skew) * 20)
        open_interest_component = _clamp(abs(open_interest_change) / 8)
        lsr_component = _clamp(abs(long_short_ratio - 1.0) / 0.8)
        liquidation_component = _clamp(liquidation_volume / 25_000_000)
        volatility_component = {
            "LOW": 0.15,
            "NORMAL": 0.35,
            "HIGH": 0.7,
            "EXTREME": 0.95,
        }.get(volatility_regime, 0.35)

        score = _clamp(
            exchange_adl_indicator * 0.33
            + funding_component * 0.12
            + skew_component * 0.1
            + open_interest_component * 0.15
            + lsr_component * 0.1
            + liquidation_component * 0.1
            + volatility_component * 0.1
        )

        if score >= 0.75:
            risk_level = "EXTREME"
        elif score >= 0.55:
            risk_level = "HIGH"
        elif score >= 0.3:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        pressure_side = "NONE"
        if long_short_ratio >= 1.08 or funding_skew >= 0.02:
            pressure_side = "LONG"
        elif long_short_ratio <= 0.92 or funding_skew <= -0.02:
            pressure_side = "SHORT"

        return ADLRiskResult(
            adl_risk_score=round(score, 4),
            adl_risk_level=risk_level,
            adl_pressure_side=pressure_side,
        )


def evaluate_adl_symbol_risk(market_data: dict) -> dict:
    detector = ADLRiskDetector()
    return asdict(detector.evaluate_symbol(market_data))
