class StrategyInteractionGuard:
    def __init__(self, *, max_same_side_per_symbol: int = 2):
        self.max_same_side_per_symbol = max(1, int(max_same_side_per_symbol))

    @staticmethod
    def _blocked_item(item: dict, reason: str) -> dict:
        return {
            **item,
            "decision": "REJECT",
            "reason_code": "GATE_REJECT",
            "decision_layer": "GATE",
            "reasons": sorted(set((item.get("reasons") or []) + [reason])),
        }

    def apply(self, decisions: list[dict]) -> tuple[list[dict], list[dict]]:
        by_symbol: dict[str, list[dict]] = {}
        for row in decisions:
            by_symbol.setdefault(str(row.get("symbol") or "UNKNOWN").upper(), []).append(row)

        output: list[dict] = []
        blocked: list[dict] = []
        for symbol, rows in by_symbol.items():
            allowed = [item for item in rows if item.get("decision") == "ALLOW"]
            if not allowed:
                output.extend(rows)
                continue

            long_candidates = [item for item in allowed if item.get("side") == "LONG"]
            short_candidates = [item for item in allowed if item.get("side") == "SHORT"]
            if long_candidates and short_candidates:
                keep = max(allowed, key=lambda item: float(item.get("confidence") or 0.0))
                for item in rows:
                    if item is keep or item.get("decision") != "ALLOW":
                        output.append(item)
                        continue
                    blocked_item = self._blocked_item(item, "STRATEGY_INTERACTION_CONFLICT")
                    blocked.append(blocked_item)
                    output.append(blocked_item)
            else:
                same_side = long_candidates if long_candidates else short_candidates
                ordered = sorted(same_side, key=lambda item: float(item.get("confidence") or 0.0), reverse=True)
                keep_refs = set(id(item) for item in ordered[: self.max_same_side_per_symbol])
                for item in rows:
                    if item.get("decision") != "ALLOW" or id(item) in keep_refs:
                        output.append(item)
                        continue
                    blocked_item = self._blocked_item(item, "STRATEGY_INTERACTION_STACKED")
                    blocked.append(blocked_item)
                    output.append(blocked_item)

        return output, blocked
