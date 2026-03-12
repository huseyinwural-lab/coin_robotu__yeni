def evaluate_funding_alignment(*, funding_rate: float, funding_bias_direction: str) -> dict:
    rate = float(funding_rate or 0.0)
    bias_direction = (funding_bias_direction or "NEUTRAL").upper()

    if rate >= 0.0012 or bias_direction == "LONG_BIAS":
        bias = "SHORT"
        confidence = min(0.9, 0.55 + abs(rate) * 180)
    elif rate <= -0.0012 or bias_direction == "SHORT_BIAS":
        bias = "LONG"
        confidence = min(0.9, 0.55 + abs(rate) * 180)
    else:
        bias = "NEUTRAL"
        confidence = 0.4

    return {
        "funding_alignment_bias": bias,
        "funding_alignment_confidence": round(confidence, 4),
    }
