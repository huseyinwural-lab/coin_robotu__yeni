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
                "event_priority_distribution": event_priority.get("distribution") or {},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return result

    def _compute_backpressure_policy(self, *, max_results: int) -> dict:
        queue_state = get_json(self.cache, "scanner:queue:state") or {}
        runtime_state = get_json(self.cache, "scanner:runtime:latest:global") or {}
        metrics = runtime_state.get("runtime_metrics") or {}

        queue_depth = int(metrics.get("queue_depth") or queue_state.get("depth") or 0)
        scan_latency_ms = float(metrics.get("scan_latency_ms") or queue_state.get("cycle_latency_ms") or 0.0)
        snapshot_age_ms = float(metrics.get("snapshot_age_ms") or 0.0)

        adjusted_max = int(max_results)
        interval_seconds = 15
        reason_codes: list[str] = []

        if queue_depth > 40:
            interval_seconds = 30
            reason_codes.append("queue_depth_high")

        if scan_latency_ms > 4000:
            adjusted_max = max(20, int(adjusted_max * 0.6))
            reason_codes.append("scan_latency_high")

        if snapshot_age_ms > 150000:
            adjusted_max = max(10, int(adjusted_max * 0.7))
            reason_codes.append("snapshot_age_high")

        return {
            "active": len(reason_codes) > 0,
            "reason_code": "+".join(reason_codes) if reason_codes else "none",
            "scan_interval_seconds": interval_seconds,
            "adjusted_max_results": adjusted_max,
            "queue_depth": queue_depth,
            "scan_latency_ms": scan_latency_ms,
            "snapshot_age_ms": snapshot_age_ms,
        }
