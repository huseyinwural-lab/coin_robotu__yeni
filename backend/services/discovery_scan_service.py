from datetime import datetime, timezone

from services.pipeline.cache_store import get_json
from services.quote_asset_policy import filter_allowed_quote_symbols


def _symbol_score(cache, symbol: str) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    volume_event = get_json(cache, f"event:volume_spike:{symbol}") or {}
    if bool(volume_event.get("active", False)):
        score += 2.5
        reasons.append("volume_spike")

    spread_state = get_json(cache, f"market:spread:{symbol}") or {}
    spread_bps = float(spread_state.get("spread_bps") or 0.0)
    if spread_bps <= 25:
        score += 1.5
        reasons.append("spread_ok")
    elif spread_bps >= 40:
        score -= 1.0
        reasons.append("spread_wide")

    momentum_state = get_json(cache, f"market:momentum:{symbol}") or {}
    momentum = abs(float(momentum_state.get("zscore") or 0.0))
    if momentum >= 1.0:
        score += 1.5
        reasons.append("momentum_shift")

    volatility_state = get_json(cache, f"market:volatility:{symbol}") or {}
    volatility = float(volatility_state.get("atr_pct") or 0.0)
    if volatility >= 0.8:
        score += 1.0
        reasons.append("volatility_expansion")

    return score, reasons


def run_discovery_scan(cache, universe_symbols: list[str], *, max_candidates: int) -> dict:
    normalized = filter_allowed_quote_symbols(
        [str(symbol or "").upper().strip() for symbol in universe_symbols]
    )
    rows = []

    for symbol in normalized:
        score, reasons = _symbol_score(cache, symbol)
        rows.append(
            {
                "symbol": symbol,
                "discovery_score": round(score, 6),
                "reasons": reasons,
            }
        )

    rows.sort(key=lambda item: (float(item["discovery_score"]), item["symbol"]), reverse=True)
    selected = rows[: max(1, int(max_candidates or 100))]
    return {
        "universe_size": len(normalized),
        "discovery_candidates": selected,
        "discovery_candidate_symbols": [item["symbol"] for item in selected],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
