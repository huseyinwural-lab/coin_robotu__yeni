class PortfolioLeverageGuard:
    def evaluate(self, *, portfolio_leverage: float, proposed_leverage: float) -> dict:
        portfolio_value = float(portfolio_leverage or 0.0)
        proposed = float(proposed_leverage or 0.0)

        portfolio_limit = 2.5
        trade_limit = 5.0

        if portfolio_value >= portfolio_limit:
            adjustment = 0.55
        elif portfolio_value >= 2.0:
            adjustment = 0.75
        else:
            adjustment = 1.0

        guarded_proposed = min(proposed * adjustment, trade_limit)
        return {
            "portfolio_adjustment_factor": round(adjustment, 4),
            "portfolio_leverage": round(portfolio_value, 4),
            "portfolio_limit": portfolio_limit,
            "max_trade_leverage": trade_limit,
            "guarded_leverage_cap": round(guarded_proposed, 4),
        }
