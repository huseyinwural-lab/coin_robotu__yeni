from datetime import datetime, timezone

from core.users.user_scanner_signal_service import run_user_scanner
from services.pipeline.cache_store import get_json, set_json
from services.top_volume_fallback import evaluate_top_volume_fallback
from services.universe_service import get_full_market_universe


def _decision_label(value: str) -> str:
    candidate = str(value or "PASS").strip().upper()
    if candidate in {"LONG", "SHORT"}:
        return candidate
    return "PASS"


def run_scanner_runtime(
    db,
    cache,
    *,
    user_id: str,
    symbol_selection_mode: str = "all_market_symbols",
    selected_symbols: list[str] | None = None,
    symbol_source: str = "crypto",
    max_results: int = 120,
) -> dict:
    fallback_state = evaluate_top_volume_fallback(cache)
    effective_mode = "top_volume" if bool(fallback_state.get("active", False)) else str(symbol_selection_mode or "all_market_symbols")

    universe_payload = get_full_market_universe(
        db,
        cache,
        scanner_mode=effective_mode,
        selected_symbols=selected_symbols or [],
        top_n=50,
    )

    scan_payload = run_user_scanner(
        db,
        user_id,
        requested_mode=None,
        max_results=max_results,
        symbol_source=symbol_source,
        selected_symbols=selected_symbols or [],
        symbol_selection_mode=effective_mode,
    )

    decisions = []
    candidate_symbols: list[str] = []
    for item in scan_payload.get("items") or []:
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        decision = _decision_label(item.get("final_decision") or item.get("signal"))
        confidence = float(item.get("confidence") or 0)
        strategy = str(item.get("strategy_code") or item.get("strategy") or "unknown")
        reason_codes = item.get("reason_codes") or []
        reason = str(reason_codes[0] if reason_codes else "no_reason")

        decisions.append(
            {
                "symbol": symbol,
                "decision": decision,
                "confidence": round(confidence, 6),
                "strategy": strategy,
                "reason": reason,
            }
        )
        if decision in {"LONG", "SHORT"}:
            candidate_symbols.append(symbol)

    payload = {
        "user_id": user_id,
        "run_id": scan_payload.get("run_id"),
        "symbol_selection_mode": str(symbol_selection_mode or "all_market_symbols").lower(),
        "effective_mode": str(effective_mode).lower(),
        "fallback_active": bool(fallback_state.get("active", False)),
        "fallback_state": fallback_state,
        "candidate_symbols": sorted(set(candidate_symbols)),
        "candidate_count": len(set(candidate_symbols)),
        "decision_count": len(decisions),
        "decisions": decisions,
        "universe_size": int(universe_payload.get("combined_universe_size") or 0),
        "scanner_perf": scan_payload.get("scanner_perf") or {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, f"scanner:runtime:snapshot:user:{user_id}", payload)
    set_json(cache, "scanner:runtime:latest:global", payload)
    return payload


def get_runtime_snapshot(cache, *, user_id: str) -> dict:
    return get_json(cache, f"scanner:runtime:snapshot:user:{user_id}") or {}


def get_latest_global_runtime_snapshot(cache) -> dict:
    return get_json(cache, "scanner:runtime:latest:global") or {}
