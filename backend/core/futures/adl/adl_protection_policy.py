class ADLProtectionPolicy:
    def evaluate(self, adl_state: dict) -> dict:
        level = str(adl_state.get("risk_level") or "LOW").upper()
        side = str(adl_state.get("dominant_side") or "NONE").upper()

        if level == "EXTREME":
            return {
                "adl_policy_state": level,
                "adl_policy_action": "FREEZE_SIDE",
                "blocked_side": side,
                "reduce_ratio": 0.4,
                "leverage_cap": 2,
            }
        if level == "HIGH":
            return {
                "adl_policy_state": level,
                "adl_policy_action": "REDUCE_EXPOSURE",
                "blocked_side": side,
                "reduce_ratio": 0.25,
                "leverage_cap": 3,
            }
        if level == "MEDIUM":
            return {
                "adl_policy_state": level,
                "adl_policy_action": "LIMIT_NEW_POSITIONS",
                "blocked_side": side,
                "reduce_ratio": 0.1,
                "leverage_cap": 4,
            }
        return {
            "adl_policy_state": "LOW",
            "adl_policy_action": "ALLOW",
            "blocked_side": "NONE",
            "reduce_ratio": 0.0,
            "leverage_cap": 5,
        }
