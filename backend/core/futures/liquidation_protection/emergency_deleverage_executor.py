from dataclasses import asdict, dataclass


@dataclass
class ExecutionPlan:
    positions_to_reduce: list[dict]
    reduce_ratio: float
    execution_priority: list[str]


class EmergencyDeleverageExecutor:
    def execute(self, portfolio: list[dict], policy_decision: dict) -> ExecutionPlan:
        policy_action = str(policy_decision.get("policy_action", "ALLOW")).upper()
        reduce_ratio = float(policy_decision.get("reduce_ratio", 0.0) or 0.0)
        if policy_action not in {"REDUCE", "FORCE_REDUCE", "FREEZE", "LIMIT_NEW"}:
            return ExecutionPlan(positions_to_reduce=[], reduce_ratio=0.0, execution_priority=[])

        ranked = sorted(
            portfolio,
            key=lambda item: (
                float(item.get("distance_to_liquidation") or 999),
                -float(item.get("leverage") or 0),
                -float(item.get("position_risk_score") or 0),
            ),
        )

        positions_to_reduce: list[dict] = []
        execution_priority: list[str] = []
        for index, row in enumerate(ranked, start=1):
            notional = float(row.get("notional_value") or 0.0)
            reduce_notional = max(notional * reduce_ratio, 0.0)
            if reduce_notional <= 0:
                continue
            symbol = str(row.get("symbol") or "UNKNOWN")
            execution_priority.append(symbol)
            positions_to_reduce.append(
                {
                    "symbol": symbol,
                    "side": row.get("side"),
                    "reduce_notional": round(reduce_notional, 4),
                    "priority": index,
                    "reason": "forced_exit" if policy_action == "FREEZE" else "risk_reduce",
                }
            )

        return ExecutionPlan(
            positions_to_reduce=positions_to_reduce,
            reduce_ratio=round(reduce_ratio, 4),
            execution_priority=execution_priority,
        )


def build_deleverage_plan(positions: list[dict], policy_action: str, reduce_ratio: float) -> dict:
    executor = EmergencyDeleverageExecutor()
    plan = executor.execute(
        portfolio=positions,
        policy_decision={"policy_action": policy_action, "reduce_ratio": reduce_ratio},
    )
    payload = asdict(plan)
    payload["actions"] = [
        {
            "symbol": item["symbol"],
            "side": item.get("side"),
            "action": item.get("reason"),
            "reduce_notional": item.get("reduce_notional", 0.0),
            "reduce_ratio": payload["reduce_ratio"],
        }
        for item in payload["positions_to_reduce"]
    ]
    payload["forced_reduce_volume"] = round(
        sum(float(item.get("reduce_notional") or 0.0) for item in payload["positions_to_reduce"]),
        4,
    )
    return payload
