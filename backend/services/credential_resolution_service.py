import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import (
    credential_fingerprint,
    mask_secret,
)
from models import AdminExchangeCredential, CredentialAssignmentRule, User, UserExchangeConnection
from services.secret_provider_service import (
    decrypt_secret_value,
    encrypt_secret_value,
    revoke_secret_value,
    rotate_secret_value,
    secret_provider_name,
)

ALLOWED_SCOPE_TYPES = {"global", "tenant", "group"}
ALLOWED_EXCHANGES = {"binance", "bybit", "okx"}
ALLOWED_MARKETS = {"spot", "futures", "usdt_perp", "coin_perp"}
ALLOWED_ENVS = {"testnet", "live"}
ALLOWED_PURPOSES = {"market_data", "execution", "fallback", "execution_fallback", "ops_probe"}
ALLOWED_SOURCES = {"user", "admin", "admin_fallback"}
PROBE_STATUS = {
    "ready",
    "connectivity_only",
    "invalid_key",
    "permission_restricted",
    "ip_restricted",
    "env_mismatch",
    "rate_limited",
    "probe_not_supported",
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


def _normalize_market_type(market_type: str) -> str:
    normalized = _norm(market_type)
    return "spot" if normalized == "execution" else normalized


def _normalize_purpose(purpose: str) -> str:
    normalized = _norm(purpose)
    return "fallback" if normalized == "execution_fallback" else normalized


def _purpose_aliases(purpose: str) -> list[str]:
    normalized = _normalize_purpose(purpose)
    if normalized == "execution":
        return ["execution", "fallback", "execution_fallback"]
    if normalized == "fallback":
        return ["fallback", "execution", "execution_fallback"]
    return [normalized]


def _market_aliases(market_type: str) -> list[str]:
    normalized = _normalize_market_type(market_type)
    if normalized == "spot":
        return ["spot"]
    if normalized == "usdt_perp":
        return ["usdt_perp", "futures"]
    if normalized == "coin_perp":
        return ["coin_perp", "futures"]
    if normalized == "futures":
        return ["futures", "usdt_perp", "coin_perp"]
    return [normalized]


def _is_perp_market(market_type: str) -> bool:
    return _normalize_market_type(market_type) in {"futures", "usdt_perp", "coin_perp"}


def _is_execution_purpose(purpose: str) -> bool:
    return _normalize_purpose(purpose) in {"execution", "fallback", "execution_fallback"}


def _verify_secret_roundtrip(*, plain: str, encrypted: str) -> None:
    if decrypt_secret_value(encrypted) != str(plain or ""):
        raise ValueError("credential_readback_verification_failed")


def _permission_scope_from_meta(meta: dict | None) -> dict:
    payload = dict(meta or {})
    scope = payload.get("permission_scope")
    if isinstance(scope, dict):
        return {
            "read": bool(scope.get("read", False)),
            "trade": bool(scope.get("trade", False)),
            "withdraw": bool(scope.get("withdraw", False)),
        }
    return {"read": False, "trade": False, "withdraw": False}


def _validate_permission_scope(*, purpose: str, permission_scope: dict) -> dict:
    read_ok = bool(permission_scope.get("read", False))
    trade_ok = bool(permission_scope.get("trade", False))
    withdraw_enabled = bool(permission_scope.get("withdraw", False))

    if _is_execution_purpose(purpose):
        if withdraw_enabled:
            return {
                "status": "block",
                "reason_code": "withdraw_scope_detected",
                "message": "withdraw yetkisi olan key execution için bloklandı",
            }
        if not trade_ok:
            return {
                "status": "block",
                "reason_code": "missing_trade_scope",
                "message": "execution için trade scope zorunlu",
            }
        if not read_ok:
            return {
                "status": "warn",
                "reason_code": "missing_read_scope",
                "message": "read scope doğrulanamadı",
            }
        return {"status": "pass", "reason_code": "scope_ok", "message": "scope doğrulandı"}

    if not read_ok:
        return {
            "status": "warn",
            "reason_code": "missing_read_scope",
            "message": "market_data purpose için read scope beklenir",
        }
    return {"status": "pass", "reason_code": "scope_ok", "message": "scope doğrulandı"}


def _lifecycle_status(row: AdminExchangeCredential) -> str:
    meta = dict(row.last_probe_meta or {})
    explicit = str(meta.get("lifecycle_status") or "").strip().lower()
    if explicit:
        return explicit
    if str(row.approval_status) == "revoked":
        return "revoked"
    if row.last_probe_status in {"ready", "connectivity_only"}:
        return "verified"
    if str(row.approval_status) == "approved":
        return "approved"
    return "pending"


def _base_url_environment_mismatch(*, environment: str, base_url: str | None) -> bool:
    url = str(base_url or "").lower()
    env = _norm(environment)
    if not url:
        return False
    if env == "live" and "testnet" in url:
        return True
    if env == "testnet" and "testnet" not in url and any(part in url for part in ["binance.com", "bybit.com", "okx.com"]):
        return True
    return False


def _proxy_headers_for_probe(*, exchange: str, market_type: str, environment: str) -> dict[str, str]:
    normalized_exchange = _norm(exchange)
    normalized_env = _norm(environment)
    normalized_market = _normalize_market_type(market_type)
    token = None

    if normalized_exchange == "binance":
        if normalized_market == "spot":
            token = (
                os.environ.get("BINANCE_SPOT_TESTNET_PROXY_TOKEN")
                if normalized_env == "testnet"
                else os.environ.get("BINANCE_SPOT_LIVE_PROXY_TOKEN")
            )
            token = token or os.environ.get("BINANCE_SPOT_PROXY_TOKEN") or os.environ.get("BINANCE_PROXY_TOKEN")
        else:
            token = (
                os.environ.get("BINANCE_FUTURES_TESTNET_PROXY_TOKEN")
                if normalized_env == "testnet"
                else os.environ.get("BINANCE_FUTURES_LIVE_PROXY_TOKEN")
            )
            token = token or os.environ.get("BINANCE_FUTURES_PROXY_TOKEN") or os.environ.get("BINANCE_PROXY_TOKEN")
    elif normalized_exchange == "bybit":
        token = os.environ.get("BYBIT_PROXY_TOKEN")
    elif normalized_exchange == "okx":
        token = os.environ.get("OKX_PROXY_TOKEN")

    if not token:
        return {}
    return {"X-Proxy-Token": token}


def _default_spot_base(exchange: str, environment: str) -> str:
    if exchange == "binance":
        return "https://testnet.binance.vision" if environment == "testnet" else "https://api.binance.com"
    if exchange == "bybit":
        return "https://api-testnet.bybit.com" if environment == "testnet" else "https://api.bybit.com"
    return "https://www.okx.com"


def _default_futures_base(exchange: str, environment: str) -> str:
    if exchange == "binance":
        return "https://testnet.binancefuture.com" if environment == "testnet" else "https://fapi.binance.com"
    if exchange == "bybit":
        return "https://api-testnet.bybit.com" if environment == "testnet" else "https://api.bybit.com"
    return "https://www.okx.com"


def _effective_base_url(*, exchange: str, market_type: str, environment: str, override: str | None) -> str:
    if override and str(override).strip():
        return str(override).strip().rstrip("/")
    if _is_perp_market(market_type):
        return _default_futures_base(exchange, environment)
    return _default_spot_base(exchange, environment)


def _signed_get(
    *,
    base_url: str,
    endpoint: str,
    api_key: str,
    api_secret: str,
    params: dict | None = None,
    extra_headers: dict | None = None,
) -> tuple[int, dict]:
    payload = {**(params or {}), "timestamp": int(time.time() * 1000), "recvWindow": 60000}
    qs = urlencode(payload)
    signature = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{qs}&signature={signature}"
    headers = {"X-MBX-APIKEY": api_key, **(extra_headers or {})}
    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, headers=headers)
    try:
        body = response.json() if response.content else {}
    except Exception:
        body = {"raw": response.text[:200]}
    return response.status_code, body


def _spot_probe(*, base_url: str, api_key: str, api_secret: str, extra_headers: dict | None = None) -> tuple[str, str, dict]:
    with httpx.Client(timeout=10.0) as client:
        ping = client.get(f"{base_url}/api/v3/ping", headers=extra_headers or None)
    if ping.status_code == 451:
        return "ip_restricted", "spot_ping_451", {"ping_status": ping.status_code}
    if ping.status_code >= 400:
        return "unreachable", f"spot_ping_{ping.status_code}", {"ping_status": ping.status_code}

    status, body = _signed_get(
        base_url=base_url,
        endpoint="/api/v3/account",
        api_key=api_key,
        api_secret=api_secret,
        extra_headers=extra_headers,
    )
    if status == 200:
        permission_scope = {
            "read": True,
            "trade": bool(body.get("canTrade", True)) if isinstance(body, dict) else True,
            "withdraw": bool(body.get("canWithdraw", False)) if isinstance(body, dict) else False,
        }
        return "ready", "spot_account_ok", {"account_status": status, "permission_scope": permission_scope}

    code = str((body or {}).get("code") or "")
    msg = str((body or {}).get("msg") or "").lower()
    if status == 451:
        return "ip_restricted", "spot_signed_451", {"status": status, "code": code, "message": msg}
    if status == 429:
        return "rate_limited", "spot_rate_limited", {"status": status, "code": code, "message": msg}
    if status in {401, 403} and code in {"-2015", "-2014"}:
        return "invalid_key", "spot_invalid_key", {"status": status, "code": code, "message": msg}
    if "permission" in msg:
        return "permission_restricted", "spot_permission_restricted", {"status": status, "code": code, "message": msg}
    if "testnet" in msg or "live" in msg:
        return "env_mismatch", "spot_environment_mismatch", {"status": status, "code": code, "message": msg}
    return "unreachable", "spot_probe_failed", {"status": status, "code": code, "message": msg}


def _futures_probe(*, base_url: str, api_key: str, api_secret: str, extra_headers: dict | None = None) -> tuple[str, str, dict]:
    with httpx.Client(timeout=10.0) as client:
        ping = client.get(f"{base_url}/fapi/v1/ping", headers=extra_headers or None)
    if ping.status_code == 451:
        return "ip_restricted", "futures_ping_451", {"ping_status": ping.status_code}
    if ping.status_code >= 400:
        return "unreachable", f"futures_ping_{ping.status_code}", {"ping_status": ping.status_code}

    status, body = _signed_get(
        base_url=base_url,
        endpoint="/fapi/v2/account",
        api_key=api_key,
        api_secret=api_secret,
        extra_headers=extra_headers,
    )
    if status == 200:
        permission_scope = {
            "read": True,
            "trade": bool(body.get("canTrade", True)) if isinstance(body, dict) else True,
            "withdraw": False,
        }
        return "ready", "futures_account_ok", {"account_status": status, "permission_scope": permission_scope}

    code = str((body or {}).get("code") or "")
    msg = str((body or {}).get("msg") or "").lower()
    if status == 451:
        return "ip_restricted", "futures_signed_451", {"status": status, "code": code, "message": msg}
    if status == 429:
        return "rate_limited", "futures_rate_limited", {"status": status, "code": code, "message": msg}
    if status in {401, 403} and code in {"-2015", "-2014"}:
        return "invalid_key", "futures_invalid_key", {"status": status, "code": code, "message": msg}
    if "permission" in msg:
        return "permission_restricted", "futures_permission_restricted", {"status": status, "code": code, "message": msg}
    if "testnet" in msg or "live" in msg:
        return "env_mismatch", "futures_environment_mismatch", {"status": status, "code": code, "message": msg}
    return "unreachable", "futures_probe_failed", {"status": status, "code": code, "message": msg}


def _public_probe(*, base_url: str, endpoint: str, provider: str, extra_headers: dict | None = None) -> tuple[str, str, dict]:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{base_url}{endpoint}", headers=extra_headers or None)
    if response.status_code == 451:
        return "ip_restricted", f"{provider}_public_451", {"status": response.status_code}
    if response.status_code == 429:
        return "rate_limited", f"{provider}_public_rate_limited", {"status": response.status_code}
    if response.status_code >= 400:
        return "unreachable", f"{provider}_public_{response.status_code}", {"status": response.status_code}
    return "connectivity_only", f"{provider}_public_ok", {
        "status": response.status_code,
        "permission_scope": {"read": True, "trade": True, "withdraw": False},
        "permission_scope_source": "inferred_public_probe",
    }


def _serialize_admin_credential(row: AdminExchangeCredential) -> dict:
    # Handle revoked secrets gracefully - don't try to decrypt revoked credentials
    api_key = ""
    api_secret = ""
    try:
        api_key = decrypt_secret_value(row.api_key_encrypted) if row.api_key_encrypted else ""
    except RuntimeError as e:
        if "secret_revoked" in str(e):
            api_key = "[REVOKED]"
        else:
            raise
    try:
        api_secret = decrypt_secret_value(row.api_secret_encrypted) if row.api_secret_encrypted else ""
    except RuntimeError as e:
        if "secret_revoked" in str(e):
            api_secret = "[REVOKED]"
        else:
            raise

    probe_meta = row.last_probe_meta or {}
    permission_scope = _permission_scope_from_meta(probe_meta)
    permission_scope_validation = _validate_permission_scope(purpose=row.purpose, permission_scope=permission_scope)

    # For revoked credentials, use placeholder values for masked_api_key and fingerprint
    masked_key = "[REVOKED]" if api_key == "[REVOKED]" else mask_secret(api_key)
    fingerprint = "[REVOKED]" if api_key == "[REVOKED]" or api_secret == "[REVOKED]" else credential_fingerprint(api_key, api_secret)

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
        "masked_api_key": masked_key,
        "credential_fingerprint": fingerprint,
        "last_probe_status": row.last_probe_status,
        "last_probe_message": row.last_probe_message,
        "last_probe_meta": probe_meta,
        "permission_scope": permission_scope,
        "permission_scope_validation": permission_scope_validation,
        "lifecycle_status": _lifecycle_status(row),
        "secret_provider": secret_provider_name(),
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
    if _normalize_market_type(market_type) not in ALLOWED_MARKETS:
        raise ValueError("invalid_market_type")
    if environment not in ALLOWED_ENVS:
        raise ValueError("invalid_environment")
    if _normalize_purpose(purpose) not in ALLOWED_PURPOSES:
        raise ValueError("invalid_purpose")
    if exchange not in ALLOWED_EXCHANGES:
        raise ValueError("unsupported_exchange")


def list_admin_credentials(
    db: Session,
    *,
    exchange: str | None,
    market_type: str | None,
    purpose: str | None,
    environment: str | None,
    scope_type: str | None,
    approval_status: str | None,
    include_inactive: bool,
) -> list[dict]:
    query = db.query(AdminExchangeCredential)
    if exchange:
        query = query.filter(AdminExchangeCredential.exchange == _norm(exchange))
    if market_type:
        query = query.filter(AdminExchangeCredential.market_type.in_(_market_aliases(market_type)))
    if purpose:
        query = query.filter(AdminExchangeCredential.purpose.in_(_purpose_aliases(purpose)))
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
    normalized_market = _normalize_market_type(market_type)
    normalized_purpose = _normalize_purpose(purpose)
    normalized_env = _norm(environment)
    normalized_exchange = _norm(exchange)

    _validate_credential_payload(
        scope_type=normalized_scope,
        market_type=normalized_market,
        purpose=normalized_purpose,
        environment=normalized_env,
        exchange=normalized_exchange,
    )

    api_key_cipher = encrypt_secret_value(api_key)
    api_secret_cipher = encrypt_secret_value(api_secret)
    passphrase_cipher = encrypt_secret_value(passphrase or "") if passphrase else None
    _verify_secret_roundtrip(plain=api_key, encrypted=api_key_cipher)
    _verify_secret_roundtrip(plain=api_secret, encrypted=api_secret_cipher)
    if passphrase and passphrase_cipher:
        _verify_secret_roundtrip(plain=passphrase, encrypted=passphrase_cipher)

    row = AdminExchangeCredential(
        scope_type=normalized_scope,
        scope_id=(scope_id or None),
        exchange=normalized_exchange,
        market_type=normalized_market,
        purpose=normalized_purpose,
        environment=normalized_env,
        api_key_encrypted=api_key_cipher,
        api_secret_encrypted=api_secret_cipher,
        passphrase_encrypted=passphrase_cipher,
        base_url_override=(base_url_override or None),
        ip_binding_note=(ip_binding_note or None),
        is_active=False,
        is_default=bool(is_default),
        approval_status="pending",
        created_by=actor.id,
        updated_by=actor.id,
        created_at=_now(),
        updated_at=_now(),
        last_probe_meta={"lifecycle_status": "pending_verify", "read_back_verified": True},
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

    revoke_after_commit: list[str] = []

    if scope_type is not None:
        normalized_scope = _norm(scope_type)
        if normalized_scope not in ALLOWED_SCOPE_TYPES:
            raise ValueError("invalid_scope_type")
        row.scope_type = normalized_scope
    if scope_id is not None:
        row.scope_id = scope_id or None
    if purpose is not None:
        normalized_purpose = _normalize_purpose(purpose)
        if normalized_purpose not in ALLOWED_PURPOSES:
            raise ValueError("invalid_purpose")
        row.purpose = normalized_purpose
    if base_url_override is not None:
        row.base_url_override = base_url_override or None
    if ip_binding_note is not None:
        row.ip_binding_note = ip_binding_note or None
    if api_key is not None and str(api_key).strip():
        old_ref = row.api_key_encrypted
        cipher = encrypt_secret_value(api_key)
        _verify_secret_roundtrip(plain=api_key, encrypted=cipher)
        row.api_key_encrypted = cipher
        if old_ref and old_ref != cipher:
            revoke_after_commit.append(old_ref)
        row.approval_status = "pending"
        row.is_active = False
    if api_secret is not None and str(api_secret).strip():
        old_ref = row.api_secret_encrypted
        cipher = encrypt_secret_value(api_secret)
        _verify_secret_roundtrip(plain=api_secret, encrypted=cipher)
        row.api_secret_encrypted = cipher
        if old_ref and old_ref != cipher:
            revoke_after_commit.append(old_ref)
        row.approval_status = "pending"
        row.is_active = False
    if passphrase is not None:
        old_ref = row.passphrase_encrypted
        cipher = encrypt_secret_value(passphrase) if passphrase else None
        if passphrase and cipher:
            _verify_secret_roundtrip(plain=passphrase, encrypted=cipher)
        row.passphrase_encrypted = cipher
        if old_ref and old_ref != cipher:
            revoke_after_commit.append(old_ref)
        row.approval_status = "pending"
        row.is_active = False
    if is_default is not None:
        row.is_default = bool(is_default)
    if is_active is not None:
        row.is_active = bool(is_active)

    row.updated_by = actor.id
    row.updated_at = _now()
    meta = dict(row.last_probe_meta or {})
    meta["lifecycle_status"] = "pending_verify"
    meta["read_back_verified"] = True
    row.last_probe_meta = meta
    db.commit()
    db.refresh(row)

    for secret_ref in revoke_after_commit:
        try:
            revoke_secret_value(secret_ref)
        except Exception:  # noqa: BLE001
            continue
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
    meta = dict(row.last_probe_meta or {})
    meta["lifecycle_status"] = "approved"
    row.last_probe_meta = meta
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
    meta = dict(row.last_probe_meta or {})
    meta["lifecycle_status"] = "disabled"
    row.last_probe_meta = meta
    db.commit()
    db.refresh(row)
    return _serialize_admin_credential(row)


def revoke_admin_credential(db: Session, *, actor: User, credential_id: str) -> dict:
    row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == credential_id).first()
    if row is None:
        raise ValueError("credential_not_found")
    row.is_active = False
    row.approval_status = "revoked"
    row.updated_by = actor.id
    row.updated_at = _now()
    meta = dict(row.last_probe_meta or {})
    meta["lifecycle_status"] = "revoked"
    meta["revoked_at"] = _now().isoformat()
    row.last_probe_meta = meta
    db.commit()
    db.refresh(row)

    for secret_ref in [row.api_key_encrypted, row.api_secret_encrypted, row.passphrase_encrypted]:
        if not secret_ref:
            continue
        try:
            revoke_secret_value(secret_ref)
        except Exception:  # noqa: BLE001
            continue
    return _serialize_admin_credential(row)


def rotate_admin_credential(
    db: Session,
    *,
    actor: User,
    credential_id: str,
    api_key: str,
    api_secret: str,
    passphrase: str | None,
) -> dict:
    row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == credential_id).first()
    if row is None:
        raise ValueError("credential_not_found")
    if not str(api_key or "").strip() or not str(api_secret or "").strip():
        raise ValueError("invalid_rotation_payload")

    old_key_ref = row.api_key_encrypted
    old_secret_ref = row.api_secret_encrypted
    old_passphrase_ref = row.passphrase_encrypted

    api_key_cipher = rotate_secret_value(old_key_ref, api_key) if old_key_ref else encrypt_secret_value(api_key)
    api_secret_cipher = rotate_secret_value(old_secret_ref, api_secret) if old_secret_ref else encrypt_secret_value(api_secret)
    passphrase_cipher = (
        rotate_secret_value(old_passphrase_ref, passphrase)
        if passphrase and old_passphrase_ref
        else (encrypt_secret_value(passphrase) if passphrase else None)
    )
    _verify_secret_roundtrip(plain=api_key, encrypted=api_key_cipher)
    _verify_secret_roundtrip(plain=api_secret, encrypted=api_secret_cipher)
    if passphrase and passphrase_cipher:
        _verify_secret_roundtrip(plain=passphrase, encrypted=passphrase_cipher)

    row.api_key_encrypted = api_key_cipher
    row.api_secret_encrypted = api_secret_cipher
    row.passphrase_encrypted = passphrase_cipher
    row.is_active = False
    row.approval_status = "pending"
    row.approved_by = None
    row.approved_at = None
    row.last_probe_status = None
    row.last_probe_message = None
    row.last_probe_at = None
    row.updated_by = actor.id
    row.updated_at = _now()
    meta = dict(row.last_probe_meta or {})
    meta["lifecycle_status"] = "rotated_pending_verify"
    meta["rotated_at"] = _now().isoformat()
    meta["read_back_verified"] = True
    row.last_probe_meta = meta
    db.commit()
    db.refresh(row)

    if old_passphrase_ref and not passphrase:
        try:
            revoke_secret_value(old_passphrase_ref)
        except Exception:  # noqa: BLE001
            pass
    return _serialize_admin_credential(row)


def probe_admin_credential(db: Session, *, actor: User, credential_id: str) -> dict:
    row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == credential_id).first()
    if row is None:
        raise ValueError("credential_not_found")

    api_key = decrypt_secret_value(row.api_key_encrypted)
    api_secret = decrypt_secret_value(row.api_secret_encrypted)
    base_url = _effective_base_url(
        exchange=row.exchange,
        market_type=row.market_type,
        environment=row.environment,
        override=row.base_url_override,
    )
    if _base_url_environment_mismatch(environment=row.environment, base_url=base_url):
        row.last_probe_status = "env_mismatch"
        row.last_probe_message = "base_url_environment_mismatch"
        row.last_probe_meta = {
            "base_url": base_url,
            "permission_scope": {"read": False, "trade": False, "withdraw": False},
            "permission_scope_validation": {
                "status": "block",
                "reason_code": "environment_mismatch",
                "message": "credential environment ve route URL eşleşmiyor",
            },
            "lifecycle_status": "verify_failed",
        }
        row.last_probe_at = _now()
        row.updated_by = actor.id
        row.updated_at = _now()
        db.commit()
        db.refresh(row)
        return _serialize_admin_credential(row)

    proxy_headers = _proxy_headers_for_probe(exchange=row.exchange, market_type=row.market_type, environment=row.environment)

    try:
        if row.exchange == "binance" and row.market_type == "spot":
            status_code, message, meta = _spot_probe(
                base_url=base_url,
                api_key=api_key,
                api_secret=api_secret,
                extra_headers=proxy_headers,
            )
        elif row.exchange == "binance":
            status_code, message, meta = _futures_probe(
                base_url=base_url,
                api_key=api_key,
                api_secret=api_secret,
                extra_headers=proxy_headers,
            )
        elif row.exchange == "bybit":
            status_code, message, meta = _public_probe(
                base_url=base_url,
                endpoint="/v5/market/time",
                provider="bybit",
                extra_headers=proxy_headers,
            )
        elif row.exchange == "okx":
            status_code, message, meta = _public_probe(
                base_url=base_url,
                endpoint="/api/v5/public/time",
                provider="okx",
                extra_headers=proxy_headers,
            )
        else:
            status_code, message, meta = "probe_not_supported", "probe_not_supported_for_exchange", {
                "exchange": row.exchange
            }
    except Exception as exc:
        status_code, message, meta = "unreachable", "probe_exception", {"error": str(exc)}

    permission_scope = _permission_scope_from_meta(meta)
    scope_validation = _validate_permission_scope(purpose=row.purpose, permission_scope=permission_scope)
    if scope_validation["status"] == "block":
        status_code = "permission_restricted"
        message = scope_validation["reason_code"]

    row.last_probe_status = status_code
    row.last_probe_message = message
    row.last_probe_meta = {
        **(meta or {}),
        "base_url": base_url,
        "permission_scope": permission_scope,
        "permission_scope_validation": scope_validation,
        "lifecycle_status": "verified" if status_code in {"ready", "connectivity_only"} else "verify_failed",
        "verified_at": _now().isoformat(),
    }
    row.last_probe_at = _now()
    row.updated_by = actor.id
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _serialize_admin_credential(row)


def verify_admin_credential(db: Session, *, actor: User, credential_id: str) -> dict:
    row = probe_admin_credential(db, actor=actor, credential_id=credential_id)
    status = str(row.get("last_probe_status") or "")
    if status not in {"ready", "connectivity_only"}:
        raise ValueError("credential_verify_failed")
    return row


def list_assignment_rules(db: Session, *, exchange: str | None, market_type: str | None, environment: str | None) -> list[dict]:
    query = db.query(CredentialAssignmentRule)
    if exchange:
        query = query.filter(CredentialAssignmentRule.exchange == _norm(exchange))
    if market_type:
        query = query.filter(CredentialAssignmentRule.market_type.in_(_market_aliases(market_type)))
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
    normalized_market = _normalize_market_type(market_type)
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
            CredentialAssignmentRule.market_type.in_(_market_aliases(market_type)),
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
            UserExchangeConnection.market_type.in_(_market_aliases(market_type)),
            UserExchangeConnection.environment == environment,
        )
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )
    if row is None:
        return None
    api_key = decrypt_secret_value(row.api_key_encrypted)
    api_secret = decrypt_secret_value(row.api_secret_encrypted)
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
            AdminExchangeCredential.market_type.in_(_market_aliases(market_type)),
            AdminExchangeCredential.environment == environment,
            AdminExchangeCredential.is_active.is_(True),
            AdminExchangeCredential.approval_status == "approved",
        )
        .order_by(AdminExchangeCredential.is_default.desc(), AdminExchangeCredential.updated_at.desc())
    )
    rows = query.all()
    filtered = [row for row in rows if row.purpose in _purpose_aliases(purpose)]
    if not filtered:
        filtered = [row for row in rows if row.purpose in {"execution", "fallback", "execution_fallback", "market_data"}]

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
    permission_scope = _permission_scope_from_meta(row.last_probe_meta)
    scope_validation = _validate_permission_scope(purpose=purpose, permission_scope=permission_scope)
    if scope_validation["status"] == "block":
        return None

    api_key = decrypt_secret_value(row.api_key_encrypted)
    api_secret = decrypt_secret_value(row.api_secret_encrypted)
    if not api_key or not api_secret:
        return None
    base_url = _effective_base_url(
        exchange=exchange,
        market_type=market_type,
        environment=environment,
        override=row.base_url_override,
    )
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
            "permission_scope": permission_scope,
            "permission_scope_validation": scope_validation,
            "lifecycle_status": _lifecycle_status(row),
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
    symbol: str | None = None,
) -> dict:
    normalized_exchange = _norm(exchange)
    normalized_market = _normalize_market_type(market_type)
    normalized_env = _norm(environment)
    normalized_purpose = _normalize_purpose(purpose)
    if normalized_market not in ALLOWED_MARKETS:
        raise ValueError("invalid_market_type")
    if normalized_env not in ALLOWED_ENVS:
        raise ValueError("invalid_environment")

    if _is_execution_purpose(normalized_purpose):
        env_lock = _norm(os.environ.get("VENUE_ENV_LOCK"))
        if env_lock in {"testnet", "live"} and normalized_env != env_lock:
            raise ValueError("environment_lock_blocked")

        if normalized_env == "live":
            if _norm(os.environ.get("VENUE_PROD_FREEZE"), default="false") == "true":
                raise ValueError("prod_freeze_active")
            if _norm(os.environ.get("LIVE_ROUTE_APPROVED"), default="false") != "true":
                raise ValueError("live_route_not_approved")
            mode = _norm(os.environ.get("EXECUTION_MODE"), default="sim")
            if mode != "live":
                raise ValueError("mode_mismatch_live_blocked")

            from services.venue_control_plane_service import get_cached_venue_control_plane_sanity

            sanity_gate_required = _norm(os.environ.get("LIVE_SANITY_GATE_REQUIRED"), default="true") in {
                "1",
                "true",
                "yes",
            }
            if sanity_gate_required:
                sanity_result = get_cached_venue_control_plane_sanity()
                if not sanity_result or str(sanity_result.get("net_status") or "").upper() != "PASS":
                    raise ValueError("sanity_gate_blocked")

            canary_allowlist = [item.strip() for item in str(os.environ.get("LIVE_CANARY_ALLOWLIST_USER_IDS") or "").split(",") if item.strip()]
            if canary_allowlist and str(user_id) not in canary_allowlist:
                raise ValueError("canary_allowlist_blocked")

            two_step_required = _norm(os.environ.get("LIVE_TWO_STEP_APPROVAL_REQUIRED"), default="false") in {"1", "true", "yes"}
            if two_step_required:
                approved_users = [item.strip() for item in str(os.environ.get("LIVE_TWO_STEP_APPROVED_USER_IDS") or "").split(",") if item.strip()]
                if str(user_id) not in approved_users:
                    raise ValueError("two_step_approval_missing")

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

    if _is_execution_purpose(normalized_purpose):
        from services.venue_service import check_user_venue_access

        access_allowed, _, _, _ = check_user_venue_access(
            db,
            user_id=user_id,
            exchange=normalized_exchange,
            market_type=normalized_market,
            environment=normalized_env,
        )
        if not access_allowed:
            raise ValueError("venue_not_allowed")

        if normalized_env == "live" and str(selected.get("source") or "").startswith("user"):
            allow_live_user_source = _norm(os.environ.get("LIVE_USER_EXECUTION_SOURCE_ALLOWED"), default="false") in {
                "1",
                "true",
                "yes",
            }
            if not allow_live_user_source:
                raise ValueError("approved_credential_required")

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
    purpose: str = "execution",
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
