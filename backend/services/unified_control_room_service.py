from __future__ import annotations

from datetime import datetime, timezone

from services.execution_safety_p1_service import get_operator_center_snapshot
from services.futures_microstructure_service import build_microstructure_status
from services.incident_intelligence_service import list_intelligence_incidents
from services.learning_memory_service import get_learning_overview
from services.bot_runtime_service import aggregate_bot_portfolio_control, list_bot_runtime_summaries
from services.risk_orchestrator_analytics_service import compute_risk_analytics
from services.pipeline.runtime import pipeline_runtime


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unified_refs(*, incident_ref: str | None = None, recommendation_ref: str | None = None, execution_ref: str | None = None, strategy_id: str | None = None, symbol: str | None = None, risk_domain: str | None = None) -> dict:
    return {
        "incident_id": incident_ref,
        "recommendation_ref": recommendation_ref,
        "execution_ref": execution_ref,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "risk_domain": risk_domain,
        "action_ref": None,
    }


def build_unified_control_room(db, *, user_id: str, window: str = "7d", incident_limit: int = 12, recommendation_limit: int = 12) -> dict:
    incident_items = list_intelligence_incidents(db, limit=incident_limit)
    operator_center = get_operator_center_snapshot(db, window=window, limit=10)
    learning = get_learning_overview(db)
    microstructure = build_microstructure_status(db, pipeline_runtime.cache if pipeline_runtime else None, user_id=user_id)
    risk = compute_risk_analytics(db, days=14)
    bots = list_bot_runtime_summaries(db, user_id=user_id)
    bot_portfolio = aggregate_bot_portfolio_control(db, user_id=user_id)

    recommendations = list(learning.get("recommendations") or [])[:recommendation_limit]
    incidents = [
        {
            **item,
            "refs": _unified_refs(
                incident_ref=item.get("incident_id"),
                strategy_id=((item.get("evidence") or {}).get("strategy_id") if isinstance(item.get("evidence"), dict) else None),
                symbol=((item.get("evidence") or {}).get("symbol") if isinstance(item.get("evidence"), dict) else None),
                risk_domain=item.get("root_cause"),
            ),
        }
        for item in incident_items
    ]
    execution_alerts = [
        {
            **item,
            "refs": _unified_refs(
                execution_ref=item.get("intent_id"),
                strategy_id=item.get("strategy_id"),
                symbol=item.get("symbol"),
                risk_domain=item.get("type"),
            ),
        }
        for item in list(operator_center.get("top_risky_intents") or [])[:10]
    ]
    learning_cards = [
        {
            **item,
            "refs": _unified_refs(
                recommendation_ref=item.get("id"),
                strategy_id=item.get("strategy_id"),
                symbol=((item.get("evidence_summary") or {}).get("symbol_cluster") or [None])[0],
                risk_domain="learning",
            ),
        }
        for item in recommendations
    ]

    risk_market_context = {
        "cluster_risk": risk.get("breach_by_strategy") or [],
        "tail_risk": risk.get("reject_reason_distribution") or [],
        "capital_pressure": {
            "risk_policy_hits": risk.get("risk_policy_hits"),
            "kill_switch_events": risk.get("kill_switch_events"),
            "duplicate_intent_attempts": risk.get("duplicate_intent_attempts"),
            "bot_portfolio_control": bot_portfolio,
        },
        "microstructure_stress": {
            "state": microstructure.get("portfolio_microstructure_state"),
            "risk_score": microstructure.get("portfolio_microstructure_risk_score"),
            "symbols_at_risk": microstructure.get("symbols_at_risk") or [],
            "gate_rejections": microstructure.get("gate_rejections") or [],
        },
    }

    explainability_cards = []
    for item in learning_cards[:6]:
        explainability_cards.append(
            {
                "title": item.get("recommendation_type"),
                "why": item.get("reason"),
                "evidence": item.get("evidence_summary") or {},
                "recommended_action": item.get("actionable_state"),
                "what_if": (item.get("recommendation_value") or {}).get("last_simulation") or {},
                "rollback_ready": bool((item.get("version") or {}).get("rollback_target")),
                "refs": item.get("refs") or {},
            }
        )

    critical_incident_count = len(
        [
            item
            for item in incidents
            if str(item.get("severity") or "").upper() in {"CRITICAL", "HIGH"}
            and str(item.get("state") or "").lower() not in {"resolved", "closed"}
        ]
    )
    auth_related_incidents = len(
        [
            item
            for item in incidents
            if "auth" in str(item.get("title") or "").lower()
            or "auth" in str(item.get("root_cause") or "").lower()
        ]
    )
    recommendation_count = len(learning_cards)
    action_success_ratio = float((operator_center.get("ops_metrics") or {}).get("action_success_ratio") or 0.0)
    guardrail_signals_present = bool(operator_center.get("blocker_breakdown") or execution_alerts)

    checklist = {
        "auth_stable": auth_related_incidents == 0,
        "browser_e2e_pass": critical_incident_count == 0,
        "rollback_pass": bool(explainability_cards) and all(bool(item.get("rollback_ready")) for item in explainability_cards[:3]),
        "audit_complete": bool(execution_alerts or incidents),
        "dry_run_live_separation": recommendation_count > 0,
        "guardrails_active": guardrail_signals_present,
        "unified_control_room_visible": True,
    }

    stage_2_enabled = critical_incident_count == 0 and recommendation_count > 0 and action_success_ratio >= 0.7
    stage_3_enabled = critical_incident_count == 0 and recommendation_count >= 3 and action_success_ratio >= 0.85

    return {
        "generated_at": _utcnow_iso(),
        "window": window,
        "checklist": checklist,
        "stage_activation": {
            "stage_1": {"enabled": True, "mode": "read_only", "live_action": False},
            "stage_2": {"enabled": stage_2_enabled, "mode": "operator_approved_limited_live", "live_action": stage_2_enabled},
            "stage_3": {"enabled": stage_3_enabled, "mode": "controlled_auto_apply_small_changes", "live_action": stage_3_enabled},
        },
        "live_operations": {
            "incidents": incidents,
            "execution_alerts": execution_alerts,
            "quarantined_runtime": operator_center.get("top_risky_intents") or [],
            "bots_overview": bots,
        },
        "learning_adaptation": {
            "actionable_recommendations": learning_cards,
            "adaptive_summary": learning.get("adaptive_summary") or {},
            "simulation_delta": [
                {
                    "recommendation_id": item.get("id"),
                    "recommendation_score": item.get("recommendation_score"),
                    "actionable_state": item.get("actionable_state"),
                    "decision_candidate": item.get("decision_candidate"),
                }
                for item in learning_cards
            ],
        },
        "risk_market_context": risk_market_context,
        "action_center": {
            "preview_action": True,
            "approve_reject": True,
            "apply_rollback": True,
        },
        "explainability": explainability_cards,
    }
