from services.unified_risk_core_service import (
    calibrate_thresholds,
    get_calibrated_thresholds,
    get_scenario_pack_library,
    run_replay_timeline,
    run_unified_risk_orchestrator,
    upsert_scenario_pack,
)


def _extreme_input_state():
    return {
        "account": {"equity": 3000.0, "free_collateral": 200.0, "used_margin": 2800.0},
        "positions": [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "quantity": 0.18,
                "entry_price": 65000.0,
                "mark_price": 62000.0,
                "leverage": 12,
                "margin_mode": "cross",
                "strategy_id": "risk-heavy",
            },
            {
                "symbol": "SOLUSDT",
                "side": "LONG",
                "quantity": 160,
                "entry_price": 190.0,
                "mark_price": 175.0,
                "leverage": 15,
                "margin_mode": "cross",
                "strategy_id": "risk-heavy",
            },
        ],
        "strategy_risk_budgets": {"risk-heavy": 10.0},
        "cluster_override": {"correlation_spike": True},
        "tail_override": {"returns": [-0.24] * 100},
    }


def test_multifactor_kill_switch_matrix_triggers():
    payload = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=_extreme_input_state(),
        stage="kill-matrix",
        persist_artifact=False,
        actor_id=None,
        use_calibrated_thresholds=False,
    )
    assert payload["kill_switch"]["triggered"] is True
    assert payload["kill_switch"]["level"] in {"CRITICAL", "BLOCKED"}
    assert payload["global_risk_state"] in {"CRITICAL", "BLOCKED"}


def test_scenario_pack_reusable_and_deterministic():
    upsert_scenario_pack(
        {
            "scenario_id": "pytest_bear_deterministic",
            "description": "deterministic bear shock",
            "shocks": {"BTC": -0.2, "ALT": -0.3, "correlation": 0.85, "liquidity": -0.1},
        }
    )
    library = get_scenario_pack_library()
    assert any(item.get("scenario_id") == "pytest_bear_deterministic" for item in library.get("scenarios") or [])

    base_input = {
        "account": {"equity": 10000.0, "free_collateral": 8000.0, "used_margin": 2000.0},
        "positions": [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "quantity": 0.1,
                "entry_price": 65000.0,
                "mark_price": 65000.0,
                "leverage": 8,
                "margin_mode": "cross",
                "strategy_id": "default",
            }
        ],
        "strategy_risk_budgets": {"default": 25.0},
    }

    run1 = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=base_input,
        scenario_id="pytest_bear_deterministic",
        stage="scenario-run-1",
        persist_artifact=False,
        actor_id=None,
        use_calibrated_thresholds=False,
    )
    run2 = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=base_input,
        scenario_id="pytest_bear_deterministic",
        stage="scenario-run-2",
        persist_artifact=False,
        actor_id=None,
        use_calibrated_thresholds=False,
    )

    assert run1["global_risk_state"] == run2["global_risk_state"]
    assert run1["tail_risk"]["var"] == run2["tail_risk"]["var"]


def test_calibration_engine_produces_thresholds():
    result = calibrate_thresholds(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        actor_id=None,
    )
    thresholds = result["calibrated_thresholds"]
    assert "var_limit" in thresholds
    assert "cluster_limit" in thresholds
    assert "margin_high_limit" in thresholds
    persisted = get_calibrated_thresholds()
    assert persisted["var_limit"] == thresholds["var_limit"]


def test_replay_timeline_and_hysteresis_guard():
    steps = [
        {
            "stage": "t0-spike",
            "input_state": _extreme_input_state(),
        },
        {
            "stage": "t1-cooldown",
            "input_state": {
                "account": {"equity": 3000.0, "free_collateral": 900.0, "used_margin": 2100.0},
                "positions": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "LONG",
                        "quantity": 0.05,
                        "entry_price": 65000.0,
                        "mark_price": 64900.0,
                        "leverage": 6,
                        "margin_mode": "cross",
                        "strategy_id": "risk-heavy",
                    }
                ],
                "strategy_risk_budgets": {"risk-heavy": 35.0},
            },
        },
    ]
    replay = run_replay_timeline(
        db=None,
        cache=None,
        user_id="test-user",
        steps=steps,
        ruleset="binance",
        actor_id=None,
        use_calibrated_thresholds=False,
    )
    assert len(replay["timeline"]) == 2
    assert replay["timeline"][0]["risk_state"] in {"HIGH", "CRITICAL", "BLOCKED"}
    assert replay["timeline"][1]["risk_state"] in {"WARN", "HIGH", "CRITICAL", "BLOCKED"}


def test_explainability_root_cause_chain_present():
    payload = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=_extreme_input_state(),
        stage="root-cause",
        persist_artifact=False,
        actor_id=None,
        use_calibrated_thresholds=False,
    )
    explainability = payload["explainability"]
    assert isinstance(explainability.get("root_cause"), str)
    assert isinstance(explainability.get("chain"), list)
    assert explainability["chain"]
