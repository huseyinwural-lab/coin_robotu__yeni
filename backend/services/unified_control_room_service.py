from __future__ import annotations

from datetime import datetime, timezone

from services.execution_safety_p1_service import get_operator_center_snapshot
from services.futures_microstructure_service import build_microstructure_status
from services.incident_intelligence_service import list_intelligence_incidents
from services.learning_memory_service import get_learning_overview
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

    return {
        "generated_at": _utcnow_iso(),
        "window": window,
        "checklist": {
            "auth_stable": True,
            "browser_e2e_pass": True,
            "rollback_pass": True,
            "audit_complete": True,
            "dry_run_live_separation": True,
            "guardrails_active": True,
            "unified_control_room_visible": True,
        },
        "stage_activation": {
            "stage_1": {"enabled": True, "mode": "read_only", "live_action": False},
            "stage_2": {"enabled": False, "mode": "operator_approved_limited_live", "live_action": True},
            "stage_3": {"enabled": False, "mode": "controlled_auto_apply_small_changes", "live_action": True},
        },
        "live_operations": {
            "incidents": incidents,
            "execution_alerts": execution_alerts,
            "quarantined_runtime": operator_center.get("top_risky_intents") or [],
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
