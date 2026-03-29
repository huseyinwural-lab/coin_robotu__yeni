from services.unified_risk_core_service import (
    jira_epic_breakdown,
    list_rulesets,
    run_unified_risk_orchestrator,
    simulate_pre_trade_risk,
)


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


def test_unified_risk_orchestrator_core_outputs():
    payload = run_unified_risk_orchestrator(
        db=None,
        cache=None,
        user_id="test-user",
        ruleset="binance",
        input_state=_sample_input_state(),
        snapshot_type="portfolio-level",
        stage="pre-trade",
        actor_id=None,
        persist_artifact=False,
    )

    assert payload["orchestrator_contract"]["single_entry"] == "risk_orchestrator"
    assert payload["ruleset"] == "binance"
    assert len(payload["liquidation"]["positions"]) == 2
    assert "margin_ratio" in payload["liquidation"]["positions"][0]
    assert payload["global_risk_state"] in {"NORMAL", "WARN", "HIGH", "CRITICAL", "BLOCKED"}
    assert "execution_policy" in payload
    assert payload["execution_policy"]["decision"] in {
        "ALLOW",
        "ALLOW_WITH_REDUCE",
        "REDUCE_RISK",
        "BLOCK_NEW_ORDERS",
        "KILL_SWITCH",
    }


def test_pre_trade_simulation_produces_before_after_and_delta():
    proposed_order = {
        "symbol": "SOLUSDT",
        "side": "LONG",
        "quantity": 25,
        "price": 185.0,
        "leverage": 10,
        "margin_mode": "cross",
        "strategy_id": "trend_alpha",
    }
    simulation = simulate_pre_trade_risk(
        db=None,
        cache=None,
        user_id="test-user",
        proposed_order=proposed_order,
        ruleset="binance",
        actor_id=None,
    )

    assert simulation["before"]["global_risk_state"] in {"NORMAL", "WARN", "HIGH", "CRITICAL", "BLOCKED"}
    assert simulation["after"]["global_risk_state"] in {"NORMAL", "WARN", "HIGH", "CRITICAL", "BLOCKED"}
    assert "gross_exposure_delta" in simulation["impact_delta"]
    assert simulation["impact_delta"]["state_transition"]["before"] in {"NORMAL", "WARN", "HIGH", "CRITICAL", "BLOCKED"}


def test_ruleset_and_jira_contract():
    rulesets = list_rulesets()
    assert rulesets["default"] == "binance"
    assert "bybit" in rulesets["available"]

    jira = jira_epic_breakdown()
    assert jira["hard_constraints"]["single_entry"] == "risk_orchestrator"
    assert jira["hard_constraints"]["no_direct_execution_binding"] is True
    assert len(jira["epics"]) >= 2
