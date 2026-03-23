from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import AuditLog, BrandSetting, ReleaseGateOverride
from services.audit_service import create_audit_log
from services.prod_config_remediation_service import build_prod_config_remediation_state

PRODUCTION_GATE_METADATA_KEY = "production_gate_control"
PRODUCTION_GATE_ENTITY_TYPE = "production_gate"
PRODUCTION_GATE_STATES = {"NO_GO", "GO", "GO_WITH_OVERRIDE"}
OVERRIDE_REASON_CODES = {
    "INCIDENT_MITIGATION",
    "THIRD_PARTY_DEGRADATION",
    "HOTFIX_VALIDATED",
    "MANUAL_RISK_ACCEPTANCE",
}
CHECK_STALE_MINUTES = 10

DEFAULT_CHECKLIST = [
    {"item_key": "change_window_confirmed", "title": "Change window confirmed", "required": True},
    {"item_key": "rollback_plan_verified", "title": "Rollback plan verified", "required": True},
    {"item_key": "oncall_ready", "title": "On-call owner ready", "required": True},
    {"item_key": "stakeholder_communication_ready", "title": "Stakeholder communication ready", "required": True},
]

CHECK_REMEDIATION = {
    "prod_env_resolution": "Prod env çözüm raporunu tekrar çalıştırın ve eksik değerleri düzeltin.",
    "secret_readiness": "Eksik secret değerlerini tamamlayıp secret readiness kontrolünü yeniden çalıştırın.",
    "prod_env_preflight": "Preflight FAIL maddelerini düzeltip yeniden doğrulayın.",
    "final_release_gate": "Final release gate NO_GO nedenlerini giderin ve tekrar çalıştırın.",
    "release_gate_contract": "Release gate BLOCKED reason_code listesindeki blokajları kapatın.",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _get_or_create_brand_setting(db: Session) -> BrandSetting:
    brand = db.query(BrandSetting).filter(BrandSetting.id == "default").first()
    if brand is None:
        brand = BrandSetting(id="default", metadata_json={})
        db.add(brand)
        db.commit()
        db.refresh(brand)
    return brand


def _normalize_checklist(raw_items: list[dict] | None) -> list[dict]:
    existing = {str(item.get("item_key") or ""): dict(item or {}) for item in list(raw_items or [])}
    normalized: list[dict] = []
    for template in DEFAULT_CHECKLIST:
        key = template["item_key"]
        prev = existing.get(key) or {}
        normalized.append(
            {
                "item_key": key,
                "title": template["title"],
                "required": bool(template.get("required", True)),
                "checked": bool(prev.get("checked", False)),
                "updated_at": prev.get("updated_at"),
                "updated_by_user_id": prev.get("updated_by_user_id"),
            }
        )
    return normalized


def _normalize_store(raw_store: dict | None) -> dict:
    now_iso = _iso(_utcnow())
    store = dict(raw_store or {})
    configured_state = str(store.get("state") or "NO_GO").strip().upper()
    if configured_state not in PRODUCTION_GATE_STATES:
        configured_state = "NO_GO"
    normalized = {
        "state": configured_state,
        "checklist": _normalize_checklist(store.get("checklist") if isinstance(store.get("checklist"), list) else []),
        "checks": list(store.get("checks") or []),
        "override": dict(store.get("override") or {}) if store.get("override") else None,
        "updated_at": store.get("updated_at") or now_iso,
        "updated_by_user_id": store.get("updated_by_user_id"),
        "last_transition": dict(store.get("last_transition") or {}),
    }
    return normalized


def _load_store(db: Session) -> dict:
    brand = _get_or_create_brand_setting(db)
    metadata = dict(brand.metadata_json or {})
    return _normalize_store(metadata.get(PRODUCTION_GATE_METADATA_KEY) or {})


def _persist_store(db: Session, *, store: dict, actor_user_id: str | None) -> dict:
    brand = _get_or_create_brand_setting(db)
    metadata = dict(brand.metadata_json or {})
    normalized = _normalize_store(store)
    metadata[PRODUCTION_GATE_METADATA_KEY] = normalized
    brand.metadata_json = metadata
    brand.updated_by_user_id = actor_user_id
    db.commit()
    db.refresh(brand)
    return normalized


def _check_remediation_text(check_key: str) -> str:
    return CHECK_REMEDIATION.get(check_key, "Check FAIL nedenini giderin ve rerun ile yeniden doğrulayın.")


def _build_checks_from_remediation(remediation_state: dict) -> list[dict]:
    now_iso = _iso(_utcnow())
    checks: list[dict] = []
    for check in list(remediation_state.get("checks") or []):
        key = str(check.get("check_name") or "unknown_check").strip().lower()
        raw_status = str(check.get("status") or "UNKNOWN").strip().upper()
        status_value = "PASS" if raw_status == "PASS" else "FAIL" if raw_status == "FAIL" else "RUNNING"
        fail_reason = None if status_value == "PASS" else str(check.get("detail") or "check_failed")
        remediation = None if status_value == "PASS" else _check_remediation_text(key)
        checks.append(
            {
                "check_key": key,
                "title": key.replace("_", " ").title(),
                "status": status_value,
                "blocking": status_value != "PASS",
                "fail_reason": fail_reason,
                "remediation": remediation,
                "remediation_payload": {
                    "severity": "critical" if status_value != "PASS" else "info",
                    "suggested_action": remediation,
                },
                "last_run_at": now_iso,
                "stale": False,
            }
        )

    release_gate_status = str(remediation_state.get("release_gate_status") or "UNKNOWN").strip().upper()
    reason_codes = [str(item).strip() for item in list(remediation_state.get("release_gate_reason_codes") or []) if str(item).strip()]
    release_gate_check_status = "PASS" if release_gate_status == "PASS" else "FAIL"
    checks.append(
        {
            "check_key": "release_gate_contract",
            "title": "Release Gate Contract",
            "status": release_gate_check_status,
            "blocking": release_gate_check_status != "PASS",
            "fail_reason": None if release_gate_check_status == "PASS" else ", ".join(reason_codes) or "release_gate_blocked",
            "remediation": None if release_gate_check_status == "PASS" else _check_remediation_text("release_gate_contract"),
            "remediation_payload": {
                "severity": "critical" if release_gate_check_status != "PASS" else "info",
                "suggested_action": _check_remediation_text("release_gate_contract"),
                "reason_codes": reason_codes,
            },
            "last_run_at": now_iso,
            "stale": False,
        }
    )

    dedup: dict[str, dict] = {}
    for item in checks:
        dedup[item["check_key"]] = item
    return list(dedup.values())


def _resolve_override_active(override_payload: dict | None, now: datetime) -> dict | None:
    if not isinstance(override_payload, dict):
        return None
    revoked_at = _parse_dt(override_payload.get("revoked_at"))
    expires_at = _parse_dt(override_payload.get("expires_at"))
    if revoked_at is not None:
        return None
    if expires_at is None:
        return None
    if expires_at <= now:
        return None
    return dict(override_payload)


def _enrich_checks_with_stale(checks: list[dict], now: datetime) -> tuple[list[dict], list[str], list[str]]:
    enriched: list[dict] = []
    failing_keys: list[str] = []
    running_or_stale_keys: list[str] = []
    stale_threshold = timedelta(minutes=CHECK_STALE_MINUTES)

    for item in list(checks or []):
        row = dict(item or {})
        status_value = str(row.get("status") or "RUNNING").strip().upper()
        if status_value not in {"PASS", "FAIL", "RUNNING"}:
            status_value = "RUNNING"
        last_run_at = _parse_dt(row.get("last_run_at"))
        stale = True
        if last_run_at is not None:
            stale = (now - last_run_at) > stale_threshold

        if status_value != "PASS":
            failing_keys.append(str(row.get("check_key") or "check_unknown"))
        if status_value == "RUNNING" or stale:
            running_or_stale_keys.append(str(row.get("check_key") or "check_unknown"))

        row["status"] = status_value
        row["stale"] = bool(stale)
        row["blocking"] = status_value != "PASS" or bool(stale)
        if stale and status_value == "PASS":
            row["fail_reason"] = row.get("fail_reason") or "check_stale"
            row["remediation"] = row.get("remediation") or "Check stale oldu. Rerun ile güncel doğrulama alın."
            payload = dict(row.get("remediation_payload") or {})
            payload["severity"] = "warning"
            payload["suggested_action"] = row.get("remediation")
            row["remediation_payload"] = payload

        enriched.append(row)

    return enriched, failing_keys, running_or_stale_keys


def _sync_override_expiry(db: Session, *, store: dict) -> bool:
    override_payload = dict(store.get("override") or {})
    if not override_payload:
        return False

    now = _utcnow()
    revoked_at = _parse_dt(override_payload.get("revoked_at"))
    expires_at = _parse_dt(override_payload.get("expires_at"))
    if revoked_at is not None or expires_at is None or expires_at > now:
        return False

    previous_state = str(store.get("state") or "NO_GO")
    override_id = str(override_payload.get("override_id") or "")

    row = db.query(ReleaseGateOverride).filter(ReleaseGateOverride.id == override_id).first() if override_id else None
    if row is not None and row.revoked_at is None:
        row.revoked_at = now
        row.deploy_context = {**(row.deploy_context or {}), "auto_revoked": "expired", "auto_revoked_at": _iso(now)}
        db.commit()

    override_payload["revoked_at"] = _iso(now)
    store["override"] = override_payload
    store["state"] = "NO_GO"
    store["updated_at"] = _iso(now)
    store["last_transition"] = {
        "previous_state": previous_state,
        "next_state": "NO_GO",
        "reason_code": "OVERRIDE_EXPIRED",
        "reason_text": "Süreli GO_WITH_OVERRIDE süresi dolduğu için NO_GO durumuna dönüldü.",
        "expiry": _iso(expires_at),
        "changed_at": _iso(now),
    }

    create_audit_log(
        db,
        action="PRODUCTION_GATE_OVERRIDE_EXPIRED",
        entity_type=PRODUCTION_GATE_ENTITY_TYPE,
        entity_id="global",
        actor_user_id=None,
        actor_role="system",
        severity="warning",
        details={
            "previous_state": previous_state,
            "next_state": "NO_GO",
            "reason_code": "OVERRIDE_EXPIRED",
            "reason_text": "override_expired",
            "expiry": _iso(expires_at),
            "override_id": override_id,
        },
    )
    return True


def _resolve_status(store: dict) -> dict:
    now = _utcnow()
    checklist = _normalize_checklist(store.get("checklist") if isinstance(store.get("checklist"), list) else [])
    checks, failing_keys, running_or_stale_keys = _enrich_checks_with_stale(list(store.get("checks") or []), now)

    checklist_incomplete_keys = [
        str(item.get("item_key") or "")
        for item in checklist
        if bool(item.get("required", True)) and not bool(item.get("checked", False))
    ]

    checklist_complete = len(checklist_incomplete_keys) == 0
    checks_all_pass = len(checks) > 0 and len(failing_keys) == 0 and len(running_or_stale_keys) == 0
    has_stale_or_running = len(running_or_stale_keys) > 0

    configured_state = str(store.get("state") or "NO_GO").strip().upper()
    if configured_state not in PRODUCTION_GATE_STATES:
        configured_state = "NO_GO"

    active_override = _resolve_override_active(store.get("override"), now)

    blocked_reason_codes: list[str] = []
    if configured_state == "NO_GO":
        blocked_reason_codes.append("state_no_go")
    if not checklist_complete:
        blocked_reason_codes.append("checklist_incomplete")
    if len(failing_keys) > 0:
        blocked_reason_codes.append("failing_checks_present")
    if has_stale_or_running:
        blocked_reason_codes.append("stale_or_running_checks")
    if configured_state == "GO_WITH_OVERRIDE" and active_override is None:
        blocked_reason_codes.append("override_inactive")

    effective_state = "NO_GO"
    if configured_state == "GO" and checklist_complete and checks_all_pass and not has_stale_or_running:
        effective_state = "GO"
    elif configured_state == "GO_WITH_OVERRIDE" and active_override is not None:
        effective_state = "GO_WITH_OVERRIDE"

    deploy_allowed = effective_state in {"GO", "GO_WITH_OVERRIDE"}
    unique_codes = list(dict.fromkeys([code for code in blocked_reason_codes if str(code).strip()]))
    blocked_reason_text = None
    if not deploy_allowed:
        blocked_reason_text = (
            "Deploy/LIVE aktivasyonu Production Gate tarafından engellendi. "
            f"reason_codes={','.join(unique_codes) if unique_codes else 'unknown'}"
        )

    release_gate_contract = "UNKNOWN"
    for check in checks:
        if str(check.get("check_key") or "") == "release_gate_contract":
            release_gate_contract = str(check.get("status") or "UNKNOWN")
            break

    return {
        "configured_state": configured_state,
        "effective_state": effective_state,
        "deploy_allowed": deploy_allowed,
        "checklist_complete": checklist_complete,
        "checks_all_pass": checks_all_pass,
        "has_stale_or_running": has_stale_or_running,
        "blocked_reason_codes": unique_codes,
        "blocked_reason_text": blocked_reason_text,
        "release_gate_contract": release_gate_contract,
        "validation_block_http_status": 400,
        "deploy_block_http_status": 403,
        "checklist": checklist,
        "checks": checks,
        "active_override": active_override,
        "updated_at": _parse_dt(store.get("updated_at")) or now,
        "updated_by_user_id": store.get("updated_by_user_id"),
    }


def _list_audit_history(db: Session, *, limit: int = 30) -> list[dict]:
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == PRODUCTION_GATE_ENTITY_TYPE)
        .order_by(AuditLog.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "severity": row.severity,
            "actor_user_id": row.actor_user_id,
            "actor_role": row.actor_role,
            "details": row.details or {},
            "created_at": row.created_at,
        }
        for row in rows
    ]


def get_production_gate_status(db: Session, *, refresh_checks: bool = False, audit_limit: int = 30) -> dict:
    store = _load_store(db)
    changed = False

    if refresh_checks or len(list(store.get("checks") or [])) == 0:
        remediation_state = build_prod_config_remediation_state(db)
        store["checks"] = _build_checks_from_remediation(remediation_state)
        store["updated_at"] = _iso(_utcnow())
        changed = True

    if _sync_override_expiry(db, store=store):
        changed = True

    if changed:
        store = _persist_store(db, store=store, actor_user_id=store.get("updated_by_user_id"))

    status_payload = _resolve_status(store)
    status_payload["audit_history"] = _list_audit_history(db, limit=audit_limit) if audit_limit > 0 else []
    return status_payload


def rerun_production_gate_checks(
    db: Session,
    *,
    actor_user_id: str,
    actor_role: str,
    check_key: str | None = None,
) -> dict:
    store = _load_store(db)
    previous_state = str(store.get("state") or "NO_GO")
    remediation_state = build_prod_config_remediation_state(db)
    fresh_checks = _build_checks_from_remediation(remediation_state)

    if check_key:
        normalized_key = str(check_key or "").strip().lower()
        target = next((item for item in fresh_checks if str(item.get("check_key") or "") == normalized_key), None)
        if target is None:
            raise ValueError("check_not_found")

        existing_map = {str(item.get("check_key") or ""): dict(item or {}) for item in list(store.get("checks") or [])}
        existing_map[normalized_key] = target
        store["checks"] = list(existing_map.values())
    else:
        store["checks"] = fresh_checks

    store["updated_at"] = _iso(_utcnow())
    store["updated_by_user_id"] = actor_user_id
    store = _persist_store(db, store=store, actor_user_id=actor_user_id)

    create_audit_log(
        db,
        action="PRODUCTION_GATE_CHECK_RERUN_SINGLE" if check_key else "PRODUCTION_GATE_CHECK_RERUN_ALL",
        entity_type=PRODUCTION_GATE_ENTITY_TYPE,
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={
            "previous_state": previous_state,
            "next_state": str(store.get("state") or "NO_GO"),
            "reason_code": "CHECK_RERUN",
            "reason_text": f"rerun::{str(check_key or 'all').lower()}",
            "expiry": _iso(_parse_dt((store.get("override") or {}).get("expires_at"))) if store.get("override") else None,
        },
    )

    return get_production_gate_status(db, refresh_checks=False, audit_limit=30)


def update_production_gate_checklist_item(
    db: Session,
    *,
    actor_user_id: str,
    actor_role: str,
    item_key: str,
    checked: bool,
) -> dict:
    store = _load_store(db)
    normalized_key = str(item_key or "").strip().lower()
    found = False
    for item in list(store.get("checklist") or []):
        if str(item.get("item_key") or "").strip().lower() != normalized_key:
            continue
        found = True
        item["checked"] = bool(checked)
        item["updated_at"] = _iso(_utcnow())
        item["updated_by_user_id"] = actor_user_id
        break
    if not found:
        raise ValueError("checklist_item_not_found")

    previous_state = str(store.get("state") or "NO_GO")
    store["updated_at"] = _iso(_utcnow())
    store["updated_by_user_id"] = actor_user_id
    store = _persist_store(db, store=store, actor_user_id=actor_user_id)

    create_audit_log(
        db,
        action="PRODUCTION_GATE_CHECKLIST_UPDATED",
        entity_type=PRODUCTION_GATE_ENTITY_TYPE,
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        details={
            "previous_state": previous_state,
            "next_state": str(store.get("state") or "NO_GO"),
            "reason_code": "CHECKLIST_UPDATED",
            "reason_text": f"{normalized_key}={bool(checked)}",
            "expiry": _iso(_parse_dt((store.get("override") or {}).get("expires_at"))) if store.get("override") else None,
        },
    )
    return get_production_gate_status(db, refresh_checks=False, audit_limit=30)


def set_production_gate_state(
    db: Session,
    *,
    actor_user_id: str,
    actor_role: str,
    target_state: str,
    reason_code: str,
    reason_text: str,
) -> dict:
    normalized_target = str(target_state or "").strip().upper()
    if normalized_target not in {"NO_GO", "GO"}:
        raise ValueError("invalid_target_state")

    normalized_reason_code = str(reason_code or "").strip().upper()
    normalized_reason_text = str(reason_text or "").strip()
    if len(normalized_reason_code) < 2:
        raise ValueError("reason_code_required")
    if len(normalized_reason_text) < 5:
        raise ValueError("reason_text_required")

    store = _load_store(db)
    if len(list(store.get("checks") or [])) == 0:
        remediation_state = build_prod_config_remediation_state(db)
        store["checks"] = _build_checks_from_remediation(remediation_state)

    _sync_override_expiry(db, store=store)
    status_payload = _resolve_status(store)

    if normalized_target == "GO":
        if not bool(status_payload.get("checklist_complete")):
            raise ValueError("checklist_incomplete")
        if not bool(status_payload.get("checks_all_pass")):
            raise ValueError("checks_not_passed")
        if bool(status_payload.get("has_stale_or_running")):
            raise ValueError("stale_or_running_checks")

    previous_state = str(store.get("state") or "NO_GO")
    store["state"] = normalized_target
    store["updated_at"] = _iso(_utcnow())
    store["updated_by_user_id"] = actor_user_id
    store["last_transition"] = {
        "previous_state": previous_state,
        "next_state": normalized_target,
        "reason_code": normalized_reason_code,
        "reason_text": normalized_reason_text,
        "expiry": _iso(_parse_dt((store.get("override") or {}).get("expires_at"))) if store.get("override") else None,
        "changed_at": _iso(_utcnow()),
    }

    if normalized_target == "NO_GO" and isinstance(store.get("override"), dict):
        override_id = str((store.get("override") or {}).get("override_id") or "")
        if override_id:
            row = db.query(ReleaseGateOverride).filter(ReleaseGateOverride.id == override_id).first()
            if row is not None and row.revoked_at is None:
                row.revoked_at = _utcnow()
                row.deploy_context = {
                    **(row.deploy_context or {}),
                    "revoked_by": actor_user_id,
                    "revoked_reason": "manual_no_go",
                }
                db.commit()
            store["override"]["revoked_at"] = _iso(_utcnow())

    _persist_store(db, store=store, actor_user_id=actor_user_id)

    create_audit_log(
        db,
        action="PRODUCTION_GATE_STATE_CHANGED",
        entity_type=PRODUCTION_GATE_ENTITY_TYPE,
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning" if normalized_target == "NO_GO" else "info",
        details={
            "previous_state": previous_state,
            "next_state": normalized_target,
            "reason_code": normalized_reason_code,
            "reason_text": normalized_reason_text,
            "expiry": _iso(_parse_dt((store.get("override") or {}).get("expires_at"))) if store.get("override") else None,
        },
    )

    return get_production_gate_status(db, refresh_checks=False, audit_limit=30)


def create_production_gate_override(
    db: Session,
    *,
    actor_user_id: str,
    actor_role: str,
    reason_code: str,
    reason_text: str,
    ttl_minutes: int,
) -> dict:
    normalized_reason_code = str(reason_code or "").strip().upper()
    normalized_reason_text = str(reason_text or "").strip()
    if normalized_reason_code not in OVERRIDE_REASON_CODES:
        raise ValueError("invalid_override_reason_code")
    if len(normalized_reason_text) < 12:
        raise ValueError("reason_text_too_short")
    if int(ttl_minutes) > 30:
        raise ValueError("ttl_minutes_max_30")

    store = _load_store(db)
    _sync_override_expiry(db, store=store)
    current_status = _resolve_status(store)
    if str(current_status.get("effective_state") or "NO_GO") != "NO_GO":
        raise ValueError("override_requires_no_go_state")

    now = _utcnow()
    expires_at = now + timedelta(minutes=max(int(ttl_minutes), 1))
    gate_snapshot = {
        "configured_state": current_status.get("configured_state"),
        "effective_state": current_status.get("effective_state"),
        "blocked_reason_codes": current_status.get("blocked_reason_codes") or [],
    }

    row = ReleaseGateOverride(
        id=str(uuid.uuid4()),
        admin_user_id=actor_user_id,
        reason_code=normalized_reason_code,
        reason_note=normalized_reason_text,
        release_gate_snapshot=gate_snapshot,
        deploy_context={"source": "production_gate_control_panel"},
        created_at=now,
        expires_at=expires_at,
        revoked_at=None,
        used_deploy_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    previous_state = str(store.get("state") or "NO_GO")
    store["state"] = "GO_WITH_OVERRIDE"
    store["override"] = {
        "override_id": row.id,
        "reason_code": row.reason_code,
        "reason_text": row.reason_note,
        "expires_at": _iso(row.expires_at),
        "created_at": _iso(row.created_at),
        "revoked_at": _iso(row.revoked_at),
        "created_by_user_id": row.admin_user_id,
    }
    store["updated_at"] = _iso(_utcnow())
    store["updated_by_user_id"] = actor_user_id
    _persist_store(db, store=store, actor_user_id=actor_user_id)

    create_audit_log(
        db,
        action="PRODUCTION_GATE_OVERRIDE_CREATED",
        entity_type=PRODUCTION_GATE_ENTITY_TYPE,
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={
            "previous_state": previous_state,
            "next_state": "GO_WITH_OVERRIDE",
            "reason_code": normalized_reason_code,
            "reason_text": normalized_reason_text,
            "expiry": _iso(expires_at),
            "override_id": row.id,
        },
    )
    return get_production_gate_status(db, refresh_checks=False, audit_limit=30)


def revoke_production_gate_override(
    db: Session,
    *,
    actor_user_id: str,
    actor_role: str,
    override_id: str,
) -> dict:
    normalized_id = str(override_id or "").strip()
    if not normalized_id:
        raise ValueError("override_id_required")

    row = db.query(ReleaseGateOverride).filter(ReleaseGateOverride.id == normalized_id).first()
    if row is None:
        raise ValueError("override_not_found")
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        row.deploy_context = {**(row.deploy_context or {}), "revoked_by": actor_user_id, "revoked_reason": "manual_revoke"}
        db.commit()
        db.refresh(row)

    store = _load_store(db)
    previous_state = str(store.get("state") or "NO_GO")
    if isinstance(store.get("override"), dict) and str((store.get("override") or {}).get("override_id") or "") == normalized_id:
        store["override"]["revoked_at"] = _iso(row.revoked_at)
    store["state"] = "NO_GO"
    store["updated_at"] = _iso(_utcnow())
    store["updated_by_user_id"] = actor_user_id
    _persist_store(db, store=store, actor_user_id=actor_user_id)

    create_audit_log(
        db,
        action="PRODUCTION_GATE_OVERRIDE_REVOKED",
        entity_type=PRODUCTION_GATE_ENTITY_TYPE,
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={
            "previous_state": previous_state,
            "next_state": "NO_GO",
            "reason_code": "OVERRIDE_REVOKED",
            "reason_text": "manual_revoke",
            "expiry": _iso(row.expires_at),
            "override_id": normalized_id,
        },
    )
    return get_production_gate_status(db, refresh_checks=False, audit_limit=30)


def enforce_production_gate_or_raise(
    db: Session,
    *,
    actor_user_id: str,
    actor_role: str,
    action_type: str,
    reason_text: str,
) -> dict:
    gate_status = get_production_gate_status(db, refresh_checks=False, audit_limit=0)
    if bool(gate_status.get("deploy_allowed")):
        create_audit_log(
            db,
            action="PRODUCTION_GATE_ACTION_ALLOWED",
            entity_type=PRODUCTION_GATE_ENTITY_TYPE,
            entity_id="global",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            details={
                "previous_state": gate_status.get("configured_state"),
                "next_state": gate_status.get("effective_state"),
                "reason_code": "GATE_ALLOWED",
                "reason_text": reason_text,
                "expiry": (gate_status.get("active_override") or {}).get("expires_at") if gate_status.get("active_override") else None,
                "action_type": action_type,
            },
        )
        return gate_status

    create_audit_log(
        db,
        action="PRODUCTION_GATE_ACTION_BLOCKED",
        entity_type=PRODUCTION_GATE_ENTITY_TYPE,
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={
            "previous_state": gate_status.get("configured_state"),
            "next_state": gate_status.get("effective_state"),
            "reason_code": "GATE_BLOCKED",
            "reason_text": reason_text,
            "expiry": (gate_status.get("active_override") or {}).get("expires_at") if gate_status.get("active_override") else None,
            "action_type": action_type,
            "blocked_reason_codes": gate_status.get("blocked_reason_codes") or [],
        },
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "production_gate_blocked",
            "gate_state": gate_status.get("effective_state"),
            "blocked_reason_codes": gate_status.get("blocked_reason_codes") or [],
        },
    )


def build_production_gate_export(db: Session) -> dict:
    return {
        "exported_at": _utcnow(),
        "gate": get_production_gate_status(db, refresh_checks=False, audit_limit=200),
    }