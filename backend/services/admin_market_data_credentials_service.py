import json
import base64
import hashlib
import hmac
import os
import time
from datetime import datetime, timezone

import httpx

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret, mask_secret
from models import AllowedMarket, ExchangeRegistry, ExternalProviderCredential, User, UserRole, UserVenueAssignment
from sqlalchemy import distinct, func
from services.live_mode_service import adapter
from services.venue_service import seed_binance_venue_registry


MARKET_DATA_PROVIDER_PREFIX = "market_data_global_live"
SUPPORTED_EXCHANGES = {"binance", "bybit", "okx"}
SUPPORTED_MARKETS = {"spot", "futures"}

DEFAULT_PAYLOAD = {
    "exchange": "binance",
    "market": "spot",
    "purpose": "market_data",
    "scope": "global",
    "environment": "live",
    "status": "inactive",
    "api_key": "",
    "api_secret": "",
    "api_passphrase": "",
    "base_url_override": "",
    "ip_route_note": "",
    "note": "",
    "auto_start_enabled": True,
    "last_error": "",
    "last_validated_at": None,
    "activated_at": None,
}


def _normalize(payload: dict | None) -> dict:
    merged = {**DEFAULT_PAYLOAD, **(payload or {})}
    exchange = str(merged.get("exchange") or "binance").strip().lower()
    market = str(merged.get("market") or "spot").strip().lower()
    if exchange not in SUPPORTED_EXCHANGES:
        exchange = "binance"
    if market not in SUPPORTED_MARKETS:
        market = "spot"
    return {
        "exchange": exchange,
        "market": market,
        "purpose": str(merged.get("purpose") or "market_data").strip().lower(),
        "scope": str(merged.get("scope") or "global").strip().lower(),
        "environment": "live",
        "status": str(merged.get("status") or "inactive").strip().lower(),
        "api_key": str(merged.get("api_key") or "").strip(),
        "api_secret": str(merged.get("api_secret") or "").strip(),
        "api_passphrase": str(merged.get("api_passphrase") or "").strip(),
        "base_url_override": str(merged.get("base_url_override") or "").strip(),
        "ip_route_note": str(merged.get("ip_route_note") or "").strip(),
        "note": str(merged.get("note") or "").strip(),
        "auto_start_enabled": bool(merged.get("auto_start_enabled", True)),
        "last_error": str(merged.get("last_error") or "").strip(),
        "last_validated_at": merged.get("last_validated_at"),
        "activated_at": merged.get("activated_at"),
    }


def _read_payload(row: ExternalProviderCredential | None) -> dict:
    if row is None or not row.api_key_encrypted:
        return dict(DEFAULT_PAYLOAD)
    decrypted = decrypt_exchange_secret(row.api_key_encrypted)
    if not decrypted:
        return dict(DEFAULT_PAYLOAD)
    try:
        parsed = json.loads(decrypted)
        if isinstance(parsed, dict):
            return _normalize(parsed)
    except Exception:
        return dict(DEFAULT_PAYLOAD)
    return dict(DEFAULT_PAYLOAD)


def _provider_for(exchange: str, market: str) -> str:
    return f"{exchange}_{market}_{MARKET_DATA_PROVIDER_PREFIX}"


def _row_for_provider(db, provider: str) -> ExternalProviderCredential:
    row = db.query(ExternalProviderCredential).filter(ExternalProviderCredential.provider == provider).first()
    if row is None:
        row = ExternalProviderCredential(provider=provider)
        db.add(row)
        db.flush()
    return row


def _validate_live_readonly(exchange: str, market: str, api_key: str, api_secret: str) -> tuple[bool, str]:
    if not api_key or not api_secret:
        return False, "api_key_and_api_secret_required"

    if exchange == "bybit":
        return _validate_bybit_live_readonly(api_key, api_secret)

    if exchange == "okx":
        return False, "okx_passphrase_required"

    try:
        if market == "futures":
            payload, status_code, _ = adapter.account_probe(api_key, api_secret)
        else:
            payload, status_code, _ = adapter.account_probe_spot(api_key, api_secret)
    except Exception as exc:
        return False, f"binance_probe_error:{exc}"

    if status_code == 200:
        return True, ""

    if isinstance(payload, dict):
        reason = str(payload.get("msg") or payload.get("code") or "binance_validation_failed")
    else:
        reason = "binance_validation_failed"
    return False, reason


def _validate_bybit_live_readonly(api_key: str, api_secret: str) -> tuple[bool, str]:
    base_url = str(os.environ.get("BYBIT_REST_URL") or "https://api.bybit.com").rstrip("/")
    endpoint = "/v5/account/wallet-balance"
    query = "accountType=UNIFIED"
    recv_window = "5000"
    timestamp = str(int(time.time() * 1000))
    sign_payload = f"{timestamp}{api_key}{recv_window}{query}"
    signature = hmac.new(api_secret.encode("utf-8"), sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    try:
        response = httpx.get(
            f"{base_url}{endpoint}?{query}",
            headers={
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN": signature,
            },
            timeout=10,
        )
    except Exception as exc:
        return False, f"bybit_probe_error:{exc}"

    payload = response.json() if response.content else {}
    if response.status_code == 200 and str(payload.get("retCode", "")) == "0":
        return True, ""
    reason = str(payload.get("retMsg") or payload.get("retCode") or f"http_{response.status_code}")
    return False, f"bybit_validation_failed:{reason}"


def _validate_okx_live_readonly(api_key: str, api_secret: str, api_passphrase: str) -> tuple[bool, str]:
    if not api_passphrase:
        return False, "okx_passphrase_required"
    base_url = str(os.environ.get("OKX_REST_URL") or "https://www.okx.com").rstrip("/")
    endpoint = "/api/v5/account/balance"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    prehash = f"{timestamp}GET{endpoint}"
    signature = base64.b64encode(
        hmac.new(api_secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    try:
        response = httpx.get(
            f"{base_url}{endpoint}",
            headers={
                "OK-ACCESS-KEY": api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": api_passphrase,
            },
            timeout=10,
        )
    except Exception as exc:
        return False, f"okx_probe_error:{exc}"

    payload = response.json() if response.content else {}
    if response.status_code == 200 and str(payload.get("code", "")) == "0":
        return True, ""
    reason = str(payload.get("msg") or payload.get("code") or f"http_{response.status_code}")
    return False, f"okx_validation_failed:{reason}"


def _validate_live_readonly_with_passphrase(
    exchange: str,
    market: str,
    api_key: str,
    api_secret: str,
    api_passphrase: str,
) -> tuple[bool, str]:
    if exchange == "okx":
        return _validate_okx_live_readonly(api_key, api_secret, api_passphrase)
    return _validate_live_readonly(exchange, market, api_key, api_secret)


def _ensure_global_live_distribution(db, *, exchange: str, market: str) -> dict:
    try:
        if exchange == "binance":
            seed_binance_venue_registry(db)
    except Exception:
        # Registry satırını aşağıda garanti ediyoruz; seed başarısız olsa da akış devam eder.
        pass

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange).first()
    if exchange_row is None:
        exchange_row = ExchangeRegistry(
            exchange_code=exchange,
            exchange_name=exchange.upper(),
            status="active",
            supported_market_types=[market],
            supports_testnet=False,
            supports_live=True,
            health_status="healthy",
            rate_limit_status="ok",
            adapter_version="v1",
        )
        db.add(exchange_row)
    else:
        exchange_row.status = "active"
        exchange_row.supports_live = True
        exchange_row.supports_testnet = False
        exchange_row.health_status = "healthy"
        exchange_row.rate_limit_status = "ok"
        supported = set(exchange_row.supported_market_types or [])
        supported.add(market)
        exchange_row.supported_market_types = sorted(supported)
        exchange_row.updated_at = datetime.now(timezone.utc)

    allowed_market = (
        db.query(AllowedMarket)
        .filter(AllowedMarket.exchange_code == exchange, AllowedMarket.market_type == market, AllowedMarket.environment == "live")
        .first()
    )
    if allowed_market is None:
        allowed_market = AllowedMarket(exchange_code=exchange, market_type=market, environment="live", enabled=True)
        db.add(allowed_market)
    else:
        allowed_market.enabled = True
        allowed_market.updated_at = datetime.now(timezone.utc)

    users = db.query(User).filter(User.role == UserRole.USER, User.is_active.is_(True), User.approval_status == "approved").all()
    created = 0
    updated = 0
    for user in users:
        assignment = (
            db.query(UserVenueAssignment)
            .filter(UserVenueAssignment.user_id == user.id, UserVenueAssignment.exchange_code == exchange)
            .first()
        )
        if assignment is None:
            assignment = UserVenueAssignment(user_id=user.id, exchange_code=exchange)
            db.add(assignment)
            created += 1
        else:
            updated += 1

        if market == "spot":
            assignment.spot_allowed = True
        if market == "futures":
            assignment.futures_allowed = True
        assignment.live_allowed = True
        assignment.testnet_allowed = False
        assignment.updated_at = datetime.now(timezone.utc)

    return {
        "active_user_count": len(users),
        "assignments_created": created,
        "assignments_updated": updated,
    }


def get_market_data_keys_summary(db) -> dict:
    rows = (
        db.query(ExternalProviderCredential)
        .filter(ExternalProviderCredential.provider.like(f"%_{MARKET_DATA_PROVIDER_PREFIX}"))
        .order_by(ExternalProviderCredential.updated_at.desc())
        .all()
    )

    active_user_count = (
        db.query(User)
        .filter(User.role == UserRole.USER, User.is_active.is_(True), User.approval_status == "approved")
        .count()
    )
    users_with_live_distribution = (
        db.query(UserVenueAssignment)
        .filter(UserVenueAssignment.live_allowed.is_(True), (UserVenueAssignment.spot_allowed.is_(True) | UserVenueAssignment.futures_allowed.is_(True)))
        .with_entities(func.count(distinct(UserVenueAssignment.user_id)))
        .scalar()
    )

    items = []
    has_active = False
    for row in rows:
        payload = _read_payload(row)
        if not payload.get("api_key"):
            continue
        is_active = payload.get("status") == "active" and bool(payload.get("api_key") and payload.get("api_secret"))
        has_active = has_active or is_active
        items.append(
            {
                "provider": row.provider,
                "exchange": payload.get("exchange") or "binance",
                "market": payload.get("market") or "spot",
                "purpose": payload.get("purpose") or "market_data",
                "scope": payload.get("scope") or "global",
                "environment": "live",
                "status": "active" if is_active else (payload.get("status") or "inactive"),
                "api_key_masked": mask_secret(payload.get("api_key") or ""),
                "has_api_passphrase": bool(payload.get("api_passphrase")),
                "note": payload.get("note") or "",
                "base_url_override": payload.get("base_url_override") or "",
                "ip_route_note": payload.get("ip_route_note") or "",
                "auto_start_enabled": bool(payload.get("auto_start_enabled", True)),
                "last_error": payload.get("last_error") or "",
                "last_validated_at": payload.get("last_validated_at"),
                "activated_at": payload.get("activated_at"),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )

    return {
        "active_key": has_active,
        "items": items,
        "users_with_live_distribution": users_with_live_distribution,
        "active_user_count": active_user_count,
    }


def upsert_market_data_key(db, payload: dict) -> dict:
    incoming = _normalize(payload or {})
    exchange = incoming.get("exchange") or "binance"
    market = incoming.get("market") or "spot"
    provider = _provider_for(exchange, market)

    row = _row_for_provider(db, provider)
    current = _read_payload(row)
    merged = _normalize({**current, **incoming})

    api_key = merged.get("api_key") or ""
    api_secret = merged.get("api_secret") or ""
    api_passphrase = merged.get("api_passphrase") or ""
    is_valid, reason = _validate_live_readonly_with_passphrase(exchange, market, api_key, api_secret, api_passphrase)
    if not is_valid:
        raise ValueError(reason)

    now_iso = datetime.now(timezone.utc).isoformat()
    merged["status"] = "active"
    merged["note"] = merged.get("note") or "credential_saved"
    merged["last_error"] = ""
    merged["last_validated_at"] = now_iso
    merged["activated_at"] = now_iso
    merged["environment"] = "live"
    merged["scope"] = "global"
    merged["purpose"] = "market_data"
    merged["market"] = market
    merged["exchange"] = exchange
    merged["auto_start_enabled"] = True

    row.api_key_encrypted = encrypt_exchange_secret(json.dumps(merged, ensure_ascii=False))
    row.updated_at = datetime.now(timezone.utc)

    distribution = _ensure_global_live_distribution(db, exchange=exchange, market=market)
    db.commit()
    db.refresh(row)

    summary = get_market_data_keys_summary(db)
    summary["distribution"] = distribution
    return summary
