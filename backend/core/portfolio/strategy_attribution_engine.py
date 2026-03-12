def build_strategy_attribution(decisions: list[dict], paper_trades: list[dict]) -> dict:
    pnl_by_strategy: dict[str, float] = {}
    trade_count_by_strategy: dict[str, int] = {}
    risk_by_strategy: dict[str, list[str]] = {}

    for trade in paper_trades:
        strategy = str(trade.get("strategy") or "unknown")
        pnl = float(trade.get("paper_pnl") or 0.0)
        pnl_by_strategy[strategy] = round(pnl_by_strategy.get(strategy, 0.0) + pnl, 6)
        trade_count_by_strategy[strategy] = int(trade_count_by_strategy.get(strategy, 0) + 1)

    for decision in decisions:
        strategy = str(decision.get("strategy") or decision.get("strategy_id") or "unknown")
        reasons = decision.get("reasons") or []
        if reasons:
            risk_by_strategy.setdefault(strategy, [])
            for reason in reasons:
                if reason not in risk_by_strategy[strategy]:
                    risk_by_strategy[strategy].append(reason)

    strategies = sorted(set(list(pnl_by_strategy.keys()) + list(trade_count_by_strategy.keys()) + list(risk_by_strategy.keys())))
    rows = []
    for strategy in strategies:
        rows.append(
            {
                "strategy": strategy,
                "pnl_attribution": pnl_by_strategy.get(strategy, 0.0),
                "trade_count": trade_count_by_strategy.get(strategy, 0),
                "risk_attribution": risk_by_strategy.get(strategy, []),
            }
        )

    return {
        "strategy_attribution": rows,
    }
