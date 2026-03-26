from __future__ import annotations

from datetime import datetime, timezone
import csv
import io
import os
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from models import (
    OnboardingAmlDenylist,
    User,
    UserActivationEvent,
    UserExchangeConnection,
    UserKycDocument,
    UserOnboardingDecisionLog,
    UserOnboardingProfile,
    UserRole,
    UserStrategyScope,
)
from services.risk_policy_defaults_service import ensure_user_safe_default_risk_policy
from services.venue_service import ensure_user_venue_assignment


ALLOWED_KYC_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_KYC_DOCUMENTS = 5
AUTO_APPROVE_THRESHOLD = 35


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _blocked_regions() -> set[str]:
    raw = str(os.getenv("ONBOARDING_BLOCKED_COUNTRIES") or "").strip()
    if not raw:
        return set()
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def _normalize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def _get_user_for_onboarding(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.USER).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return user


def get_or_create_onboarding_profile(db: Session, user_id: str) -> UserOnboardingProfile:
    row = db.query(UserOnboardingProfile).filter(UserOnboardingProfile.user_id == user_id).first()
    if row:
        return row
    row = UserOnboardingProfile(user_id=user_id, email_verified=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _exchange_connections_context(db: Session, user_id: str) -> tuple[list[dict], str]:
    rows = db.query(UserExchangeConnection).filter(UserExchangeConnection.user_id == user_id).all()
    if not rows:
        return [], "invalid"

    items: list[dict] = []
    status_set: set[str] = set()
    for row in rows:
        readiness = dict(getattr(row, "readiness_snapshot", {}) or {})
        reason_codes = [str(item).lower() for item in (readiness.get("reason_codes") or [])]
        raw_valid = readiness.get("api_valid")
        if raw_valid is True:
            api_status = "valid"
        elif any("expired" in code for code in reason_codes):
            api_status = "expired"
        else:
            api_status = "invalid"
        status_set.add(api_status)
        items.append(
            {
                "connection_id": row.id,
                "exchange": row.exchange,
                "market_type": row.market_type,
                "environment": row.environment,
                "api_key_validity": api_status,
                "readiness_snapshot": readiness,
            }
        )

    if "valid" in status_set:
        aggregate = "valid"
    elif "expired" in status_set:
        aggregate = "expired"
    else:
        aggregate = "invalid"
    return items, aggregate


def _compute_aml_flag(db: Session, user: User, profile: UserOnboardingProfile) -> tuple[str, str | None]:
    if str(profile.aml_flag or "").lower() in {"blacklist", "sanction_hit"}:
        return str(profile.aml_flag), profile.aml_reason

    email_key = _normalize_email(user.email)
    deny_email = (
        db.query(OnboardingAmlDenylist)
        .filter(
            OnboardingAmlDenylist.is_active.is_(True),
            OnboardingAmlDenylist.match_type == "email",
            OnboardingAmlDenylist.match_key == email_key,
        )
        .first()
    )
    if deny_email:
        return "blacklist", str(deny_email.reason or "aml_internal_denylist")

    country = str(profile.country_code or "").strip().upper()
    if country and country in _blocked_regions():
        return "sanction_hit", "region_blocked"

    return "clear", profile.aml_reason


def _decision_engine(context: dict) -> dict:
    risk_score = float(context.get("risk_score") or 0)
    flags = list(context.get("risk_flags") or [])
    approval_disabled = bool(context.get("approval_disabled", False))

    if "aml_hit" in flags:
        return {
            "recommended_action": "force_manual_review",
            "auto_approve": False,
            "why_approving": "AML/sanction eşleşmesi bulundu; manuel inceleme zorunlu.",
            "precheck_blocked": approval_disabled,
        }

    if risk_score < AUTO_APPROVE_THRESHOLD:
        return {
            "recommended_action": "auto_approve",
            "auto_approve": True,
            "why_approving": (
                f"Risk skoru {risk_score:.2f} < {AUTO_APPROVE_THRESHOLD}; otomatik onay kriteri sağlandı."
                + (" Ancak pre-check blokajı mevcut." if approval_disabled else "")
            ),
            "precheck_blocked": approval_disabled,
        }

    return {
        "recommended_action": "force_manual_review",
        "auto_approve": False,
        "why_approving": (
            f"Risk skoru {risk_score:.2f} >= {AUTO_APPROVE_THRESHOLD}; manuel inceleme gerekli."
            + (" Pre-check blokajı da mevcut." if approval_disabled else "")
        ),
        "precheck_blocked": approval_disabled,
    }


def _decision_support_payload(context: dict) -> dict:
    risk_score = float(context.get("risk_score") or 0)
    balance = float(context.get("balance_usd") or 0)
    api_validity = str(context.get("api_key_validity") or "invalid")
    aml_flag = str(context.get("aml_flag") or "clear")

    reason_codes: list[str] = []
    if aml_flag in {"blacklist", "sanction_hit"}:
        reason_codes.append("aml_hit")
    if risk_score >= 70:
        reason_codes.append("high_risk_score")
    if api_validity != "valid":
        reason_codes.append("invalid_api")
    if balance <= 50:
        reason_codes.append("low_balance")
    if not bool(context.get("leverage_permission", False)):
        reason_codes.append("high_leverage_request")

    if "aml_hit" in reason_codes:
        recommended_action = "reject"
        confidence = 0.98
    elif risk_score < AUTO_APPROVE_THRESHOLD and not context.get("approval_disabled", False):
        recommended_action = "approve"
        confidence = 0.82
    elif risk_score >= 70:
        recommended_action = "reject"
        confidence = 0.86
    else:
        recommended_action = "manual_review"
        confidence = 0.65

    if risk_score >= 70 or "aml_hit" in reason_codes:
        auto_tag = "high-risk"
    elif risk_score < 25 and balance >= 5000:
        auto_tag = "vip"
    else:
        auto_tag = "normal"

    if reason_codes:
        summary = " + ".join(reason_codes)
    else:
        summary = "low risk baseline"

    return {
        "recommended_action": recommended_action,
        "confidence": round(float(confidence), 2),
        "reason_codes": reason_codes,
        "human_readable_summary": summary,
        "auto_tag": auto_tag,
    }


def _append_activation_event(db: Session, *, user_id: str, event_type: str, payload: dict) -> None:
    db.add(UserActivationEvent(user_id=user_id, event_type=event_type, payload=payload))


def run_post_approval_activation(db: Session, *, user: User, actor: User | None) -> dict:
    now = _now()
    actor_id = actor.id if actor else None

    _append_activation_event(
        db,
        user_id=user.id,
        event_type="user.approval.completed",
        payload={"at": now.isoformat(), "actor_user_id": actor_id},
    )

    ensure_user_safe_default_risk_policy(db, user.id, commit=False)
    _append_activation_event(
        db,
        user_id=user.id,
        event_type="user.risk.defaults_assigned",
        payload={"at": now.isoformat(), "actor_user_id": actor_id},
    )

    strategy_scope = db.query(UserStrategyScope).filter(UserStrategyScope.user_id == user.id).first()
    if strategy_scope is None:
        strategy_scope = UserStrategyScope(
            user_id=user.id,
            strategy_code="core-default",
            created_by=actor_id,
        )
        db.add(strategy_scope)
    _append_activation_event(
        db,
        user_id=user.id,
        event_type="user.strategy.default_bound",
        payload={"strategy_name": "core-default", "at": now.isoformat()},
    )

    ensure_user_venue_assignment(
        db,
        user_id=user.id,
        exchange_code="binance",
        market_type="futures",
        environment="testnet",
        commit=False,
    )
    _append_activation_event(
        db,
        user_id=user.id,
        event_type="user.activation.started",
        payload={"at": now.isoformat()},
    )
    db.commit()
    return {"events": 4, "strategy_scope": "core-default"}


def build_onboarding_context(db: Session, user_id: str) -> dict:
    user = _get_user_for_onboarding(db, user_id)
    profile = get_or_create_onboarding_profile(db, user.id)
    docs = (
        db.query(UserKycDocument)
        .filter(UserKycDocument.user_id == user.id)
        .order_by(UserKycDocument.uploaded_at.desc())
        .all()
    )

    exchange_connections, aggregate_api_validity = _exchange_connections_context(db, user.id)
    if not exchange_connections:
        profile_api_validity = str(profile.api_key_validity or "unknown").strip().lower()
        if profile_api_validity in {"valid", "invalid", "expired"}:
            aggregate_api_validity = profile_api_validity
    aml_flag, aml_reason = _compute_aml_flag(db, user, profile)
    kyc_status = str(profile.kyc_status or "pending").lower()
    risk_score = float(profile.risk_score or 0)
    balance_usd = float(profile.balance_usd or 0)
    country_code = str(profile.country_code or "").strip().upper() or None
    account_age_days = max(0, int((_now() - user.created_at).total_seconds() // 86400))

    precheck_reasons: list[str] = []
    if kyc_status != "verified":
        precheck_reasons.append("kyc_not_verified")
    if aml_flag in {"blacklist", "sanction_hit"}:
        precheck_reasons.append("aml_hit")
    if risk_score <= 0:
        precheck_reasons.append("risk_score_missing")
    if aggregate_api_validity != "valid":
        precheck_reasons.append("api_key_invalid")
    if balance_usd <= 0:
        precheck_reasons.append("balance_missing")
    if country_code and country_code in _blocked_regions():
        precheck_reasons.append("region_blocked")

    trading_eligibility = len(precheck_reasons) == 0
    risk_flags = []
    if aml_flag in {"blacklist", "sanction_hit"}:
        risk_flags.append("aml_hit")
    if aggregate_api_validity != "valid":
        risk_flags.append("invalid_api")
    if not bool(profile.leverage_permission):
        risk_flags.append("high_leverage_request")

    context = {
        "user_id": user.id,
        "email": user.email,
        "approval_status": user.approval_status,
        "account_age_days": account_age_days,
        "exchange_connections": exchange_connections,
        "api_key_validity": aggregate_api_validity,
        "balance_usd": balance_usd,
        "first_funding_at": profile.first_funding_at.isoformat() if profile.first_funding_at else None,
        "kyc_status": kyc_status,
        "kyc_documents": [
            {
                "document_id": row.id,
                "file_name": row.file_name,
                "file_type": row.file_type,
                "review_status": row.review_status,
                "review_note": row.review_note,
                "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
            }
            for row in docs
        ],
        "risk_score": risk_score,
        "aml_flag": aml_flag,
        "aml_reason": aml_reason,
        "trading_eligibility": trading_eligibility,
        "region_compliance": "restricted" if "region_blocked" in precheck_reasons else "allowed",
        "leverage_permission": bool(profile.leverage_permission),
        "futures_capability": bool(profile.futures_capability),
        "spot_capability": bool(profile.spot_capability),
        "risk_flags": risk_flags,
        "approval_disabled": not trading_eligibility,
        "approval_disable_reasons": precheck_reasons,
    }
    context["decision_engine"] = _decision_engine(context)
    context["decision_support"] = _decision_support_payload(context)
    return context


def upsert_risk_foundation(
    db: Session,
    *,
    user_id: str,
    risk_score: float,
    aml_flag: str,
    aml_reason: str | None,
    api_key_validity: str,
    balance_usd: float,
    country_code: str | None,
    leverage_permission: bool,
    futures_capability: bool,
    spot_capability: bool,
) -> UserOnboardingProfile:
    user = _get_user_for_onboarding(db, user_id)
    profile = get_or_create_onboarding_profile(db, user.id)
    profile.risk_score = max(0.0, min(100.0, float(risk_score)))
    profile.aml_flag = str(aml_flag or "clear").strip().lower()
    profile.aml_reason = (aml_reason or "").strip() or None
    profile.api_key_validity = str(api_key_validity or "unknown").strip().lower()
    profile.balance_usd = max(0.0, float(balance_usd or 0.0))
    profile.country_code = (country_code or "").strip().upper() or None
    profile.leverage_permission = bool(leverage_permission)
    profile.futures_capability = bool(futures_capability)
    profile.spot_capability = bool(spot_capability)
    if profile.balance_usd > 0 and profile.first_funding_at is None:
        profile.first_funding_at = _now()
    db.commit()
    db.refresh(profile)
    return profile


def upload_kyc_document(
    db: Session,
    *,
    user_id: str,
    upload_file: UploadFile,
    uploaded_by: User,
) -> UserKycDocument:
    user = _get_user_for_onboarding(db, user_id)
    profile = get_or_create_onboarding_profile(db, user.id)

    existing_count = db.query(UserKycDocument).filter(UserKycDocument.user_id == user.id).count()
    if existing_count >= MAX_KYC_DOCUMENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="kyc_document_limit_reached")

    original_name = str(upload_file.filename or "").strip()
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in ALLOWED_KYC_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="kyc_file_type_not_allowed")

    storage_root = Path("/tmp/kyc_documents")
    storage_root.mkdir(parents=True, exist_ok=True)
    document_id = f"{user.id}-{int(_now().timestamp())}-{existing_count + 1}"
    file_path = storage_root / f"{document_id}.{extension}"
    content = upload_file.file.read()
    with open(file_path, "wb") as handle:
        handle.write(content)

    row = UserKycDocument(
        user_id=user.id,
        file_name=original_name,
        file_type=extension,
        storage_ref=str(file_path),
        upload_status="uploaded",
        review_status="pending",
        uploaded_by=uploaded_by.id,
        document_metadata={"content_type": upload_file.content_type, "size_bytes": len(content)},
    )
    profile.kyc_status = "pending"
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def review_kyc_document(
    db: Session,
    *,
    user_id: str,
    document_id: str,
    review_status: str,
    review_note: str,
    reviewer: User,
) -> UserKycDocument:
    user = _get_user_for_onboarding(db, user_id)
    profile = get_or_create_onboarding_profile(db, user.id)
    row = (
        db.query(UserKycDocument)
        .filter(UserKycDocument.id == document_id, UserKycDocument.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kyc_document_not_found")

    normalized = str(review_status or "").strip().lower()
    if normalized not in {"approved", "rejected"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_kyc_review_status")

    row.review_status = normalized
    row.review_note = review_note
    row.reviewed_by = reviewer.id
    row.reviewed_at = _now()

    docs = db.query(UserKycDocument).filter(UserKycDocument.user_id == user.id).all()
    statuses = [str(item.review_status or "pending") for item in docs]
    if "rejected" in statuses:
        profile.kyc_status = "rejected"
    elif statuses and all(item == "approved" for item in statuses):
        profile.kyc_status = "verified"
    else:
        profile.kyc_status = "pending"

    db.commit()
    db.refresh(row)
    return row


def append_decision_log(
    db: Session,
    *,
    user_id: str,
    decision: str,
    decision_source: str,
    actor: User | None,
    reason: str,
    explanation: str,
    context_snapshot: dict,
) -> UserOnboardingDecisionLog:
    row = UserOnboardingDecisionLog(
        user_id=user_id,
        decision=decision,
        decision_source=decision_source,
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else "system",
        reason=reason,
        explanation=explanation,
        context_snapshot=context_snapshot,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _enforce_same_actor_constraint(db: Session, *, user_id: str, actor: User, target_decision: str) -> None:
    previous = (
        db.query(UserOnboardingDecisionLog)
        .filter(
            UserOnboardingDecisionLog.user_id == user_id,
            UserOnboardingDecisionLog.actor_user_id == actor.id,
            UserOnboardingDecisionLog.decision.in_(["approved", "rejected"]),
        )
        .order_by(UserOnboardingDecisionLog.created_at.desc())
        .first()
    )
    if previous and str(previous.decision) != target_decision:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="same_actor_cannot_approve_and_reject")


def execute_onboarding_decision(
    db: Session,
    *,
    user_id: str,
    actor: User,
    decision: str,
    reason: str,
    confirm_token: str,
    decision_source: str = "manual",
) -> dict:
    if str(confirm_token or "").strip().upper() != "CONFIRM":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="double_confirmation_required")
    reason_note = str(reason or "").strip()
    if len(reason_note) < 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="decision_reason_required")

    user = _get_user_for_onboarding(db, user_id)
    context = build_onboarding_context(db, user.id)
    engine = context.get("decision_engine") or {}

    normalized = str(decision or "").strip().lower()
    if normalized not in {"approve", "reject"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_decision")

    target_decision = "approved" if normalized == "approve" else "rejected"
    _enforce_same_actor_constraint(db, user_id=user.id, actor=actor, target_decision=target_decision)

    if normalized == "approve":
        if bool(context.get("approval_disabled")):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "approval_disabled", "reasons": context.get("approval_disable_reasons") or []},
            )
        user.approval_status = "approved"
        user.is_active = True
        user.approved_at = _now()
        user.disabled_at = None
    else:
        user.approval_status = "rejected"
        user.is_active = False
        user.approved_at = None
        user.disabled_at = _now()

    db.commit()
    db.refresh(user)
    activation_result = None
    if normalized == "approve":
        activation_result = run_post_approval_activation(db, user=user, actor=actor)
    log = append_decision_log(
        db,
        user_id=user.id,
        decision=target_decision,
        decision_source=decision_source,
        actor=actor,
        reason=reason_note,
        explanation=str(engine.get("why_approving") or "manual_decision"),
        context_snapshot=context,
    )
    return {
        "user_id": user.id,
        "approval_status": user.approval_status,
        "is_active": user.is_active,
        "decision_log_id": log.id,
        "decision_engine": engine,
        "decision_support": context.get("decision_support") or {},
        "activation": activation_result,
    }


def execute_auto_approve_if_eligible(db: Session, *, user_id: str, actor: User, reason: str, confirm_token: str) -> dict:
    context = build_onboarding_context(db, user_id)
    engine = context.get("decision_engine") or {}
    if str(engine.get("recommended_action")) != "auto_approve":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="manual_review_required")
    return execute_onboarding_decision(
        db,
        user_id=user_id,
        actor=actor,
        decision="approve",
        reason=reason,
        confirm_token=confirm_token,
        decision_source="auto",
    )


def export_onboarding_decision_logs_csv(db: Session, *, limit: int = 1000) -> bytes:
    rows = db.query(UserOnboardingDecisionLog).order_by(UserOnboardingDecisionLog.created_at.desc()).limit(limit).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["log_id", "user_id", "decision", "decision_source", "actor_user_id", "actor_role", "reason", "explanation", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.user_id,
                row.decision,
                row.decision_source,
                row.actor_user_id,
                row.actor_role,
                row.reason,
                row.explanation,
                row.created_at.isoformat() if row.created_at else None,
            ]
        )
    return buffer.getvalue().encode("utf-8")
