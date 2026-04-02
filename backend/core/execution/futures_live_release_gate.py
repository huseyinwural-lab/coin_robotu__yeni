class FuturesLiveReleaseGate:
    def evaluate(self, *, live_mode_enabled: bool, release_gate_status: str, has_live_credentials: bool) -> dict:
        status = str(release_gate_status or "BLOCKED").upper()
        reasons: list[str] = []

        if not live_mode_enabled:
            reasons.append("LIVE_MODE_DISABLED_BY_DEFAULT")
        if has_live_credentials:
            reasons.append("LIVE_CREDENTIALS_FORBIDDEN")

        if status == "BLOCKED":
            reasons.append("RELEASE_GATE_BLOCKED")

        if reasons:
            final_status = "BLOCKED"
        elif status == "PASS_WITH_WARNINGS":
            final_status = "PASS_WITH_WARNINGS"
        else:
            final_status = "PASS"

        return {
            "status": final_status,
            "reasons": reasons if reasons else ["PASS"],
            "order_path_open": final_status in {"PASS", "PASS_WITH_WARNINGS"},
        }
