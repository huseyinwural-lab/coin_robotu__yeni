import uuid

from services.unified_risk_core_service import (
    _append_policy_history_rows,
    get_policy_history,
    policy_decay,
    policy_leaderboard,
    policy_portfolio,
    policy_trends,
    run_policy_benchmark,
)


def test_policy_leaderboard_and_history_pipeline():
    result = run_policy_benchmark(
        db=None,
        cache=None,
        user_id="test-user",
        scenario_ids=["bear_regime_v1", "bull_regime_v1", "high_volatility_v1"],
        policy_sets=[
            {"id": "P1", "thresholds": {"var_limit": 0.055, "cluster_limit": 0.62}},
            {"id": "P2", "thresholds": {"var_limit": 0.05, "cluster_limit": 0.58}},
            {"id": "P3", "thresholds": {"var_limit": 0.045, "cluster_limit": 0.54}},
        ],
        strategy_class="trend",
        ruleset="binance",
        base_input_state=None,
        actor_id=None,
    )

    assert result["recommended_policy"]["recommended_policy"] in {"P1", "P2", "P3"}
    assert result["recommended_policy"]["variance"] >= 0.0

    leaderboard = policy_leaderboard(limit=10)
    assert leaderboard["leaderboard"]
    assert "rank" in leaderboard["leaderboard"][0]
    assert "stability" in leaderboard["leaderboard"][0]

    history = get_policy_history(policy_id="P1", limit=50)
    assert history["items"]


def test_policy_decay_detection_marks_degrading():
    policy_id = f"DECAY_TEST_{uuid.uuid4().hex[:8]}"
    _append_policy_history_rows(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "run_id": "manual", "policy_id": policy_id, "score": 0.90, "regime": "bull", "scenario": "manual", "strategy_class": "default"},
            {"timestamp": "2026-01-02T00:00:00Z", "run_id": "manual", "policy_id": policy_id, "score": 0.88, "regime": "bull", "scenario": "manual", "strategy_class": "default"},
            {"timestamp": "2026-01-03T00:00:00Z", "run_id": "manual", "policy_id": policy_id, "score": 0.55, "regime": "bear", "scenario": "manual", "strategy_class": "default"},
            {"timestamp": "2026-01-04T00:00:00Z", "run_id": "manual", "policy_id": policy_id, "score": 0.52, "regime": "bear", "scenario": "manual", "strategy_class": "default"},
        ]
    )

    decay = policy_decay(window=2, drop_threshold=0.15)
    match = next((row for row in decay["items"] if row["policy"] == policy_id), None)
    assert match is not None
    assert match["status"] == "DEGRADING"


def test_policy_portfolio_and_trend_outputs():
    portfolio = policy_portfolio(top_k=2)
    assert len(portfolio["policy_portfolio"]) >= 1
    total_weight = sum(item["weight"] for item in portfolio["policy_portfolio"])
    assert 0.99 <= total_weight <= 1.01

    trends = policy_trends()
    assert "insight" in trends
    assert "transitions" in trends
