import uuid

from services.unified_risk_core_service import jira_epic_breakdown, list_rulesets, run_unified_risk_orchestrator, simulate_pre_trade_risk


def _sample_input_state():
    return {
        "account": {
            "equity": 15000.0,
            "free_collateral": 11000.0,
            "used_margin": 4000.0,
            "portfolio_id": "sim-portfolio-001",
        },
        "positions": [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "quantity": 0.12,
                "entry_price": 65000.0,
                "mark_price": 64000.0,
                "leverage": 8,
                "margin_mode": "cross",
                "strategy_id": "trend_alpha",
            },
            {
                "symbol": "ETHUSDT",
                "side": "SHORT",
                "quantity": 1.5,
                "entry_price": 3300.0,
                "mark_price": 3360.0,
                "leverage": 6,
                "margin_mode": "isolated",
                "isolated_margin": 950.0,
                "strategy_id": "mean_reversion",
            },
        ],
        "strategy_risk_budgets": {
            "trend_alpha": 35.0,
            "mean_reversion": 25.0,
        },
    }


def test_correlation_spike_sets_cluster_high_and_state_escalates():
    input_state = _sample_input_state()
    input_state["cluster_override"] = {"correlation_spike": True}
    payload = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=input_state,
        snapshot_type="portfolio-level",
        stage="cluster-spike",
        actor_id=None,
        persist_artifact=False,
    )

    assert payload["cluster_risk"]["risk_flag"] == "HIGH"
    assert payload["global_risk_state"] in {"HIGH", "CRITICAL", "BLOCKED"}
    assert "cluster_concentration_high" in payload["explainability"]["reason"] or "cluster_concentration_critical" in payload["explainability"]["reason"]


def test_tail_shock_changes_execution_policy():
    input_state = _sample_input_state()
    input_state["tail_override"] = {"returns": [-0.22] * 80}
    payload = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=input_state,
        snapshot_type="portfolio-level",
        stage="tail-shock",
        actor_id=None,
        persist_artifact=False,
    )

    assert payload["tail_risk"]["risk_flag"] == "HIGH"
    assert payload["execution_policy"]["decision"] != "ALLOW"
    assert payload["tail_risk"]["var"] > 0
    assert payload["tail_risk"]["cvar"] > 0


def test_strategy_overload_triggers_pause_or_block():
    strategy_id = f"stress-{uuid.uuid4().hex[:8]}"
    input_state = {
        "account": {"equity": 5000.0, "free_collateral": 1500.0, "used_margin": 3500.0},
        "positions": [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "quantity": 0.2,
                "entry_price": 65000.0,
                "mark_price": 65000.0,
                "leverage": 6,
                "margin_mode": "cross",
                "strategy_id": strategy_id,
            }
        ],
        "strategy_risk_budgets": {strategy_id: 15.0},
    }
    payload = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=input_state,
        snapshot_type="portfolio-level",
        stage="strategy-overload",
        actor_id=None,
        persist_artifact=False,
    )

    actions = [row["action"] for row in payload["strategy_risk"]["actions"]]
    assert any(action in {"THROTTLE", "PAUSE", "BLOCK"} for action in actions)
    assert payload["strategy_risk"]["strategies"][0]["usage_pct"] > 100


def test_combined_scenario_hits_critical_or_blocked():
    strategy_id = f"combo-{uuid.uuid4().hex[:8]}"
    input_state = {
        "account": {"equity": 4000.0, "free_collateral": 600.0, "used_margin": 3400.0},
        "positions": [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "quantity": 0.22,
                "entry_price": 65000.0,
                "mark_price": 63200.0,
                "leverage": 10,
                "margin_mode": "cross",
                "strategy_id": strategy_id,
            },
            {
                "symbol": "SOLUSDT",
                "side": "LONG",
                "quantity": 180,
                "entry_price": 190.0,
                "mark_price": 185.0,
                "leverage": 12,
                "margin_mode": "cross",
                "strategy_id": strategy_id,
            },
        ],
        "strategy_risk_budgets": {strategy_id: 12.0},
        "cluster_override": {"correlation_spike": True},
        "tail_override": {"returns": [-0.25] * 100},
    }

    proposed_order = {
        "symbol": "ETHUSDT",
        "side": "LONG",
        "quantity": 8,
        "price": 3300.0,
        "leverage": 8,
        "margin_mode": "cross",
        "strategy_id": strategy_id,
    }
    simulation = simulate_pre_trade_risk(
        db=None,
        cache=None,
        user_id="test-user",
        proposed_order=proposed_order,
        ruleset="binance",
        actor_id=None,
    )

    payload = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=input_state,
        snapshot_type="portfolio-level",
        stage="combined-scenario",
        actor_id=None,
        persist_artifact=False,
    )

    assert payload["global_risk_state"] in {"CRITICAL", "BLOCKED"}
    assert payload["execution_policy"]["decision"] in {"BLOCK_NEW_ORDERS", "KILL_SWITCH", "PAUSE_STRATEGY", "REDUCE_RISK"}
    assert simulation["impact_delta"]["state_transition"]["after"] in {"NORMAL", "WARN", "HIGH", "CRITICAL", "BLOCKED"}
    assert "stress_sensitivity_delta" in simulation["impact_delta"]


def test_ruleset_and_jira_contract():
    rulesets = list_rulesets()
    assert rulesets["default"] == "binance"
    assert "bybit" in rulesets["available"]

    jira = jira_epic_breakdown()
    assert jira["hard_constraints"]["single_entry"] == "risk_orchestrator"
    assert jira["hard_constraints"]["no_direct_execution_binding"] is True
    assert len(jira["epics"]) >= 2
