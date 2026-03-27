from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from services.execution_policy_service import (
    apply_portfolio_post_trade_update,
    append_execution_policy_decision_log,
    evaluate_execution_stage_enforcement,
    evaluate_execution_policy_engine,
    evaluate_post_trade_enforcement,
)


class ExecutionPipelineViolation(RuntimeError):
    def __init__(self, *, standardized_reject: dict, pipeline_result: dict):
        super().__init__(standardized_reject.get("reason_code") or "execution_pipeline_violation")
        self.standardized_reject = standardized_reject
        self.pipeline_result = pipeline_result


def _base_stage_result(*, stage: str, action: str, reason: dict | None = None, trace: dict | None = None) -> dict:
    payload = {
        "stage": stage,
        "decision": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if reason is not None:
        payload["standardized_reject"] = reason
    if trace is not None:
        payload["trace"] = trace
    return payload


def run_execution_pipeline(
    db: Session,
    *,
    lifecycle_action: str,
    context: dict,
) -> dict:
    pipeline_id = str(uuid.uuid4())
    lifecycle = str(lifecycle_action or "preview").lower()
    context_payload = {**dict(context or {}), "pipeline_id": pipeline_id}

    stage_results: list[dict] = []
    decision_path: list[dict] = []
    pretrade = evaluate_execution_policy_engine(db, context_payload, stage="PRE_TRADE")
    pretrade_action_taken = str((pretrade.get("trace") or {}).get("action_taken") or pretrade.get("enforced_action") or "ALLOW")
    pretrade_violation = bool(pretrade.get("standardized_reject"))
    append_execution_policy_decision_log(
        db,
        lifecycle_action=lifecycle,
        stage="PRE_TRADE",
        context=context_payload,
        policy_result=pretrade,
        action_taken=pretrade_action_taken,
        is_violation=pretrade_violation,
    )
    stage_results.append(
        _base_stage_result(
            stage="PRE_TRADE",
            action=str(pretrade.get("enforced_action") or "ALLOW"),
            reason=pretrade.get("standardized_reject"),
            trace=pretrade.get("trace") or {},
        )
    )
    decision_path.append(
        {
            "stage": "PRE_TRADE",
            "recommended_action": pretrade.get("recommended_action"),
            "enforced_action": pretrade.get("enforced_action"),
            "reason_code": (pretrade.get("standardized_reject") or {}).get("reason_code"),
        }
    )

    recommended_block = str(pretrade.get("recommended_action") or "ALLOW").upper() == "BLOCK"
    enforced_block = str(pretrade.get("enforced_action") or "ALLOW").upper() == "BLOCK"
    if recommended_block:
        violation_id = str(uuid.uuid4())
        violation_payload = {
            **pretrade,
            "recommended_action": "BLOCK",
            "enforced_action": "BLOCK" if enforced_block else "ALLOW",
        }
        append_execution_policy_decision_log(
            db,
            lifecycle_action=lifecycle,
            stage="VIOLATION",
            context={**context_payload, "violation_id": violation_id},
            policy_result=violation_payload,
            action_taken="VIOLATION_BLOCKED" if enforced_block else "VIOLATION_SOFT_LOGGED",
            is_violation=True,
        )
        stage_results.append(
            _base_stage_result(
                stage="VIOLATION",
                action="BLOCK" if enforced_block else "ALLOW",
                reason={
                    **dict(pretrade.get("standardized_reject") or {}),
                    "violation_id": violation_id,
                },
                trace={"violation_logged": True, "rollout_mode": pretrade.get("rollout_mode")},
            )
        )
        decision_path.append(
            {
                "stage": "VIOLATION",
                "recommended_action": "BLOCK",
                "enforced_action": "BLOCK" if enforced_block else "ALLOW",
                "reason_code": (pretrade.get("standardized_reject") or {}).get("reason_code"),
            }
        )

    if enforced_block:
        return {
            "pipeline_id": pipeline_id,
            "rollout_mode": pretrade.get("rollout_mode"),
            "recommended_action": pretrade.get("recommended_action"),
            "enforced_action": "BLOCK",
            "standardized_reject": pretrade.get("standardized_reject"),
            "policy_decision": pretrade,
            "stages": stage_results,
            "decision_trace": {
                "matched_policies": (pretrade.get("trace") or {}).get("matched_policies") or [],
                "applied_overrides": (pretrade.get("trace") or {}).get("applied_overrides") or [],
                "final_decision_path": decision_path,
            },
        }

    if lifecycle == "preview":
        return {
            "pipeline_id": pipeline_id,
            "rollout_mode": pretrade.get("rollout_mode"),
            "recommended_action": pretrade.get("recommended_action"),
            "enforced_action": "ALLOW",
            "standardized_reject": pretrade.get("standardized_reject"),
            "policy_decision": pretrade,
            "stages": stage_results,
            "decision_trace": {
                "matched_policies": (pretrade.get("trace") or {}).get("matched_policies") or [],
                "applied_overrides": (pretrade.get("trace") or {}).get("applied_overrides") or [],
                "final_decision_path": decision_path,
            },
        }

    execution_result = evaluate_execution_stage_enforcement(
        context=context_payload,
        effective_rules=pretrade.get("effective_rules") or {},
        rollout_mode=str(pretrade.get("rollout_mode") or "shadow"),
    )
    execution_violation = bool(execution_result.get("standardized_reject"))
    execution_action_taken = str((execution_result.get("trace") or {}).get("action_taken") or "ACCEPT")
    append_execution_policy_decision_log(
        db,
        lifecycle_action=lifecycle,
        stage="EXECUTION",
        context=context_payload,
        policy_result=execution_result,
        action_taken=execution_action_taken,
        is_violation=execution_violation,
    )
    stage_results.append(
        _base_stage_result(
            stage="EXECUTION",
            action=str(execution_result.get("enforced_action") or "ALLOW"),
            reason=execution_result.get("standardized_reject"),
            trace=execution_result.get("trace") or {},
        )
    )
    decision_path.append(
        {
            "stage": "EXECUTION",
            "recommended_action": execution_result.get("recommended_action"),
            "enforced_action": execution_result.get("enforced_action"),
            "reason_code": (execution_result.get("standardized_reject") or {}).get("reason_code"),
        }
    )

    if str(execution_result.get("enforced_action") or "ALLOW").upper() == "BLOCK":
        violation_id = str(uuid.uuid4())
        append_execution_policy_decision_log(
            db,
            lifecycle_action=lifecycle,
            stage="VIOLATION",
            context={**context_payload, "violation_id": violation_id},
            policy_result=execution_result,
            action_taken=str((execution_result.get("trace") or {}).get("action_taken") or "HARD_BLOCK"),
            is_violation=True,
        )
        stage_results.append(
            _base_stage_result(
                stage="VIOLATION",
                action="BLOCK",
                reason={
                    **dict(execution_result.get("standardized_reject") or {}),
                    "violation_id": violation_id,
                },
                trace={"violation_logged": True, "source_stage": "EXECUTION"},
            )
        )
        decision_path.append(
            {
                "stage": "VIOLATION",
                "recommended_action": "BLOCK",
                "enforced_action": "BLOCK",
                "reason_code": (execution_result.get("standardized_reject") or {}).get("reason_code"),
            }
        )
        return {
            "pipeline_id": pipeline_id,
            "rollout_mode": pretrade.get("rollout_mode"),
            "recommended_action": "BLOCK",
            "enforced_action": "BLOCK",
            "standardized_reject": execution_result.get("standardized_reject"),
            "policy_decision": pretrade,
            "stages": stage_results,
            "decision_trace": {
                "matched_policies": (pretrade.get("trace") or {}).get("matched_policies") or [],
                "applied_overrides": (pretrade.get("trace") or {}).get("applied_overrides") or [],
                "final_decision_path": decision_path,
            },
        }

    post_result = evaluate_post_trade_enforcement(
        context=context_payload,
        effective_rules=pretrade.get("effective_rules") or {},
        risk_reference=(pretrade.get("trace") or {}).get("risk") or {},
        rollout_mode=str(pretrade.get("rollout_mode") or "shadow"),
    )
    post_action_taken = str((post_result.get("trace") or {}).get("action_taken") or "WARN")
    post_violation = bool(post_result.get("standardized_reject"))
    append_execution_policy_decision_log(
        db,
        lifecycle_action=lifecycle,
        stage="POST_TRADE",
        context=context_payload,
        policy_result=post_result,
        action_taken=post_action_taken,
        is_violation=post_violation,
    )
    stage_results.append(
        _base_stage_result(
            stage="POST_TRADE",
            action=str(post_result.get("enforced_action") or "ALLOW"),
            reason=post_result.get("standardized_reject"),
            trace=post_result.get("trace") or {},
        )
    )
    decision_path.append(
        {
            "stage": "POST_TRADE",
            "recommended_action": post_result.get("recommended_action"),
            "enforced_action": post_result.get("enforced_action"),
            "reason_code": (post_result.get("standardized_reject") or {}).get("reason_code"),
        }
    )

    if post_violation:
        violation_id = str(uuid.uuid4())
        append_execution_policy_decision_log(
            db,
            lifecycle_action=lifecycle,
            stage="VIOLATION",
            context={**context_payload, "violation_id": violation_id},
            policy_result=post_result,
            action_taken=post_action_taken,
            is_violation=True,
        )
        stage_results.append(
            _base_stage_result(
                stage="VIOLATION",
                action="ALLOW",
                reason={
                    **dict(post_result.get("standardized_reject") or {}),
                    "violation_id": violation_id,
                },
                trace={"violation_logged": True, "source_stage": "POST_TRADE", "action": post_action_taken},
            )
        )
        decision_path.append(
            {
                "stage": "VIOLATION",
                "recommended_action": post_result.get("recommended_action"),
                "enforced_action": post_result.get("enforced_action"),
                "reason_code": (post_result.get("standardized_reject") or {}).get("reason_code"),
            }
        )

    apply_portfolio_post_trade_update(
        db,
        context=context_payload,
        post_trade_metrics=post_result.get("metrics_snapshot") or {},
    )

    final_reject = (
        execution_result.get("standardized_reject")
        or post_result.get("standardized_reject")
        or pretrade.get("standardized_reject")
    )
    final_recommended = "ALLOW"
    if str(pretrade.get("recommended_action") or "ALLOW").upper() == "BLOCK":
        final_recommended = "BLOCK"
    if str(execution_result.get("recommended_action") or "ALLOW").upper() == "BLOCK":
        final_recommended = "BLOCK"
    if str(post_result.get("recommended_action") or "ALLOW").upper() == "BLOCK":
        final_recommended = "BLOCK"

    return {
        "pipeline_id": pipeline_id,
        "rollout_mode": pretrade.get("rollout_mode"),
        "recommended_action": final_recommended,
        "enforced_action": "ALLOW",
        "standardized_reject": final_reject,
        "policy_decision": pretrade,
        "stages": stage_results,
        "decision_trace": {
            "matched_policies": (pretrade.get("trace") or {}).get("matched_policies") or [],
            "applied_overrides": (pretrade.get("trace") or {}).get("applied_overrides") or [],
            "final_decision_path": decision_path,
        },
    }
