from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import User
from schemas import (
    OnboardingContextResponse,
    OnboardingDecisionRequest,
    OnboardingDecisionResponse,
    OnboardingKycReviewRequest,
    OnboardingRiskFoundationRequest,
    OnboardingWorkflowAssignRequest,
    OnboardingWorkflowStartRequest,
    OnboardingWorkflowStepCompleteRequest,
)
from services.audit_service import create_audit_log
from services.onboarding_approval_service import (
    build_onboarding_context,
    execute_auto_approve_if_eligible,
    execute_onboarding_decision,
    export_onboarding_decision_logs_csv,
    review_kyc_document,
    upload_kyc_document,
    upsert_risk_foundation,
)
from services.onboarding_workflow_service import (
    assign_workflow_owner,
    complete_workflow_step,
    escalate_timed_out_cases,
    get_workflow_case,
    list_priority_queue,
    start_workflow_case,
)

router = APIRouter(prefix="/admin/onboarding", tags=["admin-onboarding"])
audit_router = APIRouter(prefix="/admin/audit", tags=["admin-onboarding-audit"])


@router.get("/{user_id}/context", response_model=OnboardingContextResponse)
def get_onboarding_context(user_id: str, db: Session = Depends(get_db), admin_user: User = Depends(require_admin)):
    payload = build_onboarding_context(db, user_id)
    create_audit_log(
        db,
        action="onboarding_context_view",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=admin_user.id,
        actor_role=admin_user.role.value,
        details={"approval_disabled": payload.get("approval_disabled", False)},
    )
    return payload


@router.get("/{user_id}/decision-support")
def get_onboarding_decision_support(user_id: str, db: Session = Depends(get_db), admin_user: User = Depends(require_admin)):
    payload = build_onboarding_context(db, user_id)
    return {
        "user_id": user_id,
        "decision_support": payload.get("decision_support") or {},
        "decision_engine": payload.get("decision_engine") or {},
    }


@router.post("/{user_id}/workflow/start")
def start_onboarding_workflow(
    user_id: str,
    payload: OnboardingWorkflowStartRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    case = start_workflow_case(db, user_id=user_id, assigned_admin_id=payload.assigned_admin_id, actor=admin_user)
    return {
        "workflow_case_id": case.id,
        "current_step": case.current_step,
        "assigned_admin_id": case.assigned_admin_id,
        "priority_score": case.priority_score,
        "sla_due_at": case.sla_due_at.isoformat() if case.sla_due_at else None,
    }


@router.get("/{user_id}/workflow")
def get_onboarding_workflow(user_id: str, db: Session = Depends(get_db), admin_user: User = Depends(require_admin)):
    case = get_workflow_case(db, user_id)
    if case is None:
        return {"workflow_case": None}
    return {
        "workflow_case": {
            "workflow_case_id": case.id,
            "workflow_status": case.workflow_status,
            "current_step": case.current_step,
            "assigned_admin_id": case.assigned_admin_id,
            "priority_score": case.priority_score,
            "sla_due_at": case.sla_due_at.isoformat() if case.sla_due_at else None,
            "escalated_at": case.escalated_at.isoformat() if case.escalated_at else None,
            "supervisor_queue": case.supervisor_queue,
        }
    }


@router.post("/{user_id}/workflow/assign")
def assign_onboarding_workflow(
    user_id: str,
    payload: OnboardingWorkflowAssignRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    case = assign_workflow_owner(db, user_id=user_id, assigned_admin_id=payload.assigned_admin_id, actor=admin_user)
    return {
        "workflow_case_id": case.id,
        "assigned_admin_id": case.assigned_admin_id,
        "supervisor_queue": case.supervisor_queue,
    }


@router.post("/{user_id}/workflow/steps/{step_name}/complete")
def complete_onboarding_step(
    user_id: str,
    step_name: str,
    payload: OnboardingWorkflowStepCompleteRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    case = complete_workflow_step(
        db,
        user_id=user_id,
        step_name=step_name,
        actor=admin_user,
        note=payload.note,
    )
    return {
        "workflow_case_id": case.id,
        "workflow_status": case.workflow_status,
        "current_step": case.current_step,
        "sla_due_at": case.sla_due_at.isoformat() if case.sla_due_at else None,
    }


@router.get("/workflow/queue")
def list_onboarding_priority_queue(
    assigned_admin_id: str | None = None,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    return {"items": list_priority_queue(db, assigned_admin_id=assigned_admin_id)}


@router.post("/workflow/escalate-timeouts")
def escalate_onboarding_timeouts(
    payload: dict,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    supervisor_admin_id = payload.get("supervisor_admin_id")
    result = escalate_timed_out_cases(db, actor=admin_user, supervisor_admin_id=supervisor_admin_id)
    return result


@router.post("/{user_id}/risk-foundation", response_model=OnboardingContextResponse)
def update_risk_foundation(
    user_id: str,
    payload: OnboardingRiskFoundationRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    upsert_risk_foundation(
        db,
        user_id=user_id,
        risk_score=payload.risk_score,
        aml_flag=payload.aml_flag,
        aml_reason=payload.aml_reason,
        api_key_validity=payload.api_key_validity,
        balance_usd=payload.balance_usd,
        country_code=payload.country_code,
        leverage_permission=payload.leverage_permission,
        futures_capability=payload.futures_capability,
        spot_capability=payload.spot_capability,
    )
    context = build_onboarding_context(db, user_id)
    create_audit_log(
        db,
        action="onboarding_risk_foundation_update",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=admin_user.id,
        actor_role=admin_user.role.value,
        details={
            "risk_score": payload.risk_score,
            "aml_flag": payload.aml_flag,
            "api_key_validity": payload.api_key_validity,
        },
    )
    return context


@router.post("/{user_id}/kyc-documents")
def upload_onboarding_kyc_document(
    user_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    row = upload_kyc_document(db, user_id=user_id, upload_file=file, uploaded_by=admin_user)
    context = build_onboarding_context(db, user_id)
    create_audit_log(
        db,
        action="onboarding_kyc_document_upload",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=admin_user.id,
        actor_role=admin_user.role.value,
        details={"document_id": row.id, "file_type": row.file_type},
    )
    return {
        "document_id": row.id,
        "review_status": row.review_status,
        "kyc_status": context.get("kyc_status"),
        "context": context,
    }


@router.post("/{user_id}/kyc-documents/{document_id}/review")
def review_onboarding_kyc_document(
    user_id: str,
    document_id: str,
    payload: OnboardingKycReviewRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    row = review_kyc_document(
        db,
        user_id=user_id,
        document_id=document_id,
        review_status=payload.review_status,
        review_note=payload.review_note,
        reviewer=admin_user,
    )
    context = build_onboarding_context(db, user_id)
    create_audit_log(
        db,
        action="onboarding_kyc_document_review",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=admin_user.id,
        actor_role=admin_user.role.value,
        details={
            "document_id": row.id,
            "review_status": row.review_status,
            "kyc_status": context.get("kyc_status"),
        },
    )
    return {
        "document_id": row.id,
        "review_status": row.review_status,
        "kyc_status": context.get("kyc_status"),
        "context": context,
    }


@router.post("/{user_id}/decision", response_model=OnboardingDecisionResponse)
def make_onboarding_decision(
    user_id: str,
    payload: OnboardingDecisionRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    result = execute_onboarding_decision(
        db,
        user_id=user_id,
        actor=admin_user,
        decision=payload.decision,
        reason=payload.reason,
        confirm_token=payload.confirm_token,
        decision_source="manual",
    )
    create_audit_log(
        db,
        action="onboarding_manual_decision",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=admin_user.id,
        actor_role=admin_user.role.value,
        details={"decision": payload.decision, "decision_log_id": result.get("decision_log_id")},
    )
    return result


@router.post("/{user_id}/decision/auto-approve", response_model=OnboardingDecisionResponse)
def auto_approve_onboarding_decision(
    user_id: str,
    payload: OnboardingDecisionRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    result = execute_auto_approve_if_eligible(
        db,
        user_id=user_id,
        actor=admin_user,
        reason=payload.reason,
        confirm_token=payload.confirm_token,
    )
    create_audit_log(
        db,
        action="onboarding_auto_decision",
        entity_type="user",
        entity_id=user_id,
        actor_user_id=admin_user.id,
        actor_role=admin_user.role.value,
        details={"decision_log_id": result.get("decision_log_id")},
    )
    return result


@audit_router.get("/export")
def export_onboarding_audit_csv(db: Session = Depends(get_db), admin_user: User = Depends(require_admin)):
    payload = export_onboarding_decision_logs_csv(db)
    create_audit_log(
        db,
        action="onboarding_audit_export",
        entity_type="audit",
        entity_id="user_onboarding_decision_logs",
        actor_user_id=admin_user.id,
        actor_role=admin_user.role.value,
        details={"format": "csv"},
    )
    return Response(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=onboarding_decision_audit.csv"},
    )
