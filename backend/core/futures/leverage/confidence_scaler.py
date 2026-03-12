class ConfidenceScaler:
    def evaluate(self, confidence: float) -> dict:
        value = max(0.0, min(1.0, float(confidence or 0.0)))
        if value < 0.4:
            multiplier = 0.7
        elif value <= 0.7:
            multiplier = 1.0
        else:
            multiplier = 1.2
        return {
            "confidence": round(value, 4),
            "confidence_leverage_multiplier": round(multiplier, 4),
        }
