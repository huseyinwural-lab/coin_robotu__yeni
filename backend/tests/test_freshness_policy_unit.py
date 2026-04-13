# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.freshness_policy import (
    FreshnessDecision,
    evaluate_freshness,
    resolve_sla_bucket,
    threshold_ms_for_bucket,
)


class TestResolveSLABucket:
    def test_default_is_normal(self):
        bucket = resolve_sla_bucket(
            symbol_selection_mode="all_market_symbols",
            fallback_active=False,
            max_results=50,
        )
        assert bucket == "normal"

    def test_fallback_active_returns_high(self):
        bucket = resolve_sla_bucket(
            symbol_selection_mode="all_market_symbols",
            fallback_active=True,
            max_results=50,
        )
        assert bucket == "high"

    def test_top_volume_mode_returns_high(self):
        bucket = resolve_sla_bucket(
            symbol_selection_mode="top_volume",
            fallback_active=False,
            max_results=50,
        )
        assert bucket == "high"

    def test_large_max_results_returns_low(self):
        bucket = resolve_sla_bucket(
            symbol_selection_mode="all_market_symbols",
            fallback_active=False,
            max_results=200,
        )
        assert bucket == "low"

    def test_above_200_returns_low(self):
        bucket = resolve_sla_bucket(
            symbol_selection_mode="custom",
            fallback_active=False,
            max_results=500,
        )
        assert bucket == "low"

    def test_199_results_returns_normal(self):
        bucket = resolve_sla_bucket(
            symbol_selection_mode="custom",
            fallback_active=False,
            max_results=199,
        )
        assert bucket == "normal"

    def test_fallback_takes_priority_over_large_results(self):
        bucket = resolve_sla_bucket(
            symbol_selection_mode="custom",
            fallback_active=True,
            max_results=500,
        )
        assert bucket == "high"


class TestThresholdMsForBucket:
    def test_high_bucket(self):
        assert threshold_ms_for_bucket("high") == 180_000

    def test_normal_bucket(self):
        assert threshold_ms_for_bucket("normal") == 300_000

    def test_low_bucket(self):
        assert threshold_ms_for_bucket("low") == 900_000

    def test_unknown_bucket_defaults_to_normal(self):
        assert threshold_ms_for_bucket("unknown") == 300_000


class TestEvaluateFreshness:
    def test_fresh_data(self):
        result = evaluate_freshness(bucket="normal", snapshot_age_ms=100_000)
        assert isinstance(result, FreshnessDecision)
        assert result.is_stale is False
        assert result.reason_code is None

    def test_stale_data(self):
        result = evaluate_freshness(bucket="normal", snapshot_age_ms=500_000)
        assert result.is_stale is True
        assert result.reason_code == "stale_data_skip"

    def test_exactly_at_threshold(self):
        # At exactly the threshold, not stale (> not >=)
        result = evaluate_freshness(bucket="normal", snapshot_age_ms=300_000)
        assert result.is_stale is False

    def test_just_above_threshold(self):
        result = evaluate_freshness(bucket="normal", snapshot_age_ms=300_001)
        assert result.is_stale is True

    def test_high_bucket_stale(self):
        result = evaluate_freshness(bucket="high", snapshot_age_ms=200_000)
        assert result.is_stale is True

    def test_zero_age(self):
        result = evaluate_freshness(bucket="high", snapshot_age_ms=0)
        assert result.is_stale is False

    def test_none_age_treated_as_zero(self):
        result = evaluate_freshness(bucket="high", snapshot_age_ms=None)
        assert result.is_stale is False
        assert result.snapshot_age_ms == 0.0

    def test_result_fields(self):
        result = evaluate_freshness(bucket="low", snapshot_age_ms=1000)
        assert result.bucket == "low"
        assert result.threshold_ms == 900_000
        assert result.snapshot_age_ms == 1000.0
