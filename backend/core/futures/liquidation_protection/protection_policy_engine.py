from dataclasses import asdict, dataclass


RISK_ORDER = {
    "SAFE": 0,
    "WARNING": 1,
    "CRITICAL": 2,
    "EMERGENCY": 3,
}


@dataclass
class PolicyDecision:
    policy_state: str
    policy_action: str
    reduce_ratio: float
    leverage_cap: float
    reason_code: str


class ProtectionPolicyEngine:
    def evaluate(
        self,
        liquidation_state: str,
        cascade_state: str,
        margin_state: str,
        adl_state: str,
    ) -> PolicyDecision:
        liquidation_state = (liquidation_state or "SAFE").upper()
        margin_state = (margin_state or "SAFE").upper()
        adl_state = (adl_state or "LOW").upper()
        cascade_state = (cascade_state or "NONE").upper()

        adl_to_policy_level = {
            "LOW": "SAFE",
            "MEDIUM": "WARNING",
            "HIGH": "CRITICAL",
            "EXTREME": "EMERGENCY",
        }
        cascade_to_policy_level = {
            "NONE": "SAFE",
            "CASCADE_WARNING": "WARNING",
            "CASCADE_CONFIRMED": "EMERGENCY",
        }

        merged_levels = [
            liquidation_state,
            margin_state,
            adl_to_policy_level.get(adl_state, "SAFE"),
            cascade_to_policy_level.get(cascade_state, "SAFE"),
        ]
        policy_state = max(merged_levels, key=lambda item: RISK_ORDER.get(item, 0))

        if cascade_state == "CASCADE_CONFIRMED" and policy_state in {"CRITICAL", "EMERGENCY"}:
            return PolicyDecision(
                policy_state="EMERGENCY",
                policy_action="FREEZE",
                reduce_ratio=0.5,
                leverage_cap=2,
                reason_code="CASCADE_EMERGENCY",
            )
        if policy_state == "EMERGENCY":
            return PolicyDecision(
                policy_state=policy_state,
                policy_action="FORCE_REDUCE",
                reduce_ratio=0.35,
                leverage_cap=2,
                reason_code="EMERGENCY_RISK",
            )
        if policy_state == "CRITICAL":
            return PolicyDecision(
                policy_state=policy_state,
                policy_action="REDUCE",
                reduce_ratio=0.25,
                leverage_cap=3,
                reason_code="CRITICAL_RISK",
            )
        if policy_state == "WARNING":
            return PolicyDecision(
                policy_state=policy_state,
                policy_action="LIMIT_NEW",
                reduce_ratio=0.1,
                leverage_cap=4,
                reason_code="WARNING_RISK",
            )
        return PolicyDecision(
            policy_state="SAFE",
            policy_action="ALLOW",
            reduce_ratio=0.0,
            leverage_cap=5,
            reason_code="SAFE",
        )


def resolve_protection_policy(
    *,
    risk_level: str,
    margin_state: str,
    cascade_status: str,
    adl_state: str = "LOW",
) -> dict:
    engine = ProtectionPolicyEngine()
    result = engine.evaluate(
        liquidation_state=risk_level,
        cascade_state=cascade_status,
        margin_state=margin_state,
        adl_state=adl_state,
    )
    return asdict(result)
