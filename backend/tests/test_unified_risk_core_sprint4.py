from services.unified_risk_core_service import (
    _save_calibrated_thresholds,
    benchmark_compare,
    benchmark_report,
    drift_status,
    run_policy_benchmark,
)


def test_policy_benchmark_runner_selects_best_policy():
    result = run_policy_benchmark(
        db=None,
        cache=None,
        user_id="test-user",
        scenario_ids=["bear_regime_v1", "bull_regime_v1", "high_volatility_v1"],
        policy_sets=[
            {"id": "A", "thresholds": {"var_limit": 0.06, "cluster_limit": 0.65, "margin_high_limit": 70}},
            {"id": "B", "thresholds": {"var_limit": 0.05, "cluster_limit": 0.60, "margin_high_limit": 65}},
            {"id": "C", "thresholds": {"var_limit": 0.045, "cluster_limit": 0.55, "margin_high_limit": 60}},
        ],
        strategy_class="trend",
        ruleset="binance",
        base_input_state=None,
        actor_id=None,
    )

    assert result["best_policy"] in {"A", "B", "C"}
    assert len(result["policies"]) == 3
    assert result["recommended_policy"]["recommended_policy"] in {"A", "B", "C"}
    assert result["recommended_policy"]["auto_apply"] is False
    assert result["scenarios"]


def test_benchmark_report_and_compare_outputs():
    run = run_policy_benchmark(
        db=None,
        cache=None,
        user_id="test-user",
        scenario_ids=["bear_regime_v1", "sideways_regime_v1"],
        policy_sets=[
            {"id": "A", "thresholds": {"var_limit": 0.06, "cluster_limit": 0.65}},
            {"id": "B", "thresholds": {"var_limit": 0.05, "cluster_limit": 0.60}},
        ],
        strategy_class="default",
        ruleset="binance",
        base_input_state=None,
        actor_id=None,
    )
    run_id = run["run_id"]

    report = benchmark_report(run_id)
    assert report["best_policy"]["id"] in {"A", "B"}
    assert isinstance(report["insights"], list)

    comparison = benchmark_compare(run_id, "A", "B")
    assert comparison["left"]["id"] == "A"
    assert comparison["right"]["id"] == "B"
    assert "delta_score" in comparison


def test_drift_monitor_detects_threshold_shift():
    _save_calibrated_thresholds(
        {
            "var_limit": 0.085,
            "cluster_limit": 0.78,
            "margin_high_limit": 92.0,
            "margin_critical_limit": 96.0,
            "margin_blocked_limit": 98.0,
        },
        source="pytest_drift",
        metadata={"reason": "force drift"},
    )

    status = drift_status(tolerance_pct=5.0)
    assert status["drift"]["detected"] is True
    assert status["drift"]["metric"] in {"var_limit", "cluster_limit", "margin_high_limit", "kill_switch_frequency"}
    assert status["threshold_drifts"]
