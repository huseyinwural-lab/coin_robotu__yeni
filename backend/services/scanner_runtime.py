from datetime import datetime, timezone
from time import perf_counter

from core.users.user_scanner_signal_service import run_user_scanner
from model_domains.runtime_scan_candidate import RuntimeScanCandidate
from services.pipeline.cache_store import get_json, set_json
from services.top_volume_fallback import evaluate_top_volume_fallback
from services.universe_service import get_full_market_universe


def _decision_label(value: str) -> str:
    candidate = str(value or "PASS").strip().upper()
    if candidate in {"LONG", "SHORT"}:
        return candidate
    return "PASS"


def _market_type_for_symbol(symbol: str, *, spot_symbols: set[str], futures_symbols: set[str]) -> str:
    if symbol in futures_symbols:
        return "futures"
    if symbol in spot_symbols:
        return "spot"
    return "spot"


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
    runtime_started = perf_counter()
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

    decision_started = perf_counter()
    decisions = []
    candidate_symbols: list[str] = []
    spot_set = {str(symbol).upper() for symbol in (universe_payload.get("spot_symbols") or [])}
    futures_set = {str(symbol).upper() for symbol in (universe_payload.get("futures_symbols") or [])}
    candidate_rows: list[RuntimeScanCandidate] = []
    scan_timestamp = datetime.now(timezone.utc)

    for item in scan_payload.get("items") or []:
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        decision = _decision_label(item.get("final_decision") or item.get("signal"))
        confidence = float(item.get("confidence") or 0)
        reason_codes = item.get("reason_codes") or []
        reason = str(reason_codes[0] if reason_codes else "no_reason")
        strategy_signal = str(item.get("signal") or item.get("strategy_signal") or decision).upper()
        risk_score = float(item.get("risk_score") or item.get("portfolio_risk_score") or 0)
        market_type = _market_type_for_symbol(symbol, spot_symbols=spot_set, futures_symbols=futures_set)

        decisions.append(
            {
                "symbol": symbol,
                "decision": decision,
                "confidence": round(confidence, 6),
                "reason": reason,
            }
        )
        candidate_rows.append(
            RuntimeScanCandidate(
                symbol=symbol,
                market_type=market_type,
                scan_timestamp=scan_timestamp,
                strategy_signal=strategy_signal,
                risk_score=risk_score,
                decision=decision,
                confidence=confidence,
            )
        )
        if decision in {"LONG", "SHORT"}:
            candidate_symbols.append(symbol)

    if candidate_rows:
        db.add_all(candidate_rows)
        db.commit()

    decision_latency_ms = (perf_counter() - decision_started) * 1000.0
    runtime_latency_ms = (perf_counter() - runtime_started) * 1000.0
    scanner_perf = scan_payload.get("scanner_perf") or {}
    snapshot_age_ms = float(scanner_perf.get("snapshot_age_avg_sec") or 0.0) * 1000.0
    queue_depth = int(scanner_perf.get("queue_depth") or 0)

    payload = {
        "user_id": user_id,
        "run_id": scan_payload.get("run_id"),
        "symbol_selection_mode": str(symbol_selection_mode or "all_market_symbols").lower(),
        "effective_mode": str(effective_mode).lower(),
        "fallback_active": bool(fallback_state.get("active", False)),
        "fallback_state": fallback_state,
        "candidate_symbols": sorted(set(candidate_symbols)),
        "candidate_count": len(set(candidate_symbols)),
        "persisted_candidate_count": len(candidate_rows),
        "decision_count": len(decisions),
        "decisions": decisions,
        "universe_size": int(universe_payload.get("combined_universe_size") or 0),
        "scanner_perf": scanner_perf,
        "runtime_metrics": {
            "scan_latency_ms": round(float(scanner_perf.get("cycle_duration_ms") or runtime_latency_ms), 4),
            "decision_latency_ms": round(decision_latency_ms, 4),
            "snapshot_age_ms": round(snapshot_age_ms, 4),
            "queue_depth": queue_depth,
            "candidate_count": len(set(candidate_symbols)),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_json(cache, f"scanner:runtime:snapshot:user:{user_id}", payload)
    set_json(cache, "scanner:runtime:latest:global", payload)
    return payload


def get_runtime_snapshot(cache, *, user_id: str) -> dict:
    return get_json(cache, f"scanner:runtime:snapshot:user:{user_id}") or {}


def get_latest_global_runtime_snapshot(cache) -> dict:
    return get_json(cache, "scanner:runtime:latest:global") or {}
