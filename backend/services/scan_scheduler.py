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
        return run_scanner_runtime(
            db,
            self.cache,
            user_id=user_id,
            symbol_selection_mode=symbol_selection_mode,
            selected_symbols=selected_symbols,
            symbol_source=symbol_source,
            max_results=max_results,
        )
