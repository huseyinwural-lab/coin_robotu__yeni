from datetime import datetime, timezone


def build_futures_liquidation_metrics_snapshot(status: dict) -> dict:
    return {
        "futures_liquidation_risk_score": status.get("portfolio_risk_score", 0.0),
        "futures_distance_to_liquidation": status.get("avg_distance_to_liquidation", 0.0),
        "futures_margin_usage": status.get("margin_usage", 0.0),
        "futures_cascade_warning_count": 1 if status.get("cascade_status") == "CASCADE_WARNING" else 0,
        "futures_emergency_reduce_count": len((status.get("deleverage_plan") or {}).get("actions", [])) if status.get("policy_action") in {"FORCE_REDUCE", "FREEZE"} else 0,
        "futures_forced_reduce_volume": (status.get("deleverage_plan") or {}).get("forced_reduce_volume", 0.0),
        "futures_gate_rejection_total": status.get("gate_rejection_total", 0),
        "futures_policy_state": status.get("policy_action", "ALLOW"),
        "futures_adl_risk_score": status.get("adl_risk_score", 0.0),
        "futures_adl_pressure_side": (status.get("adl_state") or {}).get("dominant_side", "NONE"),
        "futures_adl_gate_reject_total": status.get("adl_gate_rejection_total", 0),
        "futures_adl_reduce_total": len((status.get("adl_reduce_plan") or {}).get("actions", [])),
        "futures_adl_policy_state": (status.get("adl_policy") or {}).get("adl_policy_action", "ALLOW"),
        "futures_capital_recommended_ratio": (status.get("capital_recommendation") or {}).get("recommended", {}).get("futures_capital_ratio", 0.3),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
