class ADLExposureReducer:
    def build_plan(self, positions: list[dict], adl_state: dict, policy: dict) -> dict:
        action = str(policy.get("adl_policy_action") or "ALLOW").upper()
        blocked_side = str(policy.get("blocked_side") or "NONE").upper()
        reduce_ratio = float(policy.get("reduce_ratio") or 0.0)
        if action not in {"REDUCE_EXPOSURE", "FREEZE_SIDE"}:
            return {"actions": [], "total_reduce_notional": 0.0, "reduce_ratio": 0.0}

        ranked = sorted(
            positions,
            key=lambda item: (
                -float(item.get("leverage") or 0.0),
                float(item.get("distance_to_liquidation") or 100.0),
                -float(item.get("funding_bias_score") or 0.0),
                -float(item.get("cluster_exposure") or 0.0),
            ),
        )

        actions = []
        total_reduce_notional = 0.0
        for priority, item in enumerate(ranked, start=1):
            side = str(item.get("side") or "NONE").upper()
            if action == "FREEZE_SIDE" and blocked_side in {"LONG", "SHORT"} and side != blocked_side:
                continue
            reduce_notional = float(item.get("notional_value") or 0.0) * reduce_ratio
            if reduce_notional <= 0:
                continue
            total_reduce_notional += reduce_notional
            actions.append(
                {
                    "symbol": item.get("symbol"),
                    "side": side,
                    "priority": priority,
                    "reason": "ADL_PRESSURE_REDUCTION",
                    "reduce_notional": round(reduce_notional, 4),
                }
            )

        return {
            "adl_risk_level": adl_state.get("risk_level", "LOW"),
            "actions": actions,
            "total_reduce_notional": round(total_reduce_notional, 4),
            "reduce_ratio": round(reduce_ratio, 4),
        }
