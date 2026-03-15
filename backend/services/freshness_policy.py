from dataclasses import dataclass


SLA_SECONDS = {
    "high": 180,
    "normal": 300,
    "low": 900,
}


@dataclass(frozen=True)
class FreshnessDecision:
    bucket: str
    threshold_ms: int
    snapshot_age_ms: float
    is_stale: bool
    reason_code: str | None


def resolve_sla_bucket(*, symbol_selection_mode: str, fallback_active: bool, max_results: int) -> str:
    mode = str(symbol_selection_mode or "all_market_symbols").lower()
    if fallback_active or mode == "top_volume":
        return "high"
    if int(max_results or 0) >= 200:
        return "low"
    return "normal"


def threshold_ms_for_bucket(bucket: str) -> int:
    return int(SLA_SECONDS.get(str(bucket or "normal"), SLA_SECONDS["normal"]) * 1000)


def evaluate_freshness(*, bucket: str, snapshot_age_ms: float) -> FreshnessDecision:
    threshold_ms = threshold_ms_for_bucket(bucket)
    stale = float(snapshot_age_ms or 0.0) > float(threshold_ms)
    return FreshnessDecision(
        bucket=bucket,
        threshold_ms=threshold_ms,
        snapshot_age_ms=float(snapshot_age_ms or 0.0),
        is_stale=stale,
        reason_code="stale_data_skip" if stale else None,
    )
