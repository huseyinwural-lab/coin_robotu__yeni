import hashlib
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import (
    credential_fingerprint,
    decrypt_exchange_secret,
    encrypt_exchange_secret,
    mask_secret,
)
from models import AdminExchangeCredential, CredentialAssignmentRule, User, UserExchangeConnection

ALLOWED_SCOPE_TYPES = {"global", "tenant", "group"}
ALLOWED_MARKETS = {"spot", "futures"}
ALLOWED_ENVS = {"testnet", "live"}
ALLOWED_PURPOSES = {"market_data", "execution_fallback", "ops_probe"}
ALLOWED_SOURCES = {"user", "admin", "admin_fallback"}
PROBE_STATUS = {
    "ready",
    "invalid_key",
    "permission_restricted",
    "ip_restricted",
    "env_mismatch",
    "unreachable",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(value: str | None, *, default: str = "") -> str:
    return str(value or default).strip().lower()


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _default_spot_base(environment: str) -> str:
    return "https://testnet.binance.vision" if environment == "testnet" else "https://api.binance.com"


def _default_futures_base(environment: str) -> str:
    return "https://testnet.binancefuture.com" if environment == "testnet" else "https://fapi.binance.com"


def _effective_base_url(*, market_type: str, environment: str, override: str | None) -> str:
    if override and str(override).strip():
        return str(override).strip().rstrip("/")
    if market_type == "futures":
        return _default_futures_base(environment)
    return _default_spot_base(environment)


def _signed_get(*, base_url: str, endpoint: str, api_key: str, api_secret: str, params: dict | None = None) -> tuple[int, dict]:
    payload = {**(params or {}), "timestamp": int(time.time() * 1000), "recvWindow": 60000}
    qs = urlencode(payload)
    signature = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{qs}&signature={signature}"
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, headers={"X-MBX-APIKEY": api_key})
    try:
        body = response.json() if response.content else {}
    except Exception:
        body = {"raw": response.text[:200]}
    return response.status_code, body


def _spot_probe(*, base_url: str, api_key: str, api_secret: str) -> tuple[str, str, dict]:
    with httpx.Client(timeout=10.0) as client:
        ping = client.get(f"{base_url}/api/v3/ping")
    if ping.status_code == 451:
        return "ip_restricted", "spot_ping_451", {"ping_status": ping.status_code}
    if ping.status_code >= 400:
        return "unreachable", f"spot_ping_{ping.status_code}", {"ping_status": ping.status_code}

    status, body = _signed_get(base_url=base_url, endpoint="/api/v3/account", api_key=api_key, api_secret=api_secret)
    if status == 200:
        return "ready", "spot_account_ok", {"account_status": status}

    code = str((body or {}).get("code") or "")
    msg = str((body or {}).get("msg") or "").lower()
    if status == 451:
        return "ip_restricted", "spot_signed_451", {"status": status, "code": code, "message": msg}
    if status in {401, 403} and code in {"-2015", "-2014"}:
        return "invalid_key", "spot_invalid_key", {"status": status, "code": code, "message": msg}
    if "permission" in msg:
        return "permission_restricted", "spot_permission_restricted", {"status": status, "code": code, "message": msg}
    if "testnet" in msg or "live" in msg:
        return "env_mismatch", "spot_environment_mismatch", {"status": status, "code": code, "message": msg}
    return "unreachable", "spot_probe_failed", {"status": status, "code": code, "message": msg}


def _futures_probe(*, base_url: str, api_key: str, api_secret: str) -> tuple[str, str, dict]:
    with httpx.Client(timeout=10.0) as client:
        ping = client.get(f"{base_url}/fapi/v1/ping")
    if ping.status_code == 451:
        return "ip_restricted", "futures_ping_451", {"ping_status": ping.status_code}
    if ping.status_code >= 400:
        return "unreachable", f"futures_ping_{ping.status_code}", {"ping_status": ping.status_code}

    status, body = _signed_get(base_url=base_url, endpoint="/fapi/v2/account", api_key=api_key, api_secret=api_secret)
    if status == 200:
        return "ready", "futures_account_ok", {"account_status": status}

    code = str((body or {}).get("code") or "")
    msg = str((body or {}).get("msg") or "").lower()
    if status == 451:
        return "ip_restricted", "futures_signed_451", {"status": status, "code": code, "message": msg}
    if status in {401, 403} and code in {"-2015", "-2014"}:
        return "invalid_key", "futures_invalid_key", {"status": status, "code": code, "message": msg}
    if "permission" in msg:
        return "permission_restricted", "futures_permission_restricted", {"status": status, "code": code, "message": msg}
    if "testnet" in msg or "live" in msg:
        return "env_mismatch", "futures_environment_mismatch", {"status": status, "code": code, "message": msg}
    return "unreachable", "futures_probe_failed", {"status": status, "code": code, "message": msg}


def _serialize_admin_credential(row: AdminExchangeCredential) -> dict:
    api_key = decrypt_exchange_secret(row.api_key_encrypted)
    api_secret = decrypt_exchange_secret(row.api_secret_encrypted)
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "exchange": row.exchange,
        "market_type": row.market_type,
        "purpose": row.purpose,
        "environment": row.environment,
        "base_url_override": row.base_url_override,
        "ip_binding_note": row.ip_binding_note,
        "is_active": bool(row.is_active),
        "is_default": bool(row.is_default),
        "approval_status": row.approval_status,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "has_api_key": bool(row.api_key_encrypted),
        "has_api_secret": bool(row.api_secret_encrypted),
        "masked_api_key": mask_secret(api_key),
        "credential_fingerprint": credential_fingerprint(api_key, api_secret),
        "last_probe_status": row.last_probe_status,
        "last_probe_message": row.last_probe_message,
        "last_probe_meta": row.last_probe_meta or {},
        "last_probe_at": row.last_probe_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_assignment_rule(row: CredentialAssignmentRule) -> dict:
    return {
        "id": row.id,
        "exchange": row.exchange,
        "market_type": row.market_type,
        "environment": row.environment,
        "tenant_id": row.tenant_id,
        "user_id": row.user_id,
        "preferred_source": row.preferred_source,
        "fallback_enabled": bool(row.fallback_enabled),
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_credential_payload(*, scope_type: str, market_type: str, purpose: str, environment: str, exchange: str) -> None:
    if scope_type not in ALLOWED_SCOPE_TYPES:
        raise ValueError("invalid_scope_type")
    if market_type not in ALLOWED_MARKETS:
        raise ValueError("invalid_market_type")
    if environment not in ALLOWED_ENVS:
        raise ValueError("invalid_environment")
    if purpose not in ALLOWED_PURPOSES:
        raise ValueError("invalid_purpose")
    if exchange != "binance":
        raise ValueError("unsupported_exchange")


def list_admin_credentials(
    db: Session,
    *,
    exchange: str | None,
    market_type: str | None,
    environment: str | None,
    scope_type: str | None,
    approval_status: str | None,
    include_inactive: bool,
) -> list[dict]:
    query = db.query(AdminExchangeCredential)
    if exchange:
        query = query.filter(AdminExchangeCredential.exchange == _norm(exchange))
    if market_type:
        query = query.filter(AdminExchangeCredential.market_type == _norm(market_type))
    if environment:
        query = query.filter(AdminExchangeCredential.environment == _norm(environment))
    if scope_type:
        query = query.filter(AdminExchangeCredential.scope_type == _norm(scope_type))
    if approval_status:
        query = query.filter(AdminExchangeCredential.approval_status == _norm(approval_status))
    if not include_inactive:
        query = query.filter(AdminExchangeCredential.is_active.is_(True))
    rows = query.order_by(AdminExchangeCredential.updated_at.desc()).all()
    return [_serialize_admin_credential(row) for row in rows]


def create_admin_credential(
    db: Session,
    *,
    actor: User,
    scope_type: str,
    scope_id: str | None,
    exchange: str,
    market_type: str,
    purpose: str,
    environment: str,
    api_key: str,
    api_secret: str,
    passphrase: str | None,
    base_url_override: str | None,
    ip_binding_note: str | None,
    is_default: bool,
) -> dict:
    normalized_scope = _norm(scope_type)
    normalized_market = _norm(market_type)
    normalized_purpose = _norm(purpose)
    normalized_env = _norm(environment)
    normalized_exchange = _norm(exchange)

    _validate_credential_payload(
        scope_type=normalized_scope,
        market_type=normalized_market,
        purpose=normalized_purpose,
        environment=normalized_env,
        exchange=normalized_exchange,
    )

    row = AdminExchangeCredential(
        scope_type=normalized_scope,
        scope_id=(scope_id or None),
        exchange=normalized_exchange,
        market_type=normalized_market,
        purpose=normalized_purpose,
        environment=normalized_env,
        api_key_encrypted=encrypt_exchange_secret(api_key),
        api_secret_encrypted=encrypt_exchange_secret(api_secret),
        passphrase_encrypted=encrypt_exchange_secret(passphrase or "") if passphrase else None,
        base_url_override=(base_url_override or None),
        ip_binding_note=(ip_binding_note or None),
        is_active=False,
        is_default=bool(is_default),
        approval_status="pending",
        created_by=actor.id,
        updated_by=actor.id,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_admin_credential(row)


def update_admin_credential(
    db: Session,
    *,
    actor: User,
    credential_id: str,
    scope_type: str | None,
    scope_id: str | None,
    purpose: str | None,
    base_url_override: str | None,
    ip_binding_note: str | None,
    api_key: str | None,
    api_secret: str | None,
    passphrase: str | None,
    is_default: bool | None,
    is_active: bool | None,
) -> dict:
    row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == credential_id).first()
    if row is None:
        raise ValueError("credential_not_found")

    if scope_type is not None:
        normalized_scope = _norm(scope_type)
        if normalized_scope not in ALLOWED_SCOPE_TYPES:
            raise ValueError("invalid_scope_type")
        row.scope_type = normalized_scope
    if scope_id is not None:
        row.scope_id = scope_id or None
    if purpose is not None:
        normalized_purpose = _norm(purpose)
        if normalized_purpose not in ALLOWED_PURPOSES:
            raise ValueError("invalid_purpose")
        row.purpose = normalized_purpose
    if base_url_override is not None:
        row.base_url_override = base_url_override or None
    if ip_binding_note is not None:
        row.ip_binding_note = ip_binding_note or None
    if api_key is not None and str(api_key).strip():
        row.api_key_encrypted = encrypt_exchange_secret(api_key)
        row.approval_status = "pending"
        row.is_active = False
    if api_secret is not None and str(api_secret).strip():
        row.api_secret_encrypted = encrypt_exchange_secret(api_secret)
        row.approval_status = "pending"
        row.is_active = False
    if passphrase is not None:
        row.passphrase_encrypted = encrypt_exchange_secret(passphrase) if passphrase else None
        row.approval_status = "pending"
        row.is_active = False
    if is_default is not None:
        row.is_default = bool(is_default)
    if is_active is not None:
        row.is_active = bool(is_active)

    row.updated_by = actor.id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _serialize_admin_credential(row)


def approve_admin_credential(db: Session, *, actor: User, credential_id: str) -> dict:
    row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == credential_id).first()
    if row is None:
        raise ValueError("credential_not_found")
    row.approval_status = "approved"
    row.is_active = True
    row.approved_by = actor.id
    row.approved_at = _now()
    row.updated_by = actor.id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _serialize_admin_credential(row)


def disable_admin_credential(db: Session, *, actor: User, credential_id: str) -> dict:
    row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == credential_id).first()
    if row is None:
        raise ValueError("credential_not_found")
    row.is_active = False
    row.approval_status = "rejected" if row.approval_status == "pending" else row.approval_status
    row.updated_by = actor.id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _serialize_admin_credential(row)


def probe_admin_credential(db: Session, *, actor: User, credential_id: str) -> dict:
    row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == credential_id).first()
    if row is None:
        raise ValueError("credential_not_found")

    api_key = decrypt_exchange_secret(row.api_key_encrypted)
    api_secret = decrypt_exchange_secret(row.api_secret_encrypted)
    base_url = _effective_base_url(market_type=row.market_type, environment=row.environment, override=row.base_url_override)

    try:
        if row.market_type == "spot":
            status_code, message, meta = _spot_probe(base_url=base_url, api_key=api_key, api_secret=api_secret)
        else:
            status_code, message, meta = _futures_probe(base_url=base_url, api_key=api_key, api_secret=api_secret)
    except Exception as exc:
        status_code, message, meta = "unreachable", "probe_exception", {"error": str(exc)}

    row.last_probe_status = status_code
    row.last_probe_message = message
    row.last_probe_meta = {**(meta or {}), "base_url": base_url}
    row.last_probe_at = _now()
    row.updated_by = actor.id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _serialize_admin_credential(row)


def list_assignment_rules(db: Session, *, exchange: str | None, market_type: str | None, environment: str | None) -> list[dict]:
    query = db.query(CredentialAssignmentRule)
    if exchange:
        query = query.filter(CredentialAssignmentRule.exchange == _norm(exchange))
    if market_type:
        query = query.filter(CredentialAssignmentRule.market_type == _norm(market_type))
    if environment:
        query = query.filter(CredentialAssignmentRule.environment == _norm(environment))
    rows = query.order_by(CredentialAssignmentRule.updated_at.desc()).all()
    return [_serialize_assignment_rule(row) for row in rows]


def upsert_assignment_rule(
    db: Session,
    *,
    actor: User,
    exchange: str,
    market_type: str,
    environment: str,
    tenant_id: str | None,
    user_id: str | None,
    preferred_source: str,
    fallback_enabled: bool,
) -> dict:
    normalized_exchange = _norm(exchange)
    normalized_market = _norm(market_type)
    normalized_env = _norm(environment)
    normalized_source = _norm(preferred_source)

    if normalized_market not in ALLOWED_MARKETS:
        raise ValueError("invalid_market_type")
    if normalized_env not in ALLOWED_ENVS:
        raise ValueError("invalid_environment")
    if normalized_source not in ALLOWED_SOURCES:
        raise ValueError("invalid_preferred_source")

    row = (
        db.query(CredentialAssignmentRule)
        .filter(
            CredentialAssignmentRule.exchange == normalized_exchange,
            CredentialAssignmentRule.market_type == normalized_market,
            CredentialAssignmentRule.environment == normalized_env,
            CredentialAssignmentRule.tenant_id == (tenant_id or None),
            CredentialAssignmentRule.user_id == (user_id or None),
        )
        .first()
    )
    if row is None:
        row = CredentialAssignmentRule(
            exchange=normalized_exchange,
            market_type=normalized_market,
            environment=normalized_env,
            tenant_id=tenant_id or None,
            user_id=user_id or None,
            preferred_source=normalized_source,
            fallback_enabled=bool(fallback_enabled),
            updated_by=actor.id,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(row)
    else:
        row.preferred_source = normalized_source
        row.fallback_enabled = bool(fallback_enabled)
        row.updated_by = actor.id
        row.updated_at = _now()

    db.commit()
    db.refresh(row)
    return _serialize_assignment_rule(row)


def _rule_for_context(
    db: Session,
    *,
    exchange: str,
    market_type: str,
    environment: str,
    tenant_id: str | None,
    user_id: str | None,
) -> dict:
    rows = (
        db.query(CredentialAssignmentRule)
        .filter(
            CredentialAssignmentRule.exchange == exchange,
            CredentialAssignmentRule.market_type == market_type,
            CredentialAssignmentRule.environment == environment,
        )
        .order_by(CredentialAssignmentRule.updated_at.desc())
        .all()
    )
    for row in rows:
        if user_id and row.user_id == user_id:
            return {"preferred_source": row.preferred_source, "fallback_enabled": bool(row.fallback_enabled), "rule_id": row.id}
    for row in rows:
        if tenant_id and row.tenant_id == tenant_id and row.user_id is None:
            return {"preferred_source": row.preferred_source, "fallback_enabled": bool(row.fallback_enabled), "rule_id": row.id}
    for row in rows:
        if row.tenant_id is None and row.user_id is None:
            return {"preferred_source": row.preferred_source, "fallback_enabled": bool(row.fallback_enabled), "rule_id": row.id}
    return {"preferred_source": "user", "fallback_enabled": True, "rule_id": None}


def _select_user_credential(
    db: Session,
    *,
    user_id: str,
    exchange: str,
    market_type: str,
    environment: str,
) -> dict | None:
    row = (
        db.query(UserExchangeConnection)
        .filter(
            UserExchangeConnection.user_id == user_id,
            UserExchangeConnection.exchange == exchange,
            UserExchangeConnection.market_type == market_type,
            UserExchangeConnection.environment == environment,
        )
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )
    if row is None:
        return None
    api_key = decrypt_exchange_secret(row.api_key_encrypted)
    api_secret = decrypt_exchange_secret(row.api_secret_encrypted)
    if not api_key or not api_secret:
        return None
    return {
        "source": "user",
        "credential_id": row.id,
        "api_key": api_key,
        "api_secret": api_secret,
        "masked_api_key": mask_secret(api_key),
        "credential_fingerprint": credential_fingerprint(api_key, api_secret),
        "effective_base_url": None,
        "audit_metadata": {
            "source_type": "user",
            "connection_id": row.id,
            "exchange": row.exchange,
            "market_type": row.market_type,
            "environment": row.environment,
        },
    }


def _select_admin_credential(
    db: Session,
    *,
    exchange: str,
    market_type: str,
    environment: str,
    purpose: str,
    tenant_id: str | None,
    group_id: str | None,
) -> dict | None:
    query = (
        db.query(AdminExchangeCredential)
        .filter(
            AdminExchangeCredential.exchange == exchange,
            AdminExchangeCredential.market_type == market_type,
            AdminExchangeCredential.environment == environment,
            AdminExchangeCredential.is_active.is_(True),
            AdminExchangeCredential.approval_status == "approved",
        )
        .order_by(AdminExchangeCredential.is_default.desc(), AdminExchangeCredential.updated_at.desc())
    )
    rows = query.all()
    filtered = [row for row in rows if row.purpose == purpose]
    if not filtered:
        filtered = [row for row in rows if row.purpose in {"execution_fallback", "market_data"}]

    ordered: list[AdminExchangeCredential] = []
    if tenant_id:
        ordered.extend([row for row in filtered if row.scope_type == "tenant" and row.scope_id == tenant_id])
    if group_id:
        ordered.extend([row for row in filtered if row.scope_type == "group" and row.scope_id == group_id])
    ordered.extend([row for row in filtered if row.scope_type == "global"])

    seen: set[str] = set()
    deduped: list[AdminExchangeCredential] = []
    for row in ordered:
        if row.id in seen:
            continue
        seen.add(row.id)
        deduped.append(row)
    if not deduped:
        return None

    row = deduped[0]
    api_key = decrypt_exchange_secret(row.api_key_encrypted)
    api_secret = decrypt_exchange_secret(row.api_secret_encrypted)
    if not api_key or not api_secret:
        return None
    base_url = _effective_base_url(market_type=market_type, environment=environment, override=row.base_url_override)
    source = "admin_global_default"
    if row.scope_type == "tenant":
        source = "admin_tenant_default"
    elif row.scope_type == "group":
        source = "admin_group_default"

    return {
        "source": source,
        "credential_id": row.id,
        "api_key": api_key,
        "api_secret": api_secret,
        "masked_api_key": mask_secret(api_key),
        "credential_fingerprint": credential_fingerprint(api_key, api_secret),
        "effective_base_url": base_url,
        "audit_metadata": {
            "source_type": "admin",
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "purpose": row.purpose,
            "credential_id": row.id,
            "exchange": row.exchange,
            "market_type": row.market_type,
            "environment": row.environment,
        },
    }


def resolve_exchange_credentials(
    db: Session,
    *,
    user_id: str,
    exchange: str,
    market_type: str,
    environment: str,
    purpose: str,
    tenant_id: str | None = None,
    group_id: str | None = None,
    include_secrets: bool = True,
) -> dict:
    normalized_exchange = _norm(exchange)
    normalized_market = _norm(market_type)
    normalized_env = _norm(environment)
    normalized_purpose = _norm(purpose)
    if normalized_market not in ALLOWED_MARKETS:
        raise ValueError("invalid_market_type")
    if normalized_env not in ALLOWED_ENVS:
        raise ValueError("invalid_environment")

    rule = _rule_for_context(
        db,
        exchange=normalized_exchange,
        market_type=normalized_market,
        environment=normalized_env,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    preferred_source = _norm(rule.get("preferred_source"), default="user")
    fallback_enabled = bool(rule.get("fallback_enabled", True))

    user_pick = _select_user_credential(
        db,
        user_id=user_id,
        exchange=normalized_exchange,
        market_type=normalized_market,
        environment=normalized_env,
    )
    admin_pick = _select_admin_credential(
        db,
        exchange=normalized_exchange,
        market_type=normalized_market,
        environment=normalized_env,
        purpose=normalized_purpose,
        tenant_id=tenant_id,
        group_id=group_id,
    )

    selected = None
    selection_reason = ""
    if preferred_source == "admin":
        if admin_pick is not None:
            selected = admin_pick
            selection_reason = "preferred_admin"
        elif fallback_enabled and user_pick is not None:
            selected = user_pick
            selection_reason = "admin_missing_fallback_user"
    elif preferred_source == "admin_fallback":
        if admin_pick is not None:
            selected = admin_pick
            selection_reason = "preferred_admin_fallback"
        elif fallback_enabled and user_pick is not None:
            selected = user_pick
            selection_reason = "admin_fallback_to_user"
    else:
        if user_pick is not None:
            selected = user_pick
            selection_reason = "preferred_user"
        elif fallback_enabled and admin_pick is not None:
            selected = admin_pick
            selection_reason = "user_missing_fallback_admin"

    if selected is None:
        raise ValueError("credential_not_found")

    response = {
        "selected_credential_id": selected["credential_id"],
        "source": selected["source"],
        "masked_api_key": selected["masked_api_key"],
        "masked_fingerprint": selected["credential_fingerprint"],
        "effective_base_url": selected.get("effective_base_url"),
        "audit_metadata": {
            **(selected.get("audit_metadata") or {}),
            "preferred_source": preferred_source,
            "fallback_enabled": fallback_enabled,
            "rule_id": rule.get("rule_id"),
            "selection_reason": selection_reason,
        },
    }
    if include_secrets:
        response["api_key"] = selected["api_key"]
        response["api_secret"] = selected["api_secret"]
    return response


def build_user_routing_preview(
    db: Session,
    *,
    user_id: str,
    exchange: str,
    market_type: str,
    environment: str,
    purpose: str = "execution_fallback",
) -> dict:
    try:
        resolved = resolve_exchange_credentials(
            db,
            user_id=user_id,
            exchange=exchange,
            market_type=market_type,
            environment=environment,
            purpose=purpose,
            include_secrets=False,
        )
        return {
            "effective_source": resolved.get("source"),
            "routing_preview": {
                "selected_credential_id": resolved.get("selected_credential_id"),
                "selection_reason": (resolved.get("audit_metadata") or {}).get("selection_reason"),
                "effective_base_url": resolved.get("effective_base_url"),
                "masked_fingerprint": resolved.get("masked_fingerprint"),
            },
            "environment_valid": True,
        }
    except Exception as exc:
        return {
            "effective_source": "unresolved",
            "routing_preview": {
                "selection_reason": "resolution_failed",
                "error": str(exc),
            },
            "environment_valid": False,
        }
