def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_strategy_attribution(decisions: list[dict], paper_trades: list[dict]) -> dict:
    by_strategy_decisions: dict[str, list[dict]] = {}
    by_strategy_trades: dict[str, list[dict]] = {}

    for decision in decisions:
        strategy = str(decision.get("strategy") or decision.get("strategy_id") or "unknown")
        by_strategy_decisions.setdefault(strategy, []).append(decision)

    for trade in paper_trades:
        strategy = str(trade.get("strategy") or "unknown")
        by_strategy_trades.setdefault(strategy, []).append(trade)

    strategies = sorted(set(list(by_strategy_decisions.keys()) + list(by_strategy_trades.keys())))
    rows = []
    total_pnl = 0.0

    for strategy in strategies:
        decisions_for_strategy = by_strategy_decisions.get(strategy, [])
        trades_for_strategy = by_strategy_trades.get(strategy, [])

        pnl = sum(_safe_float(item.get("paper_pnl")) for item in trades_for_strategy)
        total_pnl += pnl
        trade_count = len(trades_for_strategy)
        wins = len([item for item in trades_for_strategy if _safe_float(item.get("paper_pnl")) > 0])
        losses = len([item for item in trades_for_strategy if _safe_float(item.get("paper_pnl")) < 0])
        avg_pnl = (pnl / trade_count) if trade_count > 0 else 0.0

        signal_total = len(decisions_for_strategy)
        allow_total = len([item for item in decisions_for_strategy if item.get("decision") == "ALLOW"])
        reject_total = len([item for item in decisions_for_strategy if item.get("decision") == "REJECT"])
        reject_rate = (reject_total / signal_total) if signal_total > 0 else 0.0

        avg_confidence = (
            sum(_safe_float(item.get("confidence")) for item in decisions_for_strategy) / signal_total
            if signal_total > 0
            else 0.0
        )
        avg_slippage_bps = (
            sum(_safe_float(item.get("expected_slippage_bps")) for item in trades_for_strategy) / trade_count
            if trade_count > 0
            else 0.0
        )
        avg_latency_ms = (
            sum(_safe_float(item.get("execution_latency_ms")) for item in trades_for_strategy) / trade_count
            if trade_count > 0
            else 0.0
        )

        reasons: list[str] = []
        for decision in decisions_for_strategy:
            for reason in decision.get("reasons") or []:
                if reason not in reasons:
                    reasons.append(reason)

        rows.append(
            {
                "strategy": strategy,
                "pnl_attribution": round(pnl, 6),
                "trade_count": trade_count,
                "wins": wins,
                "losses": losses,
                "win_rate": round((wins / trade_count) if trade_count > 0 else 0.0, 4),
                "avg_pnl_per_trade": round(avg_pnl, 6),
                "signal_total": signal_total,
                "allow_total": allow_total,
                "reject_total": reject_total,
                "reject_rate": round(reject_rate, 4),
                "avg_confidence": round(avg_confidence, 4),
                "avg_expected_slippage_bps": round(avg_slippage_bps, 4),
                "avg_execution_latency_ms": round(avg_latency_ms, 2),
                "risk_attribution": reasons,
            }
        )

    rows = sorted(rows, key=lambda item: item["pnl_attribution"], reverse=True)
    for row in rows:
        row["pnl_contribution_ratio"] = round(
            (row["pnl_attribution"] / total_pnl) if total_pnl not in {0.0, -0.0} else 0.0,
            4,
        )

    return {
        "strategy_attribution": rows,
        "portfolio_pnl_total": round(total_pnl, 6),
    }
