from datetime import datetime, timezone

from services.pipeline.cache_store import set_json
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
        result = run_scanner_runtime(
            db,
            self.cache,
            user_id=user_id,
            symbol_selection_mode=symbol_selection_mode,
            selected_symbols=selected_symbols,
            symbol_source=symbol_source,
            max_results=max_results,
        )
        set_json(
            self.cache,
            f"scanner:working_set:user:{user_id}",
            {
                "candidate_symbols": result.get("candidate_symbols") or [],
                "candidate_count": int(result.get("candidate_count") or 0),
                "effective_mode": result.get("effective_mode"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return result
