from datetime import datetime, timezone

from services.freshness_policy import evaluate_freshness
from services.pipeline.cache_store import get_json


def _qualification_row(cache, symbol: str, discovery_score: float, *, snapshot_age_ms: float, freshness_bucket: str) -> dict:
    reasons: list[str] = []
    qualify_score = float(discovery_score)

    trend_state = get_json(cache, f"market:trend:{symbol}") or {}
    trend_strength = float(trend_state.get("strength") or 0.0)
    if trend_strength >= 0.6:
        qualify_score += 1.5
        reasons.append("trend_fit")

    breakout_state = get_json(cache, f"market:breakout:{symbol}") or {}
    if bool(breakout_state.get("ready", False)):
        qualify_score += 1.2
        reasons.append("breakout_ready")

    mean_reversion_state = get_json(cache, f"market:mean_reversion:{symbol}") or {}
    if bool(mean_reversion_state.get("eligible", False)):
        qualify_score += 0.8
        reasons.append("mean_reversion_eligible")

    liquidity_state = get_json(cache, f"market:liquidity:{symbol}") or {}
    slippage_bps = float(liquidity_state.get("slippage_bps") or 0.0)
    if slippage_bps > 50:
        qualify_score -= 2.0
        reasons.append("liquidity_penalty")

    freshness = evaluate_freshness(bucket=freshness_bucket, snapshot_age_ms=snapshot_age_ms)
    stale = bool(freshness.is_stale)
    if stale:
        qualify_score -= 3.0
        reasons.append("stale_filtered")

    return {
        "symbol": symbol,
        "qualification_score": round(qualify_score, 6),
        "stale_filtered": stale,
        "reasons": reasons,
    }


def run_qualification_scan(
    cache,
    discovery_candidates: list[dict],
    *,
    max_candidates: int,
    snapshot_age_ms: float,
    freshness_bucket: str,
) -> dict:
    rows = []
    stale_filtered_count = 0

    for item in discovery_candidates:
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        row = _qualification_row(
            cache,
            symbol,
            float(item.get("discovery_score") or 0.0),
            snapshot_age_ms=float(snapshot_age_ms or 0.0),
            freshness_bucket=freshness_bucket,
        )
        if row["stale_filtered"]:
            stale_filtered_count += 1
            continue
        rows.append(row)

    rows.sort(key=lambda item: (float(item["qualification_score"]), item["symbol"]), reverse=True)
    selected = rows[: max(1, int(max_candidates or 30))]
    return {
        "qualified_candidates": selected,
        "qualified_candidate_symbols": [item["symbol"] for item in selected],
        "qualified_count": len(selected),
        "stale_filtered_count": stale_filtered_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
