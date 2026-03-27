from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from services.execution_policy_service import (
    append_execution_policy_decision_log,
    evaluate_execution_policy_engine,
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

    recommended_block = str(pretrade.get("recommended_action") or "ALLOW").upper() == "BLOCK"
    enforced_block = str(pretrade.get("enforced_action") or "ALLOW").upper() == "BLOCK"
    if recommended_block:
        violation_payload = {
            **pretrade,
            "recommended_action": "BLOCK",
            "enforced_action": "BLOCK" if enforced_block else "ALLOW",
        }
        append_execution_policy_decision_log(
            db,
            lifecycle_action=lifecycle,
            stage="VIOLATION",
            context=context_payload,
            policy_result=violation_payload,
            action_taken="VIOLATION_BLOCKED" if enforced_block else "VIOLATION_SOFT_LOGGED",
            is_violation=True,
        )
        stage_results.append(
            _base_stage_result(
                stage="VIOLATION",
                action="BLOCK" if enforced_block else "ALLOW",
                reason=pretrade.get("standardized_reject"),
                trace={"violation_logged": True, "rollout_mode": pretrade.get("rollout_mode")},
            )
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
        }

    execution_result = {
        "recommended_action": "ALLOW",
        "enforced_action": "ALLOW",
        "rollout_mode": pretrade.get("rollout_mode"),
        "standardized_reject": None,
        "trace": {
            "stage": "EXECUTION",
            "execution_status": "QUEUED_FOR_APPROVAL",
            "pipeline_id": pipeline_id,
        },
    }
    append_execution_policy_decision_log(
        db,
        lifecycle_action=lifecycle,
        stage="EXECUTION",
        context=context_payload,
        policy_result=execution_result,
        action_taken="EXECUTION_QUEUED",
        is_violation=False,
    )
    stage_results.append(
        _base_stage_result(
            stage="EXECUTION",
            action="ALLOW",
            trace=execution_result.get("trace") or {},
        )
    )

    post_result = {
        "recommended_action": "ALLOW",
        "enforced_action": "ALLOW",
        "rollout_mode": pretrade.get("rollout_mode"),
        "standardized_reject": None,
        "trace": {
            "stage": "POST_TRADE",
            "post_trade_status": "DECISION_LOGGED",
            "pipeline_id": pipeline_id,
        },
    }
    append_execution_policy_decision_log(
        db,
        lifecycle_action=lifecycle,
        stage="POST_TRADE",
        context=context_payload,
        policy_result=post_result,
        action_taken="POST_TRADE_LOGGED",
        is_violation=False,
    )
    stage_results.append(
        _base_stage_result(
            stage="POST_TRADE",
            action="ALLOW",
            trace=post_result.get("trace") or {},
        )
    )

    return {
        "pipeline_id": pipeline_id,
        "rollout_mode": pretrade.get("rollout_mode"),
        "recommended_action": pretrade.get("recommended_action"),
        "enforced_action": "ALLOW",
        "standardized_reject": pretrade.get("standardized_reject"),
        "policy_decision": pretrade,
        "stages": stage_results,
    }
