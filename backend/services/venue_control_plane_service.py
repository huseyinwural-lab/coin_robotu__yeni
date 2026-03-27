from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from core.users.user_exchange_connector import credential_fingerprint
from models import AdminExchangeCredential, AllowedMarket, ExchangeCapability, ExchangeRegistry
from services.secret_provider_service import decrypt_secret_value


CACHE_PATH = Path(os.environ.get("VENUE_SANITY_CACHE_PATH") or "/tmp/venue_control_plane_sanity.json")


def _status_rank(value: str) -> int:
    normalized = str(value or "pass").strip().lower()
    if normalized == "block":
        return 2
    if normalized == "warn":
        return 1
    return 0


def _base_url_environment_mismatch(environment: str, base_url: str | None) -> bool:
    url = str(base_url or "").lower()
    env = str(environment or "").lower()
    if not url:
        return False
    if env == "live" and "testnet" in url:
        return True
    if env == "testnet" and "testnet" not in url and any(part in url for part in ["binance.com", "bybit.com", "okx.com"]):
        return True
    return False


def _check(name: str, status: str, reason_code: str, severity: str, remediation_suggestions: list[str], details: dict | None = None) -> dict:
    return {
        "name": name,
        "status": str(status).upper(),
        "reason_code": str(reason_code or "ok"),
        "severity": str(severity or "low").lower(),
        "remediation_suggestions": remediation_suggestions or [],
        "details": details or {},
    }


def _save_cache(payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False))


def get_cached_venue_control_plane_sanity() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:  # noqa: BLE001
        return None


def run_venue_control_plane_sanity(db: Session) -> dict:
    checks: list[dict] = []

    credentials = db.query(AdminExchangeCredential).all()
    active_credentials = [row for row in credentials if bool(row.is_active)]

    if not active_credentials:
        checks.append(_check("credential_validity", "BLOCK", "missing_active_credentials", "high", ["En az bir active credential tanımlayın ve verify+approve edin."]))
    else:
        bad_probe = [row for row in active_credentials if str(row.last_probe_status or "no_probe") not in {"ready", "connectivity_only"}]
        if bad_probe:
            checks.append(_check("credential_validity", "WARN", "credential_probe_not_ready", "medium", ["Probe başarısız credential’ları verify edin veya revoke edin."], {"affected_credential_ids": [row.id for row in bad_probe][:20]}))
        else:
            checks.append(_check("credential_validity", "PASS", "credential_probe_ready", "low", []))

    scope_reasons: list[str] = []
    execution_creds = [row for row in active_credentials if str(row.purpose or "") in {"execution", "fallback", "execution_fallback"}]
    for row in execution_creds:
        scope = dict((row.last_probe_meta or {}).get("permission_scope") or {})
        if bool(scope.get("withdraw", False)):
            scope_reasons.append("withdraw_scope_detected")
        if not bool(scope.get("trade", False)):
            scope_reasons.append("missing_trade_scope")
    if scope_reasons:
        checks.append(_check("permission_scope", "BLOCK", sorted(set(scope_reasons))[0], "high", ["Execution credential scope’unu read+trade ile sınırlandırın, withdraw yetkisini kaldırın."], {"reason_codes": sorted(set(scope_reasons))}))
    else:
        checks.append(_check("permission_scope", "PASS", "permission_scope_ok", "low", []))

    env_mismatch_rows = [row.id for row in active_credentials if _base_url_environment_mismatch(row.environment, row.base_url_override)]
    if env_mismatch_rows:
        checks.append(_check("environment_match", "BLOCK", "credential_environment_mismatch", "high", ["base_url_override alanlarını environment ile eşleştirin."], {"affected_credential_ids": env_mismatch_rows[:20]}))
    else:
        checks.append(_check("environment_match", "PASS", "environment_match_ok", "low", []))

    registry_rows = db.query(ExchangeRegistry).all()
    registry_map = {f"{row.exchange_code}": row for row in registry_rows}
    availability_reasons: list[str] = []
    for row in active_credentials:
        registry = registry_map.get(str(row.exchange))
        if registry is None:
            availability_reasons.append("exchange_registry_missing")
            continue
        if str(registry.status or "") != "active":
            availability_reasons.append("exchange_disabled")
        if str(registry.health_status or "") == "down":
            availability_reasons.append("exchange_health_down")
    if availability_reasons:
        checks.append(_check("venue_availability", "BLOCK", sorted(set(availability_reasons))[0], "high", ["Exchange registry status/health alanlarını düzeltin."], {"reason_codes": sorted(set(availability_reasons))}))
    else:
        checks.append(_check("venue_availability", "PASS", "venue_availability_ok", "low", []))

    capability_rows = db.query(ExchangeCapability).all()
    capability_keys = {f"{row.exchange_code}:{row.market_type}" for row in capability_rows}
    missing_caps = []
    for row in active_credentials:
        market = "futures" if row.market_type in {"usdt_perp", "coin_perp"} else row.market_type
        key = f"{row.exchange}:{market}"
        if key not in capability_keys:
            missing_caps.append(key)
    if missing_caps:
        checks.append(_check("capability_match", "BLOCK", "capability_missing", "high", ["Eksik exchange/market capability kayıtlarını oluşturun."], {"missing_capabilities": sorted(set(missing_caps))}))
    else:
        checks.append(_check("capability_match", "PASS", "capability_match_ok", "low", []))

    allowed_rows = db.query(AllowedMarket).filter(AllowedMarket.enabled.is_(True)).all()
    allowed_keys = {f"{row.exchange_code}:{row.market_type}:{row.environment}" for row in allowed_rows}
    blocked_allowed = []
    for row in active_credentials:
        market = "futures" if row.market_type in {"usdt_perp", "coin_perp"} else row.market_type
        key = f"{row.exchange}:{market}:{row.environment}"
        if key not in allowed_keys:
            blocked_allowed.append(key)
    if blocked_allowed:
        checks.append(_check("allowed_market_state", "BLOCK", "allowed_market_missing", "high", ["Allowed market policy’ye exchange/market/environment ekleyin veya credential’ı disable edin."], {"missing_allowed_markets": sorted(set(blocked_allowed))}))
    else:
        checks.append(_check("allowed_market_state", "PASS", "allowed_market_ok", "low", []))

    same_fingerprint_conflicts = []
    grouped = defaultdict(set)
    for row in active_credentials:
        try:
            key = decrypt_secret_value(row.api_key_encrypted)
            secret = decrypt_secret_value(row.api_secret_encrypted)
            fp = credential_fingerprint(key, secret)
        except Exception:  # noqa: BLE001
            continue
        grouped[f"{row.exchange}:{row.market_type}:{fp}"].add(str(row.environment))
    for identity, envs in grouped.items():
        if {"live", "testnet"}.issubset(envs):
            same_fingerprint_conflicts.append(identity)
    if same_fingerprint_conflicts:
        checks.append(_check("live_testnet_conflict", "WARN", "live_testnet_credential_conflict", "medium", ["Live ve testnet için farklı key setleri kullanın."], {"conflicts": same_fingerprint_conflicts[:20]}))
    else:
        checks.append(_check("live_testnet_conflict", "PASS", "live_testnet_conflict_free", "low", []))

    default_counter = defaultdict(int)
    for row in active_credentials:
        if row.purpose not in {"execution", "fallback", "execution_fallback"}:
            continue
        if bool(row.is_default):
            key = f"{row.exchange}:{row.market_type}:{row.environment}:{row.purpose}"
            default_counter[key] += 1
    multiple_defaults = [key for key, count in default_counter.items() if count > 1]
    if multiple_defaults:
        checks.append(_check("default_route_consistency", "BLOCK", "multiple_default_credentials", "high", ["Her exchange/market/environment/purpose kombinasyonunda tek default credential bırakın."], {"multiple_defaults": multiple_defaults}))
    else:
        checks.append(_check("default_route_consistency", "PASS", "default_route_consistent", "low", []))

    highest = max((_status_rank(item.get("status")) for item in checks), default=0)
    net_status = "PASS" if highest == 0 else ("WARN" if highest == 1 else "BLOCK")
    reason_codes = sorted({str(item.get("reason_code") or "ok") for item in checks if str(item.get("reason_code") or "ok") != "ok"})
    remediation_suggestions = sorted({s for item in checks for s in (item.get("remediation_suggestions") or [])})

    return {
        "net_status": net_status,
        "reason_codes": reason_codes,
        "remediation_suggestions": remediation_suggestions,
        "checks": checks,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def run_and_cache_venue_control_plane_sanity(db: Session) -> dict:
    result = run_venue_control_plane_sanity(db)
    _save_cache(result)
    return result
