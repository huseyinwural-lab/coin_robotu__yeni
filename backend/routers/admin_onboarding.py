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
