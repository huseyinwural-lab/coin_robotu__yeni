class ADLPressureAggregator:
    def aggregate(self, symbol_risk_rows: list[dict]) -> dict:
        if not symbol_risk_rows:
            return {
                "portfolio_adl_risk": 0.0,
                "risk_level": "LOW",
                "dominant_side": "NONE",
                "risk_symbols": [],
                "symbol_details": [],
            }

        total_score = sum(float(item.get("adl_risk_score") or 0.0) for item in symbol_risk_rows)
        portfolio_adl_risk = total_score / len(symbol_risk_rows)

        if portfolio_adl_risk >= 0.75:
            risk_level = "EXTREME"
        elif portfolio_adl_risk >= 0.55:
            risk_level = "HIGH"
        elif portfolio_adl_risk >= 0.3:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        long_pressure = sum(
            float(item.get("adl_risk_score") or 0.0)
            for item in symbol_risk_rows
            if str(item.get("adl_pressure_side") or "NONE").upper() == "LONG"
        )
        short_pressure = sum(
            float(item.get("adl_risk_score") or 0.0)
            for item in symbol_risk_rows
            if str(item.get("adl_pressure_side") or "NONE").upper() == "SHORT"
        )

        if long_pressure == 0 and short_pressure == 0:
            dominant_side = "NONE"
        else:
            dominant_side = "LONG" if long_pressure >= short_pressure else "SHORT"

        sorted_rows = sorted(
            symbol_risk_rows,
            key=lambda item: float(item.get("adl_risk_score") or 0.0),
            reverse=True,
        )
        risk_symbols = [
            item.get("symbol")
            for item in sorted_rows
            if item.get("symbol") and str(item.get("adl_risk_level", "LOW")).upper() in {"HIGH", "EXTREME"}
        ]

        return {
            "portfolio_adl_risk": round(portfolio_adl_risk, 4),
            "risk_level": risk_level,
            "dominant_side": dominant_side,
            "risk_symbols": risk_symbols,
            "symbol_details": sorted_rows,
        }
