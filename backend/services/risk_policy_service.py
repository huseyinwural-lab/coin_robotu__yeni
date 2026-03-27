from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from models import User
from services.geoip_service import resolve_ip_location
from services.identity_control_service import (
    get_or_create_identity_profile,
    is_known_device,
    resolve_client_ip,
    resolve_device_fingerprint,
    resolve_ip_hash,
)

CRITICAL_ACTIONS = {
    "withdraw",
    "api_key_create",
    "api_key_delete",
    "exchange_credential_update",
    "manual_trade",
    "execute_order",
    "trade_execution",
}


def _risk_threshold_usdt() -> float:
    raw = str(os.environ.get("RISK_HIGH_AMOUNT_THRESHOLD_USDT") or "10000").strip()
    try:
        return float(raw)
    except ValueError:
        return 10000.0


@dataclass
class RiskEvaluation:
    requires_step_up: bool
    risk_level: str
    risk_reasons: list[str]
    context: dict


def _dedupe_keep_order(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def evaluate_context_risk(db: Session, *, user: User, request: Request) -> RiskEvaluation:
    profile = get_or_create_identity_profile(db, user.id, commit=False)
    snapshot = dict(profile.compliance_snapshot or {})
    security_context = dict(snapshot.get("security_context") or {})

    ip_address = resolve_client_ip(request)
    ip_hash = resolve_ip_hash(request)
    device_fingerprint = resolve_device_fingerprint(request)
    location = resolve_ip_location(ip_address)
    country_iso = str(location.get("country_iso") or "").strip().upper() or None
    known_device = is_known_device(db, user_id=user.id, device_fingerprint=device_fingerprint)

    previous_ip_hash = str(security_context.get("ip_hash") or "").strip()
    previous_country_iso = str(security_context.get("country_iso") or "").strip().upper()
    previous_device_fingerprint = str(security_context.get("device_fingerprint") or "").strip()
    has_baseline_context = bool(previous_ip_hash or previous_country_iso or previous_device_fingerprint)

    reasons: list[str] = []
    if previous_ip_hash and previous_ip_hash != ip_hash:
        reasons.append("ip_change")
    if previous_country_iso and country_iso and previous_country_iso != country_iso:
        reasons.append("country_change")
    if has_baseline_context and not known_device:
        reasons.append("new_device")

    deduped = _dedupe_keep_order(reasons)
    if not deduped:
        level = "low"
    elif "country_change" in deduped:
        level = "high"
    else:
        level = "medium"

    return RiskEvaluation(
        requires_step_up=bool(deduped),
        risk_level=level,
        risk_reasons=deduped,
        context={
            "ip_address": ip_address,
            "ip_hash": ip_hash,
            "country_iso": country_iso,
            "device_fingerprint": device_fingerprint,
            "known_device": known_device,
        },
    )


def evaluate_action_risk(*, action_name: str, amount_usdt: float | None = None) -> RiskEvaluation:
    action_key = str(action_name or "").strip().lower()
    reasons: list[str] = []

    if action_key in CRITICAL_ACTIONS:
        reasons.append("critical_action")

    threshold = _risk_threshold_usdt()
    if amount_usdt is not None and float(amount_usdt) >= threshold:
        reasons.append("high_amount")

    deduped = _dedupe_keep_order(reasons)
    if not deduped:
        level = "low"
    elif "high_amount" in deduped and "critical_action" in deduped:
        level = "high"
    elif "critical_action" in deduped:
        level = "medium"
    else:
        level = "medium"

    return RiskEvaluation(
        requires_step_up=bool(deduped),
        risk_level=level,
        risk_reasons=deduped,
        context={"action_name": action_key, "amount_usdt": amount_usdt, "threshold_usdt": threshold},
    )


def evaluate_request_risk(
    db: Session,
    *,
    user: User,
    request: Request,
    action_name: str,
    amount_usdt: float | None = None,
) -> RiskEvaluation:
    context_eval = evaluate_context_risk(db, user=user, request=request)
    action_eval = evaluate_action_risk(action_name=action_name, amount_usdt=amount_usdt)

    merged_reasons = _dedupe_keep_order([*context_eval.risk_reasons, *action_eval.risk_reasons])
    if not merged_reasons:
        level = "low"
    elif "country_change" in merged_reasons or "high_amount" in merged_reasons:
        level = "high"
    elif len(merged_reasons) >= 2:
        level = "high"
    else:
        level = "medium"

    return RiskEvaluation(
        requires_step_up=bool(merged_reasons),
        risk_level=level,
        risk_reasons=merged_reasons,
        context={
            "context": context_eval.context,
            "action": action_eval.context,
        },
    )


def standardized_risk_response(risk: RiskEvaluation) -> dict:
    return {
        "requires_step_up": bool(risk.requires_step_up),
        "risk_level": risk.risk_level,
        "risk_reasons": list(risk.risk_reasons or []),
    }
