def detect_strategy_drift(strategy_rows: list[dict]) -> dict:
    alerts: list[dict] = []
    for row in strategy_rows:
        strategy = str(row.get("strategy") or "unknown")
        pnl = float(row.get("pnl", 0.0))
        confidence = float(row.get("avg_confidence", 0.0))
        execution_quality = float(row.get("execution_quality", 0.0))
        reject_rate = float(row.get("reject_rate", 0.0))

        deterioration = pnl < -0.002
        divergence = confidence > 0.65 and pnl < 0
        execution_drop = execution_quality < 0.5 or reject_rate > 0.45
        if deterioration or divergence or execution_drop:
            reasons = []
            if deterioration:
                reasons.append("PNL_DETERIORATION")
            if divergence:
                reasons.append("CONFIDENCE_RESULT_DIVERGENCE")
            if execution_drop:
                reasons.append("EXECUTION_QUALITY_DROP")
            alerts.append(
                {
                    "strategy": strategy,
                    "event": "STRATEGY_DRIFT_ALERT",
                    "severity": "HIGH" if (deterioration and execution_drop) else "MEDIUM",
                    "reasons": reasons,
                }
            )

    return {
        "strategy_drift_alerts": alerts,
        "alert_count": len(alerts),
    }
