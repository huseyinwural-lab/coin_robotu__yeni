import json
from datetime import datetime, timezone

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret, mask_secret
from models import AllowedMarket, ExchangeRegistry, ExternalProviderCredential, User, UserRole, UserVenueAssignment
from services.live_mode_service import adapter
from services.venue_service import seed_binance_venue_registry


BINANCE_MARKET_DATA_PROVIDER = "binance_market_data_global_live_v1"

DEFAULT_PAYLOAD = {
    "exchange": "binance",
    "market": "spot",
    "purpose": "market_data",
    "scope": "global",
    "environment": "live",
    "status": "inactive",
    "api_key": "",
    "api_secret": "",
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
    return {
        "exchange": str(merged.get("exchange") or "binance").strip().lower(),
        "market": str(merged.get("market") or "spot").strip().lower(),
        "purpose": str(merged.get("purpose") or "market_data").strip().lower(),
        "scope": str(merged.get("scope") or "global").strip().lower(),
        "environment": "live",
        "status": str(merged.get("status") or "inactive").strip().lower(),
        "api_key": str(merged.get("api_key") or "").strip(),
        "api_secret": str(merged.get("api_secret") or "").strip(),
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


def _row_for_provider(db) -> ExternalProviderCredential:
    row = db.query(ExternalProviderCredential).filter(ExternalProviderCredential.provider == BINANCE_MARKET_DATA_PROVIDER).first()
    if row is None:
        row = ExternalProviderCredential(provider=BINANCE_MARKET_DATA_PROVIDER)
        db.add(row)
        db.flush()
    return row


def _validate_binance_live_readonly(api_key: str, api_secret: str) -> tuple[bool, str]:
    if not api_key or not api_secret:
        return False, "api_key_and_api_secret_required"
    try:
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


def _ensure_global_live_distribution(db) -> dict:
    seed_binance_venue_registry(db)

    exchange = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == "binance").first()
    if exchange is not None:
        exchange.status = "active"
        exchange.supports_live = True
        exchange.supports_testnet = False
        exchange.health_status = "healthy"
        exchange.rate_limit_status = "ok"
        exchange.updated_at = datetime.now(timezone.utc)

    allowed_market = (
        db.query(AllowedMarket)
        .filter(AllowedMarket.exchange_code == "binance", AllowedMarket.market_type == "spot", AllowedMarket.environment == "live")
        .first()
    )
    if allowed_market is None:
        allowed_market = AllowedMarket(exchange_code="binance", market_type="spot", environment="live", enabled=True)
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
            .filter(UserVenueAssignment.user_id == user.id, UserVenueAssignment.exchange_code == "binance")
            .first()
        )
        if assignment is None:
            assignment = UserVenueAssignment(user_id=user.id, exchange_code="binance")
            db.add(assignment)
            created += 1
        else:
            updated += 1

        assignment.spot_allowed = True
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
    row = db.query(ExternalProviderCredential).filter(ExternalProviderCredential.provider == BINANCE_MARKET_DATA_PROVIDER).first()
    payload = _read_payload(row)
    has_active = bool(payload.get("status") == "active" and payload.get("api_key") and payload.get("api_secret"))

    active_user_count = (
        db.query(User)
        .filter(User.role == UserRole.USER, User.is_active.is_(True), User.approval_status == "approved")
        .count()
    )
    users_with_live_distribution = (
        db.query(UserVenueAssignment)
        .filter(UserVenueAssignment.exchange_code == "binance", UserVenueAssignment.live_allowed.is_(True), UserVenueAssignment.spot_allowed.is_(True))
        .count()
    )

    items = []
    if row is not None and payload.get("api_key"):
        items.append(
            {
                "provider": BINANCE_MARKET_DATA_PROVIDER,
                "exchange": payload.get("exchange") or "binance",
                "market": payload.get("market") or "spot",
                "purpose": payload.get("purpose") or "market_data",
                "scope": payload.get("scope") or "global",
                "environment": "live",
                "status": payload.get("status") or "inactive",
                "api_key_masked": mask_secret(payload.get("api_key") or ""),
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
    row = _row_for_provider(db)
    current = _read_payload(row)
    merged = _normalize({**current, **(payload or {})})

    api_key = merged.get("api_key") or ""
    api_secret = merged.get("api_secret") or ""
    is_valid, reason = _validate_binance_live_readonly(api_key, api_secret)
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
    merged["market"] = "spot"
    merged["exchange"] = "binance"
    merged["auto_start_enabled"] = True

    row.api_key_encrypted = encrypt_exchange_secret(json.dumps(merged, ensure_ascii=False))
    row.updated_at = datetime.now(timezone.utc)

    distribution = _ensure_global_live_distribution(db)
    db.commit()
    db.refresh(row)

    summary = get_market_data_keys_summary(db)
    summary["distribution"] = distribution
    return summary
