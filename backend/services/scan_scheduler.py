from datetime import datetime, timezone

from services.event_priority_service import build_event_priority_distribution
from services.pipeline.cache_store import get_json, set_json
from services.scanner_runtime import run_scanner_runtime


class ScanScheduler:
    def __init__(self, cache):
        self.cache = cache

    def run_user_scan(
        self,
        db,
        *,
        user_id: str,
        symbol_selection_mode: str,
        symbol_source: str,
        selected_symbols: list[str],
        max_results: int,
    ) -> dict:
        backpressure = self._compute_backpressure_policy(max_results=max_results)
        event_priority = build_event_priority_distribution(
            self.cache,
            selected_symbols,
            position_activity=False,
        )
        result = run_scanner_runtime(
            db,
            self.cache,
            user_id=user_id,
            symbol_selection_mode=symbol_selection_mode,
            selected_symbols=selected_symbols,
            symbol_source=symbol_source,
            max_results=backpressure["adjusted_max_results"],
            backpressure_policy={
                "active": backpressure["active"],
                "reason_code": backpressure["reason_code"],
                "scan_interval_seconds": backpressure["scan_interval_seconds"],
                "adjusted_max_results": backpressure["adjusted_max_results"],
                "discovery_cap": backpressure["discovery_cap"],
                "qualification_cap": backpressure["qualification_cap"],
                "decision_cap": backpressure["decision_cap"],
                "event_priority_distribution": event_priority.get("distribution") or {},
            },
        )
        set_json(
            self.cache,
            f"scanner:working_set:user:{user_id}",
            {
                "candidate_symbols": result.get("candidate_symbols") or [],
                "candidate_count": int(result.get("candidate_count") or 0),
                "effective_mode": result.get("effective_mode"),
                "backpressure": backpressure,
                "tiered_caps": {
                    "discovery_cap": int(backpressure.get("discovery_cap") or 0),
                    "qualification_cap": int(backpressure.get("qualification_cap") or 0),
                    "decision_cap": int(backpressure.get("decision_cap") or 0),
                },
                "event_priority_distribution": event_priority.get("distribution") or {},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return result

    def _compute_backpressure_policy(self, *, max_results: int) -> dict:
        queue_state = get_json(self.cache, "scanner:queue:state") or {}
        runtime_state = get_json(self.cache, "scanner:runtime:latest:global") or {}
        fallback_state = get_json(self.cache, "scanner:runtime:fallback_state") or {}
        metrics = runtime_state.get("runtime_metrics") or {}

        queue_depth = int(metrics.get("queue_depth") or queue_state.get("depth") or 0)
        scan_latency_ms = float(metrics.get("scan_latency_ms") or queue_state.get("cycle_latency_ms") or 0.0)
        snapshot_age_ms = float(metrics.get("snapshot_age_ms") or 0.0)

        adjusted_max = int(max_results)
        interval_seconds = 15
        reason_codes: list[str] = []
        fallback_active = bool(fallback_state.get("active", False))

        discovery_cap = 120 if fallback_active else 200
        qualification_cap = 50 if fallback_active else 100
        decision_cap = 20 if fallback_active else 30

        if queue_depth > 40:
            interval_seconds = 30
            reason_codes.append("queue_depth_high")
            discovery_cap = min(discovery_cap, 120)
            qualification_cap = min(qualification_cap, 60)
            decision_cap = min(decision_cap, 20)

        if scan_latency_ms > 4000:
            adjusted_max = max(20, int(adjusted_max * 0.6))
            reason_codes.append("scan_latency_high")
            discovery_cap = min(discovery_cap, 100)
            qualification_cap = min(qualification_cap, 50)
            decision_cap = min(decision_cap, 15)

        if snapshot_age_ms > 150000:
            adjusted_max = max(10, int(adjusted_max * 0.7))
            reason_codes.append("snapshot_age_high")
            discovery_cap = min(discovery_cap, 80)
            qualification_cap = min(qualification_cap, 40)
            decision_cap = min(decision_cap, 10)

        return {
            "active": len(reason_codes) > 0,
            "reason_code": "+".join(reason_codes) if reason_codes else "none",
            "scan_interval_seconds": interval_seconds,
            "adjusted_max_results": adjusted_max,
            "discovery_cap": discovery_cap,
            "qualification_cap": qualification_cap,
            "decision_cap": decision_cap,
            "queue_depth": queue_depth,
            "scan_latency_ms": scan_latency_ms,
            "snapshot_age_ms": snapshot_age_ms,
        }
