from datetime import datetime, timezone
from time import perf_counter

from core.users.user_scanner_signal_service import run_user_scanner
from model_domains.decision_feedback_event import build_decision_feedback_event
from model_domains.runtime_scan_candidate import RuntimeScanCandidate
from services.event_priority_service import build_event_priority_distribution
from services.freshness_policy import evaluate_freshness, resolve_sla_bucket
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
    backpressure_policy: dict | None = None,
) -> dict:
    runtime_started = perf_counter()
    fallback_state = evaluate_top_volume_fallback(cache)
    effective_mode = "top_volume" if bool(fallback_state.get("active", False)) else str(symbol_selection_mode or "all_market_symbols")
    backpressure_policy = dict(backpressure_policy or {})
    adjusted_max_results = int(backpressure_policy.get("adjusted_max_results") or max_results)
    freshness_bucket = resolve_sla_bucket(
        symbol_selection_mode=effective_mode,
        fallback_active=bool(fallback_state.get("active", False)),
        max_results=adjusted_max_results,
    )

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
        max_results=adjusted_max_results,
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
    feedback_events: list[dict] = []
    scan_timestamp = datetime.now(timezone.utc)
    stale_skip_count = 0
    stale_skip_symbols: list[str] = []
    strategy_distribution: dict[str, int] = {}
    pass_reason_counter: dict[str, int] = {}
    risk_filtered_count = 0
    fallback_decision_count = 0
    scanner_perf = scan_payload.get("scanner_perf") or {}
    snapshot_age_ms = float(scanner_perf.get("snapshot_age_avg_sec") or 0.0) * 1000.0
    queue_depth = int(scanner_perf.get("queue_depth") or 0)

    freshness_check = evaluate_freshness(bucket=freshness_bucket, snapshot_age_ms=snapshot_age_ms)

    for item in scan_payload.get("items") or []:
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        base_decision = _decision_label(item.get("final_decision") or item.get("signal"))
        confidence = float(item.get("confidence") or 0)
        reason_codes = item.get("reason_codes") or []
        reason = str(reason_codes[0] if reason_codes else "no_reason")
        if freshness_check.is_stale:
            stale_skip_count += 1
            stale_skip_symbols.append(symbol)
            decision = "PASS"
            reason = freshness_check.reason_code or "stale_data_skip"
            risk_filter_reason = "stale_data"
        else:
            decision = base_decision
            risk_filter_reason = "risk_filter" if "risk" in reason else None

        strategy_signal = str(item.get("signal") or item.get("strategy_signal") or decision).upper()
        risk_score = float(item.get("risk_score") or item.get("portfolio_risk_score") or 0)
        market_type = _market_type_for_symbol(symbol, spot_symbols=spot_set, futures_symbols=futures_set)
        strategy_name = str(item.get("strategy_name") or item.get("strategy_code") or "unknown")
        signal_strength = float(item.get("signal_strength") or confidence)
        decision_reason = str(item.get("decision_reason") or reason)

        strategy_distribution[strategy_name] = int(strategy_distribution.get(strategy_name, 0)) + 1
        if decision == "PASS":
            pass_reason_counter[decision_reason] = int(pass_reason_counter.get(decision_reason, 0)) + 1
        if risk_filter_reason is not None:
            risk_filtered_count += 1
        if bool(fallback_state.get("active", False)):
            fallback_decision_count += 1

        decisions.append(
            {
                "symbol": symbol,
                "decision": decision,
                "confidence": round(confidence, 6),
                "reason": reason,
                "strategy_name": strategy_name,
                "signal_strength": round(signal_strength, 6),
                "risk_filter_reason": risk_filter_reason,
                "decision_reason": decision_reason,
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
        feedback_event = build_decision_feedback_event(
            symbol=symbol,
            decision=decision,
            strategy_attribution=strategy_name,
            filter_attribution=risk_filter_reason,
            confidence=confidence,
        )
        feedback_events.append(
            {
                "symbol": feedback_event.symbol,
                "decision": feedback_event.decision,
                "strategy_attribution": feedback_event.strategy_attribution,
                "filter_attribution": feedback_event.filter_attribution,
                "confidence": feedback_event.confidence,
                "decision_timestamp": feedback_event.decision_timestamp,
                "outcome_placeholder": feedback_event.outcome_placeholder,
            }
        )
        if decision in {"LONG", "SHORT"}:
            candidate_symbols.append(symbol)

    if candidate_rows:
        db.add_all(candidate_rows)
        db.commit()

    decision_latency_ms = (perf_counter() - decision_started) * 1000.0
    runtime_latency_ms = (perf_counter() - runtime_started) * 1000.0
    event_priority = build_event_priority_distribution(
        cache,
        [item.get("symbol") for item in decisions],
        position_activity=len(candidate_symbols) > 0,
    )

    queue_depth_state = "high" if queue_depth > 50 else "normal"
    backpressure_active = bool(backpressure_policy.get("active", False))
    fallback_reason_code = str(fallback_state.get("last_trigger_metric") or "none")

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
        "decision_feedback_events": feedback_events,
        "universe_size": int(universe_payload.get("combined_universe_size") or 0),
        "scanner_perf": scanner_perf,
        "freshness": {
            "sla_bucket": freshness_check.bucket,
            "threshold_ms": freshness_check.threshold_ms,
            "snapshot_age_ms": round(freshness_check.snapshot_age_ms, 4),
            "stale_skip_count": stale_skip_count,
            "stale_skip_symbols": stale_skip_symbols[:100],
        },
        "backpressure": {
            "active": backpressure_active,
            "reason_code": str(backpressure_policy.get("reason_code") or "none"),
            "queue_depth_state": queue_depth_state,
            "scan_interval_seconds": int(backpressure_policy.get("scan_interval_seconds") or 15),
            "adjusted_max_results": adjusted_max_results,
        },
        "event_priority": event_priority,
        "explainability_summary": {
            "strategy_decision_distribution": strategy_distribution,
            "pass_reasons": pass_reason_counter,
            "risk_filtered_count": risk_filtered_count,
            "stale_filtered_count": stale_skip_count,
            "fallback_decision_count": fallback_decision_count,
            "fallback_reason_code": fallback_reason_code,
        },
        "runtime_metrics": {
            "scan_latency_ms": round(float(scanner_perf.get("cycle_duration_ms") or runtime_latency_ms), 4),
            "decision_latency_ms": round(decision_latency_ms, 4),
            "snapshot_age_ms": round(snapshot_age_ms, 4),
            "queue_depth": queue_depth,
            "candidate_count": len(set(candidate_symbols)),
            "stale_skip_count": stale_skip_count,
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
