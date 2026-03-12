from datetime import datetime, timezone


def build_portfolio_capital_registry(
    *,
    portfolio_equity: float,
    used_margin: float,
    allocated_capital: float,
    risk_budget_ratio: float = 0.8,
) -> dict:
    equity = max(float(portfolio_equity or 0.0), 0.0)
    used = max(float(used_margin or 0.0), 0.0)
    allocated = max(float(allocated_capital or 0.0), 0.0)
    risk_budget_total = equity * max(0.0, min(float(risk_budget_ratio), 1.0))
    available_capital = max(equity - used - allocated, 0.0)

    return {
        "portfolio_equity": round(equity, 4),
        "available_capital": round(available_capital, 4),
        "allocated_capital": round(allocated, 4),
        "used_margin": round(used, 4),
        "risk_budget_total": round(risk_budget_total, 4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
