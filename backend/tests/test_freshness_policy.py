from services.freshness_policy import evaluate_freshness, resolve_sla_bucket


def test_freshness_bucket_resolution():
    assert resolve_sla_bucket(symbol_selection_mode="top_volume", fallback_active=False, max_results=50) == "high"
    assert resolve_sla_bucket(symbol_selection_mode="all_market_symbols", fallback_active=False, max_results=100) == "normal"
    assert resolve_sla_bucket(symbol_selection_mode="all_market_symbols", fallback_active=False, max_results=250) == "low"


def test_freshness_stale_detection():
    result = evaluate_freshness(bucket="normal", snapshot_age_ms=310000)
    assert result.is_stale is True
    assert result.reason_code == "stale_data_skip"
