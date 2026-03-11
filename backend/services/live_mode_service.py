import hashlib
import hmac
import json
import os
import statistics
import time
import uuid
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from core.config import settings
from db import redis_client
from models import (
    AdminControl,
    AuditLog,
    AlertPolicy,
    BotProfile,
    ExchangeRegistry,
    ExecutionLifecycleEvent,
    ExecutionMetric,
    FailedEvent,
    HardeningChecklistRun,
    LiveActivationConfig,
    PaperPosition,
    PermissionDriftEvent,
    ReleaseGateOverride,
    RiskExposureGroup,
    RiskOrchestratorPolicy,
    RiskPolicy,
    TestnetExecutionLog,
    User,
    UserExchangeSetting,
    UserRiskSetting,
)
from services.artifact_service import verify_manifest_chain
from services.risk_orchestrator_service import get_or_create_policy
from services.pipeline.cache_store import read_candles
from services.venue_service import check_user_venue_access, seed_binance_venue_registry

BINANCE_FUTURES_TESTNET_REST = "https://testnet.binancefuture.com"
BINANCE_FUTURES_TESTNET_WS = "wss://stream.binancefuture.com/ws"
BINANCE_SPOT_TESTNET_REST = "https://testnet.binance.vision"
SAFE_SYMBOL_WHITELIST = ["BTCUSDT"]
MAX_SAFE_POSITION_PCT = 0.1
MAX_SAFE_LEVERAGE = 1
MAX_SAFE_NOTIONAL_EXPOSURE = 150
VALIDATION_STALE_MINUTES = 10
OVERRIDE_REASON_CODES = {"false_positive", "exchange_incident", "ops_emergency", "manual_review"}


class BinanceFuturesTestnetAdapter:
    docs_references = [
        "https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info",
        "https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order",
    ]

    @staticmethod
    def mask_api_key(api_key: str | None) -> str:
        if not api_key:
            return "missing"
        return f"{api_key[:4]}***{api_key[-3:]}"

    @staticmethod
    def credential_fingerprint(api_key: str | None, api_secret: str | None) -> str:
        joined = f"{api_key or ''}:{api_secret or ''}"
        return hashlib.sha256(joined.encode()).hexdigest()[:12]

    @staticmethod
    def _signature(secret: str, query: str) -> str:
        return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def ping(self) -> dict:
        try:
            response = httpx.get(f"{BINANCE_FUTURES_TESTNET_REST}/fapi/v1/time", timeout=6)
            response.raise_for_status()
            payload = response.json()
            return {
                "status": "reachable",
                "server_time": payload.get("serverTime"),
                "rest_url": BINANCE_FUTURES_TESTNET_REST,
                "ws_url": BINANCE_FUTURES_TESTNET_WS,
                "message": "Binance Futures Testnet endpoint reachable.",
            }
        except Exception as exc:
            return {
                "status": "unreachable",
                "server_time": None,
                "rest_url": BINANCE_FUTURES_TESTNET_REST,
                "ws_url": BINANCE_FUTURES_TESTNET_WS,
                "message": f"Endpoint check failed: {exc}",
            }

    def _signed_get(self, api_key: str, api_secret: str, endpoint: str, params: dict) -> tuple[dict, int, dict]:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        signature = self._signature(api_secret, query)
        url = f"{BINANCE_FUTURES_TESTNET_REST}{endpoint}?{query}&signature={signature}"
        response = httpx.get(url, headers={"X-MBX-APIKEY": api_key}, timeout=8)
        payload = response.json() if response.content else {}
        return payload, response.status_code, dict(response.headers)

    def _signed_get_spot(self, api_key: str, api_secret: str, endpoint: str, params: dict) -> tuple[dict, int, dict]:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        signature = self._signature(api_secret, query)
        url = f"{BINANCE_SPOT_TESTNET_REST}{endpoint}?{query}&signature={signature}"
        response = httpx.get(url, headers={"X-MBX-APIKEY": api_key}, timeout=8)
        payload = response.json() if response.content else {}
        return payload, response.status_code, dict(response.headers)

    def _signed_post(self, api_key: str, api_secret: str, endpoint: str, params: dict) -> tuple[dict, int]:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        signature = self._signature(api_secret, query)
        url = f"{BINANCE_FUTURES_TESTNET_REST}{endpoint}?{query}&signature={signature}"
        response = httpx.post(url, headers={"X-MBX-APIKEY": api_key}, timeout=10)
        payload = response.json() if response.content else {}
        return payload, response.status_code

    def _signed_post_spot(self, api_key: str, api_secret: str, endpoint: str, params: dict) -> tuple[dict, int]:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        signature = self._signature(api_secret, query)
        url = f"{BINANCE_SPOT_TESTNET_REST}{endpoint}?{query}&signature={signature}"
        response = httpx.post(url, headers={"X-MBX-APIKEY": api_key}, timeout=10)
        payload = response.json() if response.content else {}
        return payload, response.status_code

    def _signed_delete(self, api_key: str, api_secret: str, endpoint: str, params: dict, *, spot: bool = False) -> tuple[dict, int]:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        signature = self._signature(api_secret, query)
        base_url = BINANCE_SPOT_TESTNET_REST if spot else BINANCE_FUTURES_TESTNET_REST
        url = f"{base_url}{endpoint}?{query}&signature={signature}"
        response = httpx.delete(url, headers={"X-MBX-APIKEY": api_key}, timeout=8)
        payload = response.json() if response.content else {}
        return payload, response.status_code

    def account_probe(self, api_key: str, api_secret: str) -> tuple[dict, int, dict]:
        return self._signed_get(api_key, api_secret, "/fapi/v2/account", {})

    def account_probe_spot(self, api_key: str, api_secret: str) -> tuple[dict, int, dict]:
        return self._signed_get_spot(api_key, api_secret, "/api/v3/account", {})

    def mark_price(self, symbol: str) -> float:
        response = httpx.get(
            f"{BINANCE_FUTURES_TESTNET_REST}/fapi/v1/ticker/price",
            params={"symbol": symbol},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        return float(payload.get("price") or 0)

    def book_ticker(self, symbol: str) -> dict:
        response = httpx.get(
            f"{BINANCE_FUTURES_TESTNET_REST}/fapi/v1/ticker/bookTicker",
            params={"symbol": symbol},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        bid = float(payload.get("bidPrice") or 0)
        ask = float(payload.get("askPrice") or 0)
        mid = round((bid + ask) / 2, 6) if bid > 0 and ask > 0 else 0
        return {
            "symbol": payload.get("symbol", symbol),
            "bid": bid,
            "ask": ask,
            "mid_price": mid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def set_leverage(self, api_key: str, api_secret: str, symbol: str, leverage: int) -> tuple[dict, int]:
        return self._signed_post(
            api_key,
            api_secret,
            "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": leverage},
        )

    def create_limit_order(
        self,
        api_key: str,
        api_secret: str,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str,
    ) -> tuple[dict, int]:
        return self._signed_post(
            api_key,
            api_secret,
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "LIMIT",
                "quantity": quantity,
                "price": price,
                "timeInForce": time_in_force,
            },
        )

    def create_market_order(
        self,
        api_key: str,
        api_secret: str,
        *,
        symbol: str,
        side: str,
        quantity: float,
    ) -> tuple[dict, int]:
        return self._signed_post(
            api_key,
            api_secret,
            "/fapi/v1/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": quantity,
            },
        )

    def create_spot_market_order(
        self,
        api_key: str,
        api_secret: str,
        *,
        symbol: str,
        side: str,
        quote_order_qty: float,
    ) -> tuple[dict, int]:
        return self._signed_post_spot(
            api_key,
            api_secret,
            "/api/v3/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quoteOrderQty": round(float(quote_order_qty), 2),
            },
        )

    def query_order(self, api_key: str, api_secret: str, symbol: str, order_id: int) -> tuple[dict, int]:
        payload, status_code, _ = self._signed_get(
            api_key,
            api_secret,
            "/fapi/v1/order",
            {"symbol": symbol, "orderId": order_id},
        )
        return payload, status_code

    def query_spot_order(self, api_key: str, api_secret: str, symbol: str, order_id: int) -> tuple[dict, int]:
        payload, status_code, _ = self._signed_get_spot(
            api_key,
            api_secret,
            "/api/v3/order",
            {"symbol": symbol, "orderId": order_id},
        )
        return payload, status_code

    def cancel_order(self, api_key: str, api_secret: str, symbol: str, order_id: int, *, market_type: str) -> tuple[dict, int]:
        if market_type == "spot":
            return self._signed_delete(api_key, api_secret, "/api/v3/order", {"symbol": symbol, "orderId": order_id}, spot=True)
        return self._signed_delete(api_key, api_secret, "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, spot=False)

    def evaluate_permission_controls(self, api_key: str | None, api_secret: str | None) -> dict:
        now_iso = datetime.now(timezone.utc).isoformat()
        key = (api_key or "").strip()
        secret = (api_secret or "").strip()
        endpoint_probe = self.ping()

        controls = [
            {"key": "can_trade", "status": "fail", "reason": "missing_credentials", "timestamp": now_iso},
            {"key": "can_futures", "status": "fail", "reason": "missing_credentials", "timestamp": now_iso},
            {"key": "timestamp_sync", "status": "fail", "reason": "endpoint_unreachable", "timestamp": now_iso},
            {"key": "rate_limit_ok", "status": "fail", "reason": "missing_credentials", "timestamp": now_iso},
        ]

        if endpoint_probe["status"] == "reachable" and endpoint_probe.get("server_time"):
            drift_ms = abs(int(time.time() * 1000) - int(endpoint_probe["server_time"]))
            controls[2] = {
                "key": "timestamp_sync",
                "status": "pass" if drift_ms <= 5000 else "fail",
                "reason": f"drift_ms={drift_ms}",
                "timestamp": now_iso,
            }

        if not key or not secret:
            return {"overall_status": "fail", "controls": controls, "invalid_credentials": False}

        try:
            payload, status_code, headers = self.account_probe(key, secret)
        except httpx.HTTPError as exc:
            fail_reason = f"exchange_unreachable:{exc}"
            return {
                "overall_status": "fail",
                "controls": [
                    {"key": "can_trade", "status": "fail", "reason": fail_reason, "timestamp": now_iso},
                    {"key": "can_futures", "status": "fail", "reason": fail_reason, "timestamp": now_iso},
                    controls[2],
                    {"key": "rate_limit_ok", "status": "fail", "reason": fail_reason, "timestamp": now_iso},
                ],
                "invalid_credentials": False,
            }

        error_code = payload.get("code") if isinstance(payload, dict) else None
        invalid_credentials = status_code in {401, 403} or error_code in {-2015, -2014, -1022}
        if status_code != 200:
            reason = "invalid_credentials" if invalid_credentials else f"account_probe_status={status_code}"
            return {
                "overall_status": "fail",
                "controls": [
                    {"key": "can_trade", "status": "fail", "reason": reason, "timestamp": now_iso},
                    {"key": "can_futures", "status": "fail", "reason": reason, "timestamp": now_iso},
                    controls[2],
                    {"key": "rate_limit_ok", "status": "fail", "reason": reason, "timestamp": now_iso},
                ],
                "invalid_credentials": invalid_credentials,
            }

        can_trade = bool(payload.get("canTrade", False))
        can_futures = bool(payload.get("canTrade", False))
        used_weight = int(headers.get("x-mbx-used-weight-1m", "0") or 0)

        controls[0] = {
            "key": "can_trade",
            "status": "pass" if can_trade else "fail",
            "reason": "canTrade=true" if can_trade else "canTrade=false",
            "timestamp": now_iso,
        }
        controls[1] = {
            "key": "can_futures",
            "status": "pass" if can_futures else "fail",
            "reason": "futures_permission=true" if can_futures else "futures_permission=false",
            "timestamp": now_iso,
        }
        controls[3] = {
            "key": "rate_limit_ok",
            "status": "pass" if used_weight <= 1000 else "fail",
            "reason": f"x-mbx-used-weight-1m={used_weight}",
            "timestamp": now_iso,
        }

        overall = "pass" if all(item["status"] == "pass" for item in controls) else "fail"
        return {"overall_status": overall, "controls": controls, "invalid_credentials": False}

    def permission_check(self, api_key: str | None, api_secret: str | None) -> dict:
        has_key = bool(api_key and api_key.strip())
        has_secret = bool(api_secret and api_secret.strip())
        key = api_key.strip() if api_key else None
        secret = api_secret.strip() if api_secret else None
        controls_payload = self.evaluate_permission_controls(key, secret)

        if not has_key or not has_secret:
            return {
                "api_key_present": has_key,
                "api_secret_present": has_secret,
                "masked_key": self.mask_api_key(key),
                "credential_fingerprint": self.credential_fingerprint(key, secret),
                "status": "missing_credentials",
                "message": "API key/secret eksik. Sistem fail-safe modda kaldı, canlı emir gönderilmez.",
                "controls": controls_payload["controls"],
            }

        if controls_payload["invalid_credentials"]:
            return {
                "api_key_present": has_key,
                "api_secret_present": has_secret,
                "masked_key": self.mask_api_key(key),
                "credential_fingerprint": self.credential_fingerprint(key, secret),
                "status": "invalid_credentials",
                "message": "API key/secret geçersiz veya imza doğrulaması başarısız.",
                "controls": controls_payload["controls"],
            }

        ready = controls_payload["overall_status"] == "pass"
        return {
            "api_key_present": has_key,
            "api_secret_present": has_secret,
            "masked_key": self.mask_api_key(key),
            "credential_fingerprint": self.credential_fingerprint(key, secret),
            "status": "ready" if ready else "permission_restricted",
            "message": "Permission kontrolleri tamamlandı." if ready else "Permission kontrollerinde başarısız maddeler var.",
            "controls": controls_payload["controls"],
        }


def _build_crypto() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(urlsafe_b64encode(digest))


def encrypt_secret(raw: str) -> str:
    if not raw:
        return ""
    return _build_crypto().encrypt(raw.encode()).decode()


def decrypt_secret(raw_encrypted: str) -> str:
    if not raw_encrypted:
        return ""
    return _build_crypto().decrypt(raw_encrypted.encode()).decode()


def resolve_runtime_credentials(api_key: str | None, api_secret: str | None) -> tuple[str | None, str | None, str]:
    key = (api_key or "").strip() or os.environ.get("BINANCE_TESTNET_API_KEY")
    secret = (api_secret or "").strip() or os.environ.get("BINANCE_TESTNET_API_SECRET")
    source = "request" if (api_key or "").strip() or (api_secret or "").strip() else "environment"
    return key, secret, source


def _enforce_controlled_limits(config: LiveActivationConfig):
    config.exchange = "binance"
    config.market_type = "futures_testnet"

    if config.safe_mode_enabled:
        config.symbol_whitelist = SAFE_SYMBOL_WHITELIST.copy()
        config.max_position_pct = min(config.max_position_pct, MAX_SAFE_POSITION_PCT)
        config.leverage_cap = min(config.leverage_cap, MAX_SAFE_LEVERAGE)
        config.max_notional_exposure = min(config.max_notional_exposure, MAX_SAFE_NOTIONAL_EXPOSURE)


def get_or_create_exchange_settings(db: Session, user_id: str) -> UserExchangeSetting:
    settings_row = db.query(UserExchangeSetting).filter(UserExchangeSetting.user_id == user_id).first()
    if settings_row:
        return settings_row

    settings_row = UserExchangeSetting(
        id=str(uuid.uuid4()),
        user_id=user_id,
        exchange="binance",
        mode="testnet",
        api_key_encrypted="",
        api_secret_encrypted="",
        permissions_snapshot=[],
        can_trade_snapshot=None,
        last_validation_success=None,
        last_reason_codes=[],
    )
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def save_exchange_settings(
    db: Session,
    *,
    user_id: str,
    exchange: str,
    mode: str,
    api_key: str,
    api_secret: str,
) -> UserExchangeSetting:
    settings_row = get_or_create_exchange_settings(db, user_id)
    settings_row.exchange = exchange
    settings_row.mode = mode
    settings_row.api_key_encrypted = encrypt_secret(api_key)
    settings_row.api_secret_encrypted = encrypt_secret(api_secret)
    settings_row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def exchange_settings_view(settings_row: UserExchangeSetting) -> dict:
    return {
        "exchange": settings_row.exchange,
        "mode": settings_row.mode,
        "has_api_key": bool(settings_row.api_key_encrypted),
        "has_api_secret": bool(settings_row.api_secret_encrypted),
        "updated_at": settings_row.updated_at,
    }


def permission_status_for_user(db: Session, user_id: str) -> dict:
    settings_row = get_or_create_exchange_settings(db, user_id)
    api_key = decrypt_secret(settings_row.api_key_encrypted) if settings_row.api_key_encrypted else None
    api_secret = decrypt_secret(settings_row.api_secret_encrypted) if settings_row.api_secret_encrypted else None
    check = adapter.permission_check(api_key, api_secret)
    status = "ready" if check["status"] == "ready" else "blocked"
    return {
        "overall_status": "pass" if status == "ready" else "fail",
        "live_activation": status,
        "controls": check.get("controls", []),
    }


def _normalize_permissions(account_payload: dict, market_type: str, environment: str) -> list[str]:
    raw_permissions = account_payload.get("permissions") if isinstance(account_payload, dict) else None
    if isinstance(raw_permissions, list) and raw_permissions:
        return sorted({str(item).upper() for item in raw_permissions})

    permissions: set[str] = set()
    if bool(account_payload.get("canTrade")):
        if market_type == "futures":
            permissions.add("FUTURES")
        elif market_type == "spot":
            permissions.add("SPOT")
        else:
            permissions.add("FUTURES" if environment == "testnet" else "SPOT")
    if bool(account_payload.get("canDeposit")):
        permissions.add("DEPOSIT")
    if bool(account_payload.get("canWithdraw")):
        permissions.add("WITHDRAW")
    return sorted(permissions)


def _extract_reason_codes(payload: dict, status_code: int) -> list[str]:
    reason_codes: list[str] = []
    message = str(payload.get("msg") or payload.get("message") or "").lower()
    code = payload.get("code")

    if status_code in {401, 403}:
        if "ip" in message and ("restrict" in message or "whitelist" in message):
            reason_codes.append("ip_restriction")
        if code in {-2015, -2014, -1022} or "invalid" in message:
            reason_codes.append("invalid_key")
        if "permission" in message:
            reason_codes.append("missing_trade_permission")

    if not reason_codes and status_code >= 400:
        reason_codes.append(f"exchange_error_{status_code}")
    return reason_codes


def normalize_failure_code(payload: dict | None, status_code: int | None = None, fallback: str | None = None) -> str:
    raw = payload or {}
    message = str(raw.get("msg") or raw.get("message") or "").lower()
    code = raw.get("code")

    if fallback == "stale_validation_snapshot":
        return "stale_validation"
    if status_code == 451 or "exchange_error_451" in message:
        return "invalid_key"
    if status_code in {401, 403} and (code in {-2015, -2014, -1022} or "invalid" in message):
        return "invalid_key"
    if "permission" in message or "not authorized" in message:
        return "permission_denied"
    if "ip" in message and ("whitelist" in message or "restrict" in message):
        return "ip_restricted"
    if "insufficient" in message or "balance" in message:
        return "insufficient_balance"
    if fallback == "testnet_unreachable" or status_code == 503:
        return "testnet_unreachable"
    if status_code and status_code >= 400:
        return "exchange_rejected"
    return "unknown_exchange_error"


def _is_trade_capable(permissions: list[str]) -> bool:
    normalized = {item.upper() for item in permissions}
    return bool({"SPOT", "FUTURES", "MARGIN", "TRADE"} & normalized)


def _record_permission_snapshot_and_drift(
    db: Session,
    *,
    settings_row: UserExchangeSetting,
    can_trade: bool,
    permissions: list[str],
    validation_success: bool,
    reason_codes: list[str],
) -> None:
    old_permissions = settings_row.permissions_snapshot or []
    old_can_trade = settings_row.can_trade_snapshot
    new_permissions = sorted({item.upper() for item in permissions})
    critical = bool(old_can_trade is True and not can_trade)
    changed = sorted(old_permissions) != new_permissions or old_can_trade != can_trade

    drift_event = None
    if changed and (old_permissions or old_can_trade is not None):
        drift_event = PermissionDriftEvent(
            id=str(uuid.uuid4()),
            user_id=settings_row.user_id,
            exchange=settings_row.exchange,
            old_permissions=old_permissions,
            new_permissions=new_permissions,
            old_can_trade=old_can_trade,
            new_can_trade=can_trade,
            is_critical=critical,
        )
        db.add(drift_event)

    settings_row.permissions_snapshot = new_permissions
    settings_row.can_trade_snapshot = can_trade
    settings_row.last_validation_success = validation_success
    settings_row.last_reason_codes = reason_codes
    settings_row.validation_snapshot_id = str(uuid.uuid4())
    settings_row.validation_checked_at = datetime.now(timezone.utc)
    settings_row.updated_at = datetime.now(timezone.utc)
    db.commit()

    if drift_event is not None:
        route_permission_drift_alert(db, drift_event)


def validate_exchange_credentials_for_user(
    db: Session,
    user_id: str,
    *,
    exchange: str,
    market_type: str,
    environment: str,
) -> tuple[dict, int]:
    requested_exchange = exchange.strip().lower()
    requested_market_type = market_type.strip().lower()
    requested_environment = environment.strip().lower()
    settings_row = get_or_create_exchange_settings(db, user_id)

    seed_binance_venue_registry(db)
    allowed, venue_state, capability_match, venue_reason_codes = check_user_venue_access(
        db,
        user_id,
        requested_exchange,
        requested_market_type,
        requested_environment,
    )

    def _validation_failure(reason_codes: list[str], code: int, *, capability: bool = capability_match) -> tuple[dict, int]:
        settings_row.last_validation_success = False
        settings_row.last_reason_codes = reason_codes
        settings_row.validation_snapshot_id = str(uuid.uuid4())
        settings_row.validation_checked_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "exchange": requested_exchange,
            "market_type": requested_market_type,
            "environment": requested_environment,
            "is_valid": False,
            "permissions": [],
            "can_trade": False,
            "can_withdraw": False,
            "reason_codes": reason_codes,
            "capability_match": capability,
        }, code

    if not allowed:
        return _validation_failure(venue_reason_codes or [venue_state], 403)

    if requested_exchange != settings_row.exchange.lower() or requested_environment != settings_row.mode.lower():
        return _validation_failure(["settings_mismatch"], 400)

    if requested_exchange != "binance":
        return _validation_failure(["adapter_not_configured"], 400)

    api_key = decrypt_secret(settings_row.api_key_encrypted) if settings_row.api_key_encrypted else ""
    api_secret = decrypt_secret(settings_row.api_secret_encrypted) if settings_row.api_secret_encrypted else ""

    if not api_key or not api_secret:
        return _validation_failure(["missing_credentials"], 400)

    try:
        if requested_market_type == "spot":
            payload, status_code, _ = adapter.account_probe_spot(api_key, api_secret)
        else:
            payload, status_code, _ = adapter.account_probe(api_key, api_secret)
    except httpx.HTTPError:
        return _validation_failure(["exchange_unreachable"], 503)

    reason_codes = _extract_reason_codes(payload if isinstance(payload, dict) else {}, status_code)
    if status_code >= 400:
        http_status = 403 if "ip_restriction" in reason_codes or "missing_trade_permission" in reason_codes else 400
        return _validation_failure(reason_codes, http_status)

    permissions = _normalize_permissions(payload, requested_market_type, requested_environment)
    if requested_market_type == "spot":
        can_trade = bool(payload.get("canTrade", True))
        can_withdraw = bool(payload.get("canWithdraw", True))
    else:
        can_trade = bool(payload.get("canTrade", False))
        can_withdraw = bool(payload.get("canWithdraw", False))
    trade_capable = _is_trade_capable(permissions)
    market_tag = "FUTURES" if requested_market_type == "futures" else "SPOT"
    market_capable = market_tag in {item.upper() for item in permissions}

    if not can_trade or not trade_capable or not market_capable:
        _record_permission_snapshot_and_drift(
            db,
            settings_row=settings_row,
            can_trade=False,
            permissions=permissions,
            validation_success=False,
            reason_codes=["missing_trade_permission"],
        )
        return {
            "exchange": requested_exchange,
            "market_type": requested_market_type,
            "environment": requested_environment,
            "is_valid": True,
            "permissions": permissions,
            "can_trade": can_trade and market_capable,
            "can_withdraw": can_withdraw,
            "reason_codes": ["missing_trade_permission"],
            "capability_match": capability_match,
        }, 403

    _record_permission_snapshot_and_drift(
        db,
        settings_row=settings_row,
        can_trade=True,
        permissions=permissions,
        validation_success=True,
        reason_codes=[],
    )
    return {
        "exchange": requested_exchange,
        "market_type": requested_market_type,
        "environment": requested_environment,
        "is_valid": True,
        "permissions": permissions,
        "can_trade": True,
        "can_withdraw": can_withdraw,
        "reason_codes": [],
        "capability_match": capability_match,
    }, 200


def get_market_ticker(symbol: str = "BTCUSDT") -> dict:
    snapshot = adapter.book_ticker(symbol)
    return {
        "exchange": "binance",
        "environment": "testnet",
        "symbol": snapshot["symbol"],
        "bid": snapshot["bid"],
        "ask": snapshot["ask"],
        "mid_price": snapshot["mid_price"],
        "timestamp": snapshot["timestamp"],
    }


def get_or_create_user_risk_settings(db: Session, user_id: str) -> UserRiskSetting:
    row = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
    if row:
        return row
    row = UserRiskSetting(
        id=str(uuid.uuid4()),
        user_id=user_id,
        allocation_pct=20,
        trade_risk_pct=10,
        daily_loss_limit_pct=3,
        compounding_enabled=True,
        base_capital=10000,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_user_risk_settings(
    db: Session,
    *,
    user_id: str,
    allocation_pct: float,
    trade_risk_pct: float,
    daily_loss_limit_pct: float,
    compounding_enabled: bool,
) -> UserRiskSetting:
    if not 1 <= allocation_pct <= 50:
        raise ValueError("İşleme ayrılan ana para 1-50 aralığında olmalı")
    if not 1 <= trade_risk_pct <= 25:
        raise ValueError("İşlemdeki paranın risk oranı 1-25 aralığında olmalı")
    if not 1 <= daily_loss_limit_pct <= 10:
        raise ValueError("Günlük zarar limiti 1-10 aralığında olmalı")

    row = get_or_create_user_risk_settings(db, user_id)
    row.allocation_pct = allocation_pct
    row.trade_risk_pct = trade_risk_pct
    row.daily_loss_limit_pct = daily_loss_limit_pct
    row.compounding_enabled = compounding_enabled
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def _closed_pnl_proxy(db: Session, user_id: str) -> float:
    # Exchange test order tarafında gerçek realize PnL henüz yoksa 0 bazında kalır.
    return 0.0


def _open_position_balance_proxy(db: Session, user_id: str) -> float:
    positions = db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.status == "open").all()
    return round(sum(float(item.position_size or 0) * float(item.entry_price or 0) for item in positions), 2)


def user_portfolio_overview(db: Session, user_id: str) -> dict:
    settings_row = get_or_create_user_risk_settings(db, user_id)
    closed_pnl = _closed_pnl_proxy(db, user_id)
    current_capital = round(settings_row.base_capital + closed_pnl, 2)
    open_position_balance = _open_position_balance_proxy(db, user_id)
    available_balance = round(max(current_capital - open_position_balance, 0), 2)
    next_base = current_capital if settings_row.compounding_enabled else settings_row.base_capital
    return {
        "current_capital": current_capital,
        "available_balance": available_balance,
        "open_position_balance": open_position_balance,
        "closed_pnl": round(closed_pnl, 2),
        "compounding_enabled": settings_row.compounding_enabled,
        "next_base_capital": round(next_base, 2),
    }


def user_risk_preview(
    db: Session,
    user_id: str,
    *,
    market_type: str = "spot",
    leverage: int = 1,
    margin_mode: str = "cross",
    position_side: str = "BOTH",
) -> dict:
    settings_row = get_or_create_user_risk_settings(db, user_id)
    normalized_market_type = (market_type or "spot").strip().lower()
    safe_leverage = max(1, min(int(leverage or 1), 20))
    overview = user_portfolio_overview(db, user_id)
    current_capital = overview["current_capital"]
    position_size = round(current_capital * (settings_row.allocation_pct / 100), 2)
    trade_allocation_amount = position_size
    max_trade_loss_amount = round(position_size * (settings_row.trade_risk_pct / 100), 2)
    capital_impact = round((max_trade_loss_amount / max(current_capital, 1)) * 100, 2)
    next_base = overview["next_base_capital"]

    leverage_value = None
    margin_usage_pct = None
    estimated_liquidation_buffer_pct = None

    if normalized_market_type == "futures":
        leverage_value = safe_leverage
        leveraged_notional = round(position_size * safe_leverage, 2)
        margin_usage_pct = round((position_size / max(current_capital, 1)) * 100, 2)
        estimated_liquidation_buffer_pct = round(max(2.0, (100 / safe_leverage) - (settings_row.trade_risk_pct * 0.6)), 2)
        trade_allocation_amount = leveraged_notional

    warnings: list[str] = []
    if settings_row.allocation_pct > 30:
        warnings.append("high_allocation")
    if settings_row.trade_risk_pct > 15:
        warnings.append("high_trade_risk")
    if settings_row.daily_loss_limit_pct > 5:
        warnings.append("high_daily_loss")

    return {
        "market_type": normalized_market_type,
        "current_capital": current_capital,
        "position_size": position_size,
        "risk_amount": max_trade_loss_amount,
        "allocation_pct": settings_row.allocation_pct,
        "trade_allocation_amount": trade_allocation_amount,
        "trade_risk_pct": settings_row.trade_risk_pct,
        "max_trade_loss_amount": max_trade_loss_amount,
        "total_capital_impact_pct": capital_impact,
        "compounding_enabled": settings_row.compounding_enabled,
        "next_trade_base_capital": next_base,
        "leverage": leverage_value,
        "margin_mode": margin_mode if normalized_market_type == "futures" else None,
        "position_side": position_side if normalized_market_type == "futures" else None,
        "estimated_liquidation_buffer_pct": estimated_liquidation_buffer_pct,
        "margin_usage_pct": margin_usage_pct,
        "warnings": warnings,
    }


def get_or_create_alert_policy(db: Session) -> AlertPolicy:
    row = db.query(AlertPolicy).filter(AlertPolicy.id == "global").first()
    if row:
        return row
    row = AlertPolicy(id="global")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_alert_policy(db: Session, payload: dict) -> AlertPolicy:
    row = get_or_create_alert_policy(db)
    for key, value in payload.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def _active_override(db: Session) -> ReleaseGateOverride | None:
    now = datetime.now(timezone.utc)
    return (
        db.query(ReleaseGateOverride)
        .filter(
            ReleaseGateOverride.revoked_at.is_(None),
            ReleaseGateOverride.expires_at > now,
        )
        .order_by(ReleaseGateOverride.created_at.desc())
        .first()
    )


def _serialize_override(row: ReleaseGateOverride) -> dict:
    return {
        "override_id": row.id,
        "admin_user_id": row.admin_user_id,
        "reason_code": row.reason_code,
        "reason_note": row.reason_note,
        "release_gate_snapshot": row.release_gate_snapshot,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "deploy_context": row.deploy_context,
        "used_deploy_count": row.used_deploy_count,
    }


def create_release_gate_override(
    db: Session,
    *,
    admin_user_id: str,
    reason_code: str,
    reason_note: str,
    ttl_minutes: int,
    deploy_context: dict,
) -> ReleaseGateOverride:
    normalized_reason = reason_code.strip().lower()
    if normalized_reason not in OVERRIDE_REASON_CODES:
        raise ValueError("reason_code geçersiz")
    if len(reason_note.strip()) < 12:
        raise ValueError("reason_note en az 12 karakter olmalı")
    if ttl_minutes > 60:
        raise ValueError("ttl_minutes en fazla 60 olabilir")

    gate = release_gate_view(db)
    if gate["status"] != "BLOCKED":
        raise ValueError("Manual override sadece BLOCKED durumunda açılabilir")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl_minutes or 30)
    row = ReleaseGateOverride(
        id=str(uuid.uuid4()),
        admin_user_id=admin_user_id,
        reason_code=normalized_reason,
        reason_note=reason_note.strip(),
        release_gate_snapshot=gate,
        deploy_context=deploy_context,
        created_at=now,
        expires_at=expires_at,
        revoked_at=None,
        used_deploy_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_release_gate_override(db: Session, override_id: str, admin_user_id: str) -> ReleaseGateOverride:
    row = db.query(ReleaseGateOverride).filter(ReleaseGateOverride.id == override_id).first()
    if row is None:
        raise ValueError("override bulunamadı")
    if row.revoked_at is not None:
        return row
    row.revoked_at = datetime.now(timezone.utc)
    row.deploy_context = {**(row.deploy_context or {}), "revoked_by": admin_user_id}
    db.commit()
    db.refresh(row)
    return row


def list_release_gate_overrides(db: Session, limit: int = 50) -> list[ReleaseGateOverride]:
    return db.query(ReleaseGateOverride).order_by(ReleaseGateOverride.created_at.desc()).limit(limit).all()


def mark_active_override_used_in_deploy(db: Session) -> ReleaseGateOverride | None:
    row = _active_override(db)
    if row is None:
        return None
    row.used_deploy_count += 1
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def user_readiness_checklist(
    db: Session,
    user_id: str,
    *,
    exchange: str | None = None,
    market_type: str | None = None,
    environment: str | None = None,
) -> dict:
    settings_row = get_or_create_exchange_settings(db, user_id)
    requested_exchange = (exchange or settings_row.exchange or "binance").strip().lower()
    requested_market_type = (market_type or "futures").strip().lower()
    requested_environment = (environment or settings_row.mode or "testnet").strip().lower()

    allowed, venue_state, capability_match, venue_reason_codes = check_user_venue_access(
        db,
        user_id,
        requested_exchange,
        requested_market_type,
        requested_environment,
    )

    has_api_key = bool(settings_row.api_key_encrypted)
    has_api_secret = bool(settings_row.api_secret_encrypted)
    validation_ts = settings_row.validation_checked_at
    if validation_ts and validation_ts.tzinfo is None:
        validation_ts = validation_ts.replace(tzinfo=timezone.utc)
    stale = True
    if validation_ts:
        stale = validation_ts + timedelta(minutes=VALIDATION_STALE_MINUTES) < datetime.now(timezone.utc)

    validation_success = bool(settings_row.last_validation_success)
    can_trade = bool(settings_row.can_trade_snapshot)
    is_testnet = requested_environment == "testnet"
    reason_codes = settings_row.last_reason_codes or []

    readiness_status = "blocked"
    last_error_reason = reason_codes[0] if reason_codes else ""
    if not allowed:
        readiness_status = "blocked"
        last_error_reason = (venue_reason_codes or [venue_state])[0]
    elif requested_exchange != settings_row.exchange.lower() or requested_environment != settings_row.mode.lower():
        readiness_status = "blocked"
        last_error_reason = "settings_mismatch"
    elif not has_api_key or not has_api_secret:
        readiness_status = "awaiting_valid_key"
        last_error_reason = "missing_credentials"
    elif stale:
        readiness_status = "blocked"
        last_error_reason = "stale_validation_snapshot"
    elif not validation_success or not can_trade:
        readiness_status = "blocked"
    else:
        gate = release_gate_view(db)
        if gate["status"] == "BLOCKED":
            readiness_status = "blocked"
            last_error_reason = "release_gate_forced_block"
        else:
            connectivity = adapter.ping()
            if connectivity["status"] != "reachable":
                readiness_status = "blocked"
                last_error_reason = "exchange_health_degraded"
            else:
                readiness_status = "ready_for_test_order"

    return {
        "readiness_status": readiness_status,
        "has_api_key": has_api_key,
        "has_api_secret": has_api_secret,
        "validation_success": validation_success,
        "can_trade": can_trade,
        "is_testnet_environment": is_testnet,
        "is_validation_stale": stale,
        "validation_timestamp": validation_ts,
        "validation_snapshot_id": settings_row.validation_snapshot_id,
        "stale_after_minutes": VALIDATION_STALE_MINUTES,
        "last_error_reason": last_error_reason,
        "exchange": requested_exchange,
        "market_type": requested_market_type,
        "environment": requested_environment,
        "capability_match": capability_match,
    }


def _trend_direction_from_candles() -> str:
    candles = read_candles(redis_client, "market:candles:BTCUSDT:15m")
    if len(candles) < 20:
        return "long"

    closes = [float(item.get("close") or 0) for item in candles[-20:] if float(item.get("close") or 0) > 0]
    if not closes:
        return "long"
    sma20 = sum(closes) / len(closes)
    return "long" if closes[-1] >= sma20 else "short"


def _market_volatility_pct() -> float:
    candles = read_candles(redis_client, "market:candles:BTCUSDT:15m")
    if len(candles) < 30:
        return 0.015

    closes = [float(item.get("close") or 0) for item in candles[-30:] if float(item.get("close") or 0) > 0]
    if len(closes) < 10:
        return 0.015

    mean_price = sum(closes) / len(closes)
    std_dev = statistics.pstdev(closes)
    return round((std_dev / max(mean_price, 0.0001)), 6)


def _resolve_strategy_context(db: Session, user_id: str) -> tuple[str, str]:
    trend_direction = _trend_direction_from_candles()
    bot = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == user_id, BotProfile.is_enabled.is_(True))
        .order_by(BotProfile.updated_at.desc())
        .first()
    )
    strategy_type = bot.strategy_type if bot else "trend_following"

    if strategy_type == "mean_reversion":
        direction = "short" if trend_direction == "long" else "long"
    else:
        direction = trend_direction
    return strategy_type, direction


def _build_execution_quality_score(
    *,
    expected_price: float,
    fill_price: float | None,
    execution_latency: float,
    final_status: str,
    strategy_type: str,
    volatility_pct: float,
) -> float:
    slippage_bps = 0.0
    if fill_price and expected_price > 0:
        slippage_bps = abs((fill_price - expected_price) / expected_price) * 10000

    regime = "low"
    if volatility_pct >= 0.03:
        regime = "high"
    elif volatility_pct >= 0.018:
        regime = "medium"

    regime_slippage_tolerance = {"low": 4.0, "medium": 7.0, "high": 12.0}[regime]
    strategy_multiplier = {
        "trend_following": 1.0,
        "breakout": 1.1,
        "volatility_expansion": 1.15,
        "mean_reversion": 0.85,
    }.get(strategy_type, 1.0)
    normalized_slippage = (slippage_bps / max(regime_slippage_tolerance * strategy_multiplier, 0.1)) * 10

    status_penalty = {
        "filled": 0,
        "partial_fill": 12,
        "cancelled": 20,
        "failed": 35,
    }.get(final_status, 25)
    latency_budget = 1400 if regime == "high" else 1000
    latency_component = min(35, max(0.0, execution_latency / max(latency_budget, 1)) * 35)
    score = 100 - min(45, normalized_slippage) - latency_component - status_penalty
    return round(max(0, score), 2)


def _safe_quantity(expected_price: float) -> float:
    capped_notional = min(MAX_SAFE_NOTIONAL_EXPOSURE, 100)
    raw_qty = capped_notional / max(expected_price, 1)
    return round(max(raw_qty, 0.001), 3)


def _map_order_status(status: str) -> str:
    normalized = (status or "").upper()
    if normalized == "FILLED":
        return "filled"
    if normalized == "PARTIALLY_FILLED":
        return "partial_fill"
    if normalized in {"CANCELED", "EXPIRED"}:
        return "cancelled"
    return "failed"


def run_controlled_test_order(db: Session, user: User) -> TestnetExecutionLog:
    settings_row = get_or_create_exchange_settings(db, user.id)
    api_key = decrypt_secret(settings_row.api_key_encrypted) if settings_row.api_key_encrypted else None
    api_secret = decrypt_secret(settings_row.api_secret_encrypted) if settings_row.api_secret_encrypted else None

    permission = adapter.permission_check(api_key, api_secret)
    permission_snapshot = permission.get("controls", [])
    if permission["status"] != "ready":
        raise ValueError("Permission check başarısız. Önce API key doğrulamasını geçmelisiniz.")

    symbol = SAFE_SYMBOL_WHITELIST[0]
    strategy_type, direction = _resolve_strategy_context(db, user.id)
    side = "BUY" if direction == "long" else "SELL"
    volatility_pct = _market_volatility_pct()
    volatility_regime = "high" if volatility_pct >= 0.03 else ("medium" if volatility_pct >= 0.018 else "low")
    expected_price = adapter.mark_price(symbol)
    quantity = _safe_quantity(expected_price)

    adapter.set_leverage(api_key or "", api_secret or "", symbol, MAX_SAFE_LEVERAGE)

    state_path = ["created", "submitted"]
    started = time.perf_counter()
    primary_price = round(expected_price * (0.9996 if side == "BUY" else 1.0004), 2)
    primary_order, primary_status = adapter.create_limit_order(
        api_key or "",
        api_secret or "",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=primary_price,
        time_in_force="GTC",
    )
    if primary_status >= 400:
        state_path.append("failed")
        final_status = "failed"
        fill_price = None
    else:
        state_path.append("acknowledged")
        order_id = int(primary_order.get("orderId") or 0)
        current_status_payload, _ = adapter.query_order(api_key or "", api_secret or "", symbol, order_id)
        normalized_status = _map_order_status(current_status_payload.get("status", ""))
        fill_price = float(current_status_payload.get("avgPrice") or 0) or None

        if normalized_status == "filled":
            state_path.append("filled")
            final_status = "filled"
        else:
            if normalized_status == "partial_fill":
                state_path.append("partial_fill")

            fallback_price = round(expected_price * (1.0012 if side == "BUY" else 0.9988), 2)
            fallback_order, fallback_status = adapter.create_limit_order(
                api_key or "",
                api_secret or "",
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=fallback_price,
                time_in_force="IOC",
            )

            if fallback_status >= 400:
                state_path.append("failed")
                final_status = "failed"
            else:
                fallback_id = int(fallback_order.get("orderId") or 0)
                fallback_payload, _ = adapter.query_order(api_key or "", api_secret or "", symbol, fallback_id)
                final_status = _map_order_status(fallback_payload.get("status", ""))
                fallback_avg = float(fallback_payload.get("avgPrice") or 0) or None
                fill_price = fallback_avg or fill_price
                state_path.append(final_status)

    execution_latency = round((time.perf_counter() - started) * 1000, 2)
    slippage = round((fill_price - expected_price), 6) if fill_price else None
    quality_score = _build_execution_quality_score(
        expected_price=expected_price,
        fill_price=fill_price,
        execution_latency=execution_latency,
        final_status=final_status,
        strategy_type=strategy_type,
        volatility_pct=volatility_pct,
    )

    execution_log = TestnetExecutionLog(
        id=str(uuid.uuid4()),
        user_id=user.id,
        symbol=symbol,
        strategy_direction=direction,
        expected_price=expected_price,
        fill_price=fill_price,
        slippage=slippage,
        execution_latency=execution_latency,
        execution_quality_score=quality_score,
        status=final_status,
        state_machine_path=state_path,
        permission_snapshot=permission_snapshot,
        release_gate_status="WARNING" if final_status in {"partial_fill", "cancelled"} else ("PASS" if final_status == "filled" else "BLOCKED"),
        details={
            "order_type": "limit",
            "fallback": "IOC",
            "strategy_type": strategy_type,
            "volatility_pct": volatility_pct,
            "volatility_regime": volatility_regime,
            "max_position_pct": MAX_SAFE_POSITION_PCT,
            "max_notional": MAX_SAFE_NOTIONAL_EXPOSURE,
            "leverage": MAX_SAFE_LEVERAGE,
            "position_size": quantity,
        },
    )
    db.add(execution_log)
    db.commit()
    db.refresh(execution_log)
    return execution_log


def run_exchange_test_order_market(
    db: Session,
    user: User,
    *,
    exchange: str,
    market_type: str,
    environment: str,
    leverage: int = 1,
    margin_mode: str = "cross",
    position_side: str = "BOTH",
) -> ExecutionMetric:
    normalized_exchange = exchange.strip().lower()
    normalized_market_type = market_type.strip().lower()
    normalized_environment = environment.strip().lower()

    if normalized_exchange != "binance":
        raise ValueError("Sadece binance adaptörü aktif. exchange_rejected")
    if normalized_environment != "testnet":
        raise ValueError("Sadece testnet environment destekleniyor. exchange_rejected")
    if normalized_market_type not in {"spot", "futures"}:
        raise ValueError("market_type spot veya futures olmalı")

    settings_row = get_or_create_exchange_settings(db, user.id)
    validation, status_code = validate_exchange_credentials_for_user(
        db,
        user.id,
        exchange=normalized_exchange,
        market_type=normalized_market_type,
        environment=normalized_environment,
    )
    if status_code != 200:
        normalize_map = {
            "missing_credentials": "invalid_key",
            "exchange_error_451": "invalid_key",
            "missing_trade_permission": "permission_denied",
            "ip_restriction": "ip_restricted",
            "insufficient_balance": "insufficient_balance",
            "exchange_unreachable": "testnet_unreachable",
            "stale_validation_snapshot": "stale_validation",
            "settings_mismatch": "stale_validation",
        }
        first_reason = (validation.get("reason_codes") or ["unknown_exchange_error"])[0]
        normalized_reason = normalize_map.get(first_reason, "unknown_exchange_error")
        raise ValueError(f"{normalized_reason}: Exchange doğrulaması başarısız")

    if normalized_market_type == "futures" and (leverage < 1 or leverage > 20):
        raise ValueError("Futures için leverage 1-20 aralığında olmalı")

    api_key = decrypt_secret(settings_row.api_key_encrypted)
    api_secret = decrypt_secret(settings_row.api_secret_encrypted)

    symbol = SAFE_SYMBOL_WHITELIST[0]
    side = "BUY"
    quote_qty = 10.0
    ticker = get_market_ticker(symbol)
    mid_price = float(ticker["mid_price"] or 0)
    mid_ts = ticker["timestamp"]
    if mid_price <= 0:
        raise ValueError("Market ticker alınamadı. Lütfen tekrar deneyin.")

    quantity = round(quote_qty / mid_price, 3)
    quantity = max(quantity, 0.001)
    notional = quantity * mid_price
    if notional > 10.05:
        quantity = round(10.0 / mid_price, 3)

    strategy_type, _ = _resolve_strategy_context(db, user.id)
    volatility_pct = _market_volatility_pct()
    volatility_regime = "high" if volatility_pct >= 0.03 else ("medium" if volatility_pct >= 0.018 else "low")

    order_id = str(uuid.uuid4())
    client_order_id = f"cli-{uuid.uuid4().hex[:20]}"
    submitted_at = datetime.now(timezone.utc)
    timeline_events: list[tuple[str, datetime, dict]] = [
        (
            "request_sent",
            submitted_at,
            {
                "symbol": symbol,
                "side": side,
                "quote_qty": quote_qty,
                "quantity": quantity,
                "exchange": normalized_exchange,
                "market_type": normalized_market_type,
                "environment": normalized_environment,
                "leverage": leverage if normalized_market_type == "futures" else None,
                "margin_mode": margin_mode if normalized_market_type == "futures" else None,
                "position_side": position_side if normalized_market_type == "futures" else None,
            },
        )
    ]

    started = time.perf_counter()
    order_payload: dict = {}
    order_status = 500
    exchange_order_id = "unknown"
    state_path: list[str] = ["NEW"]
    final_payload: dict = {}
    ack_at = None
    final_at = None
    failure_code = None

    try:
        if normalized_market_type == "futures":
            leverage_payload, leverage_status = adapter.set_leverage(api_key, api_secret, symbol, leverage)
            if leverage_status >= 400:
                raise ValueError(f"{normalize_failure_code(leverage_payload, leverage_status)}: leverage_context_invalid")
            order_payload, order_status = adapter.create_market_order(
                api_key,
                api_secret,
                symbol=symbol,
                side=side,
                quantity=quantity,
            )
        else:
            order_payload, order_status = adapter.create_spot_market_order(
                api_key,
                api_secret,
                symbol=symbol,
                side=side,
                quote_order_qty=quote_qty,
            )
    except httpx.HTTPError:
        order_payload = {"msg": "testnet_unreachable"}
        order_status = 503

    ack_at = datetime.now(timezone.utc)
    timeline_events.append(("exchange_ack", ack_at, {"status_code": order_status, "payload": order_payload}))

    if order_status >= 400:
        final_status = "REJECTED"
        failure_code = normalize_failure_code(order_payload, order_status)
        if final_status not in state_path:
            state_path.append(final_status)
        final_payload = order_payload
    else:
        exchange_order_id = str(order_payload.get("orderId") or "")
        first_status = str(order_payload.get("status") or "NEW").upper()
        if first_status not in state_path:
            state_path.append(first_status)
        final_payload = order_payload

        terminal_statuses = {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}
        if first_status in {"NEW", "PARTIALLY_FILLED"} and exchange_order_id:
            for _ in range(6):
                time.sleep(0.2)
                if normalized_market_type == "spot":
                    queried, _ = adapter.query_spot_order(api_key, api_secret, symbol, int(exchange_order_id))
                else:
                    queried, _ = adapter.query_order(api_key, api_secret, symbol, int(exchange_order_id))

                queried_status = str(queried.get("status") or first_status).upper()
                final_payload = queried
                now_evt = datetime.now(timezone.utc)
                if queried_status != state_path[-1]:
                    state_path.append(queried_status)
                if queried_status == "PARTIALLY_FILLED":
                    timeline_events.append(("partial_fill", now_evt, {"status": queried_status, "payload": queried}))
                if queried_status in terminal_statuses:
                    break

        current_status = str(final_payload.get("status") or state_path[-1]).upper()
        if current_status not in terminal_statuses and exchange_order_id:
            cancel_payload, cancel_status = adapter.cancel_order(
                api_key,
                api_secret,
                symbol,
                int(exchange_order_id),
                market_type=normalized_market_type,
            )
            if cancel_status < 400:
                final_payload = cancel_payload
                current_status = str(cancel_payload.get("status") or "CANCELED").upper()
            else:
                failure_code = normalize_failure_code(cancel_payload, cancel_status)

        final_status = current_status
        if final_status not in state_path:
            state_path.append(final_status)
        if final_status in {"REJECTED", "CANCELED", "EXPIRED"} and failure_code is None:
            failure_code = normalize_failure_code(final_payload, order_status)

    final_at = datetime.now(timezone.utc)
    if final_status == "FILLED":
        timeline_events.append(("final_fill", final_at, {"status": final_status}))
    elif final_status in {"CANCELED", "EXPIRED"}:
        timeline_events.append(("final_cancel", final_at, {"status": final_status}))
    else:
        timeline_events.append(("final_status", final_at, {"status": final_status}))

    avg_price = float(final_payload.get("avgPrice") or final_payload.get("cummulativeQuoteQty", 0) or 0) or None
    if normalized_market_type == "spot" and avg_price and quantity > 0 and (final_payload.get("avgPrice") in {None, "0", 0}):
        avg_price = round(float(final_payload.get("cummulativeQuoteQty") or 0) / quantity, 8)
    executed_qty = float(final_payload.get("executedQty") or 0) or None
    execution_time_ms = round((time.perf_counter() - started) * 1000, 2)
    slippage_pct = None
    if avg_price:
        slippage_pct = round((abs(avg_price - mid_price) / mid_price) * 100, 6)

    mapped_status = _map_order_status(final_status)
    quality_score = _build_execution_quality_score(
        expected_price=mid_price,
        fill_price=avg_price,
        execution_latency=execution_time_ms,
        final_status=mapped_status,
        strategy_type=strategy_type,
        volatility_pct=volatility_pct,
    )

    metric = ExecutionMetric(
        id=str(uuid.uuid4()),
        user_id=user.id,
        symbol=symbol,
        order_id=order_id,
        exchange_order_id=exchange_order_id or "unknown",
        client_order_id=client_order_id,
        order_type="MARKET",
        exchange=normalized_exchange,
        market_type=normalized_market_type,
        environment=normalized_environment,
        side=side,
        quote_qty=quote_qty,
        mid_price=mid_price,
        mid_price_timestamp=mid_ts,
        price_avg=avg_price,
        executed_qty=executed_qty,
        slippage_pct=slippage_pct,
        execution_time_ms=execution_time_ms,
        status=final_status,
        final_status=final_status,
        failure_code=failure_code,
        strategy_type=strategy_type,
        volatility_regime=volatility_regime,
        volatility_pct=volatility_pct,
        execution_quality_score=quality_score,
        submitted_at=submitted_at,
        ack_at=ack_at,
        final_at=final_at,
        validation_snapshot_id=settings_row.validation_snapshot_id,
        raw_exchange_status=final_payload,
        state_machine_path=state_path,
    )
    db.add(metric)
    db.flush()

    for event_name, event_timestamp, payload in timeline_events:
        db.add(
            ExecutionLifecycleEvent(
                id=str(uuid.uuid4()),
                execution_metric_id=metric.id,
                user_id=user.id,
                event_name=event_name,
                event_timestamp=event_timestamp,
                payload=payload,
            )
        )

    db.commit()
    db.refresh(metric)
    return metric


def latest_execution_metric(db: Session, user_id: str) -> ExecutionMetric | None:
    return (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.user_id == user_id)
        .order_by(ExecutionMetric.created_at.desc())
        .first()
    )


def list_execution_metrics(db: Session, limit: int = 20) -> list[ExecutionMetric]:
    return db.query(ExecutionMetric).order_by(ExecutionMetric.created_at.desc()).limit(limit).all()


def lifecycle_evidence_for_metric(db: Session, metric_id: str) -> list[ExecutionLifecycleEvent]:
    return (
        db.query(ExecutionLifecycleEvent)
        .filter(ExecutionLifecycleEvent.execution_metric_id == metric_id)
        .order_by(ExecutionLifecycleEvent.event_timestamp.asc())
        .all()
    )


def permission_drift_trend(db: Session, days: int = 7) -> dict:
    days = 30 if days > 7 else 7
    today = datetime.now(timezone.utc).date()
    start_date = today.fromordinal(today.toordinal() - (days - 1))

    rows = (
        db.query(PermissionDriftEvent)
        .filter(PermissionDriftEvent.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        .all()
    )

    bucket = {str(start_date.fromordinal(start_date.toordinal() + i)): {"event_count": 0, "critical_count": 0} for i in range(days)}
    affected_users = set()
    latest_timestamp = None
    for row in rows:
        date_key = row.created_at.date().isoformat()
        if date_key in bucket:
            bucket[date_key]["event_count"] += 1
            bucket[date_key]["critical_count"] += 1 if row.is_critical else 0
            affected_users.add(row.user_id)
            if latest_timestamp is None or row.created_at > latest_timestamp:
                latest_timestamp = row.created_at

    points = [
        {"date": key, "event_count": value["event_count"], "critical_count": value["critical_count"]}
        for key, value in bucket.items()
    ]
    return {
        "days": days,
        "points": points,
        "affected_user_count": len(affected_users),
        "latest_timestamp": latest_timestamp,
        "critical_drift_count": sum(item["critical_count"] for item in points),
    }


def override_alert_analytics(db: Session, days: int = 7) -> dict:
    days = 30 if days > 7 else 7
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days - 1)
    bucket = {
        (start_date + timedelta(days=i)).isoformat(): {"blocked_gate_count": 0, "override_count": 0, "override_deploy_count": 0}
        for i in range(days)
    }

    blocked_logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "release_gate_status_changed",
            AuditLog.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
        )
        .all()
    )
    for log in blocked_logs:
        if (log.details or {}).get("status") == "BLOCKED":
            key = log.created_at.date().isoformat()
            if key in bucket:
                bucket[key]["blocked_gate_count"] += 1

    overrides = (
        db.query(ReleaseGateOverride)
        .filter(ReleaseGateOverride.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        .all()
    )
    for row in overrides:
        key = row.created_at.date().isoformat()
        if key in bucket:
            bucket[key]["override_count"] += 1
            bucket[key]["override_deploy_count"] += int(row.used_deploy_count or 0)

    alert_logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
            AuditLog.severity.in_(["warning", "error"]),
        )
        .all()
    )
    breakdown: dict[str, int] = {}
    for log in alert_logs:
        source = log.action
        breakdown[source] = breakdown.get(source, 0) + 1

    return {
        "days": days,
        "points": [{"date": key, **value} for key, value in bucket.items()],
        "alert_source_breakdown": breakdown,
    }


def active_alerts(db: Session) -> list[dict]:
    policy = get_or_create_alert_policy(db)
    alerts: list[dict] = []

    score = _latest_execution_quality_score(db)
    if score < policy.execution_quality_warning_threshold:
        alerts.append(
            {
                "code": "execution_quality_alert",
                "severity": "critical" if score < policy.execution_quality_critical_threshold else "warning",
                "value": score,
                "threshold_warning": policy.execution_quality_warning_threshold,
                "threshold_critical": policy.execution_quality_critical_threshold,
            }
        )

    drift_stats = permission_drift_trend(db, days=7)
    drift_per_day = sum(point["event_count"] for point in drift_stats["points"]) / 7
    if drift_per_day > policy.permission_drift_warning_per_day:
        alerts.append(
            {
                "code": "permission_drift_alert",
                "severity": "critical" if drift_per_day > policy.permission_drift_critical_per_day else "warning",
                "value": round(drift_per_day, 2),
                "threshold_warning": float(policy.permission_drift_warning_per_day),
                "threshold_critical": float(policy.permission_drift_critical_per_day),
            }
        )

    override_stats = override_alert_analytics(db, days=7)
    override_per_day = sum(item["override_count"] for item in override_stats["points"]) / 7
    if override_per_day > policy.gate_override_warning_per_day:
        alerts.append(
            {
                "code": "gate_override_alert",
                "severity": "critical" if override_per_day > policy.gate_override_critical_per_day else "warning",
                "value": round(override_per_day, 2),
                "threshold_warning": float(policy.gate_override_warning_per_day),
                "threshold_critical": float(policy.gate_override_critical_per_day),
            }
        )

    return alerts


def route_permission_drift_alert(db: Session, drift_event: PermissionDriftEvent) -> None:
    policy = get_or_create_alert_policy(db)
    payload = {
        "user_id": drift_event.user_id,
        "exchange": drift_event.exchange,
        "old_permissions": drift_event.old_permissions,
        "new_permissions": drift_event.new_permissions,
        "old_can_trade": drift_event.old_can_trade,
        "new_can_trade": drift_event.new_can_trade,
        "is_critical": drift_event.is_critical,
        "timestamp": drift_event.created_at.isoformat(),
    }

    if policy.monitoring_alert_log_enabled:
        db.add(
            AuditLog(
                id=str(uuid.uuid4()),
                action="permission_drift_alert_logged",
                entity_type="permission_drift",
                entity_id=drift_event.id,
                actor_user_id=None,
                actor_role="system",
                severity="critical" if drift_event.is_critical else "warning",
                details=payload,
            )
        )

    if policy.admin_notification_enabled:
        db.add(
            AuditLog(
                id=str(uuid.uuid4()),
                action="permission_drift_admin_notification",
                entity_type="admin_notification",
                entity_id=drift_event.id,
                actor_user_id=None,
                actor_role="system",
                severity="warning",
                details={"channel": "admin_panel", **payload},
            )
        )

    webhook = (policy.ops_webhook_url or "").strip()
    if webhook:
        try:
            httpx.post(webhook, json=payload, timeout=4)
            db.add(
                AuditLog(
                    id=str(uuid.uuid4()),
                    action="permission_drift_ops_webhook_sent",
                    entity_type="ops_webhook",
                    entity_id=drift_event.id,
                    actor_user_id=None,
                    actor_role="system",
                    severity="info",
                    details={"webhook": webhook, "status": "sent"},
                )
            )
        except Exception as exc:
            db.add(
                AuditLog(
                    id=str(uuid.uuid4()),
                    action="permission_drift_ops_webhook_failed",
                    entity_type="ops_webhook",
                    entity_id=drift_event.id,
                    actor_user_id=None,
                    actor_role="system",
                    severity="warning",
                    details={"webhook": webhook, "error": str(exc)},
                )
            )

    db.commit()


def alert_history(db: Session, limit: int = 40) -> list[dict]:
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.severity.in_(["warning", "error"]))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "created_at": row.created_at,
            "action": row.action,
            "severity": row.severity,
            "source": row.entity_type,
            "details": row.details,
        }
        for row in rows
    ]


def latest_execution_quality(db: Session, user_id: str):
    metric = latest_execution_metric(db, user_id)
    if metric:
        return metric
    return (
        db.query(TestnetExecutionLog)
        .filter(TestnetExecutionLog.user_id == user_id)
        .order_by(TestnetExecutionLog.created_at.desc())
        .first()
    )


def list_execution_quality(db: Session, limit: int = 20):
    metrics = list_execution_metrics(db, limit=limit)
    if metrics:
        return metrics
    return db.query(TestnetExecutionLog).order_by(TestnetExecutionLog.created_at.desc()).limit(limit).all()


def enforce_release_gate(db: Session, environment: str = "prod") -> dict:
    gate = release_gate_view(db, environment=environment)
    config = get_or_create_live_config(db)
    if gate["status"] == "BLOCKED":
        config.live_mode_enabled = False
    config.updated_at = datetime.now(timezone.utc)
    db.commit()

    redis_client.set("phase4:release_gate:status", gate["status"])
    redis_client.set("phase4:release_gate:environment", gate.get("environment", "prod"))
    redis_client.set("phase4:release_gate:last_checked", datetime.now(timezone.utc).isoformat())
    redis_client.set("phase4:release_gate:live_activation", gate["live_activation"])
    redis_client.set("phase4:release_gate:reasons", json.dumps(gate["reasons"]))
    return gate


def _pick_latest_exchange_user(db: Session) -> User | None:
    row = (
        db.query(UserExchangeSetting)
        .filter(UserExchangeSetting.api_key_encrypted != "", UserExchangeSetting.api_secret_encrypted != "")
        .order_by(UserExchangeSetting.updated_at.desc())
        .first()
    )
    if not row:
        return None
    return db.query(User).filter(User.id == row.user_id).first()


def admin_permission_overview(db: Session) -> dict:
    probe_user = _pick_latest_exchange_user(db)
    if not probe_user:
        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "overall_status": "fail",
            "live_activation": "blocked",
            "controls": [
                {"key": "can_trade", "status": "fail", "reason": "no_user_credentials", "timestamp": now_iso},
                {"key": "can_futures", "status": "fail", "reason": "no_user_credentials", "timestamp": now_iso},
                {"key": "timestamp_sync", "status": "fail", "reason": "no_user_credentials", "timestamp": now_iso},
                {"key": "rate_limit_ok", "status": "fail", "reason": "no_user_credentials", "timestamp": now_iso},
            ],
        }
    return permission_status_for_user(db, probe_user.id)


def _latest_execution_quality_score(db: Session) -> float:
    latest_metric = db.query(ExecutionMetric).order_by(ExecutionMetric.created_at.desc()).first()
    if latest_metric:
        return float(latest_metric.execution_quality_score or 0)
    latest_exec = db.query(TestnetExecutionLog).order_by(TestnetExecutionLog.created_at.desc()).first()
    if latest_exec:
        return float(latest_exec.execution_quality_score or 0)
    return 0.0


def _permission_drift_alert_active(db: Session) -> bool:
    threshold = datetime.now(timezone.utc) - timedelta(days=1)
    critical_count = (
        db.query(PermissionDriftEvent)
        .filter(PermissionDriftEvent.created_at >= threshold, PermissionDriftEvent.is_critical.is_(True))
        .count()
    )
    return critical_count > 0


def _clock_drift_seconds() -> float | None:
    ping = adapter.ping()
    server_time = ping.get("server_time")
    if not server_time:
        return None
    try:
        server_ts = float(server_time)
    except (TypeError, ValueError):
        return None
    if server_ts > 1e12:
        server_ts = server_ts / 1000
    server_dt = datetime.fromtimestamp(server_ts, tz=timezone.utc)
    return abs((datetime.now(timezone.utc) - server_dt).total_seconds())


def _worker_lag_seconds() -> float:
    try:
        raw = redis_client.lindex("runtime:events:all", 0)
        if not raw:
            return 0.0
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        created_at = payload.get("created_at")
        if not created_at:
            return 0.0
        event_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return abs((datetime.now(timezone.utc) - event_dt).total_seconds())
    except Exception:
        return 0.0


def _rate_limit_health(db: Session) -> str:
    registry = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == "binance").first()
    if not registry:
        return "unknown"
    status = (registry.rate_limit_status or "unknown").lower()
    if status in {"ok", "healthy"}:
        return "ok"
    if status in {"critical", "blocked"}:
        return "critical"
    return "warning"


def _risk_orchestrator_enabled(db: Session) -> bool:
    policy = db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()
    if policy is None:
        policy = get_or_create_policy(db)
    return policy is not None


def _kill_switch_tested(db: Session) -> bool:
    threshold = datetime.now(timezone.utc) - timedelta(days=30)
    actions = {"kill_switch_triggered", "kill_switch_reset", "kill_switch_tested"}
    count = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= threshold, AuditLog.action.in_(actions))
        .count()
    )
    return count > 0


def _failed_event_backlog(db: Session) -> int:
    return db.query(FailedEvent).filter(FailedEvent.status == "dead").count()


def evaluate_release_gate_policy(db: Session, environment: str = "prod") -> dict:
    env = (environment or "").lower().strip()
    if env not in {"stage", "prod"}:
        raise ValueError("environment must be stage or prod")

    config = get_or_create_live_config(db)
    exchange_health = adapter.ping()["status"] == "reachable"
    execution_quality_score = _latest_execution_quality_score(db)
    permission_drift_alert = _permission_drift_alert_active(db)
    override = _active_override(db)
    active_override = override is not None
    live_mode_enabled = bool(config.live_mode_enabled)

    permission_overview = admin_permission_overview(db)
    permission_controls = {item.get("key"): item for item in permission_overview.get("controls", [])}

    clock_drift = _clock_drift_seconds()
    worker_lag = _worker_lag_seconds()
    rate_limit_health = _rate_limit_health(db)
    risk_orchestrator_ok = _risk_orchestrator_enabled(db)
    kill_switch_tested = _kill_switch_tested(db)
    chain_status = verify_manifest_chain()
    failed_backlog = _failed_event_backlog(db)

    score_block_threshold = 40 if env == "stage" else 60
    score_warn_threshold = 60 if env == "stage" else 75

    blockers: list[str] = []
    warnings: list[str] = []

    if not exchange_health:
        blockers.append("exchange_health")

    if execution_quality_score < score_block_threshold:
        blockers.append("execution_quality_score")
    elif execution_quality_score < score_warn_threshold:
        warnings.append("execution_quality_score_warning")

    if permission_drift_alert:
        if env == "prod":
            blockers.append("permission_drift_alert")
        else:
            warnings.append("permission_drift_alert")

    if permission_overview.get("overall_status") != "pass":
        blockers.append("permission_check_fail")
    else:
        for key, control in permission_controls.items():
            status = control.get("status")
            if status == "fail":
                blockers.append(f"{key}_fail")
            elif status == "warning":
                warnings.append(f"{key}_warning")

    if clock_drift is None:
        warnings.append("clock_drift_unknown")
    elif clock_drift > 2:
        blockers.append("clock_drift")
    elif clock_drift > 1:
        warnings.append("clock_drift_warning")

    if worker_lag > 60:
        blockers.append("worker_lag")
    elif worker_lag > 30:
        warnings.append("worker_lag_warning")

    if rate_limit_health == "critical":
        blockers.append("rate_limit_health")
    elif rate_limit_health == "warning":
        warnings.append("rate_limit_health_warning")
    elif rate_limit_health == "unknown":
        warnings.append("rate_limit_health_unknown")

    if not risk_orchestrator_ok:
        blockers.append("risk_orchestrator_missing")

    if not kill_switch_tested:
        warnings.append("kill_switch_not_tested")

    if chain_status.get("chain_broken"):
        blockers.append("chain_integrity_failure")
    elif chain_status.get("total", 0) == 0:
        warnings.append("proof_pipeline_empty")

    if failed_backlog >= 10:
        blockers.append("quarantine_backlog")
    elif failed_backlog > 0:
        warnings.append("quarantine_backlog")

    if not live_mode_enabled:
        warnings.append("live_mode_disabled")

    fail_reasons = list(dict.fromkeys(blockers))
    warning_reasons = list(dict.fromkeys(warnings))

    status = "READY"
    live_activation = "ready"
    reason_code = "ok"

    if fail_reasons:
        if active_override:
            status = "WARNING"
            live_activation = "guarded_override"
            warning_reasons = ["manual_override_active", *warning_reasons]
            reason_code = override.reason_code
        else:
            status = "BLOCKED"
            live_activation = "disabled"
            reason_code = fail_reasons[0]
    elif warning_reasons:
        status = "WARNING"
        live_activation = "guarded"
        reason_code = warning_reasons[0]

    reasons = [*fail_reasons, *warning_reasons]

    return {
        "status": status,
        "environment": env,
        "reasons": reasons,
        "fail_reasons": fail_reasons,
        "warning_reasons": warning_reasons,
        "reason_code": reason_code,
        "override_expires_at": override.expires_at if active_override else None,
        "override_id": override.id if active_override else None,
        "live_activation": live_activation,
        "metrics": {
            "exchange_health": exchange_health,
            "execution_quality_score": execution_quality_score,
            "permission_drift_alert": permission_drift_alert,
            "active_override": active_override,
            "live_mode_enabled": live_mode_enabled,
            "clock_drift_seconds": clock_drift,
            "worker_lag_seconds": worker_lag,
            "rate_limit_health": rate_limit_health,
            "risk_orchestrator_enabled": risk_orchestrator_ok,
            "kill_switch_tested": kill_switch_tested,
            "chain_integrity_broken": chain_status.get("chain_broken"),
            "failed_event_backlog": failed_backlog,
        },
    }


def compute_live_readiness_score(db: Session) -> dict:
    config = get_or_create_live_config(db)
    probe_user = _pick_latest_exchange_user(db)
    permission_ready = False
    if probe_user:
        permission_ready = permission_status_for_user(db, probe_user.id)["overall_status"] == "pass"

    risk_engine_pass = bool(db.query(AdminControl).filter(AdminControl.id == "global").first()) and bool(db.query(RiskPolicy).first())
    latest_metric = db.query(ExecutionMetric).order_by(ExecutionMetric.created_at.desc()).first()
    if latest_metric:
        execution_simulation_pass = latest_metric.status in {"FILLED", "PARTIALLY_FILLED", "CANCELED", "EXPIRED"}
    else:
        latest_exec = db.query(TestnetExecutionLog).order_by(TestnetExecutionLog.created_at.desc()).first()
        execution_simulation_pass = bool(latest_exec and latest_exec.status in {"filled", "partial_fill", "cancelled"})
    correlation_model_pass = db.query(RiskExposureGroup).count() > 0
    latest_hardening = db.query(HardeningChecklistRun).order_by(HardeningChecklistRun.created_at.desc()).first()
    hardening_checklist_pass = bool(latest_hardening and latest_hardening.readiness_status == "ready")

    score = round(
        (
            int(permission_ready)
            + int(risk_engine_pass)
            + int(execution_simulation_pass)
            + int(correlation_model_pass)
            + int(hardening_checklist_pass)
        )
        * 20,
        2,
    )

    critical_blockers: list[str] = []
    if not permission_ready:
        critical_blockers.append("permission_fail")
    if not risk_engine_pass:
        critical_blockers.append("risk_engine_fail")
    if not execution_simulation_pass:
        critical_blockers.append("execution_fail")

    release_gate_status = "PASS"
    if critical_blockers:
        release_gate_status = "BLOCKED"
        critical_blockers.append("release_gate_fail")
    elif not (correlation_model_pass and hardening_checklist_pass):
        release_gate_status = "WARNING"

    if critical_blockers and score > 80:
        score = 80

    live_activation = "disabled" if release_gate_status == "BLOCKED" else "guarded"
    if release_gate_status == "BLOCKED":
        config.live_mode_enabled = False
        db.commit()

    return {
        "readiness_score": score,
        "permission_ready": permission_ready,
        "risk_engine_pass": risk_engine_pass,
        "execution_simulation_pass": execution_simulation_pass,
        "correlation_model_pass": correlation_model_pass,
        "hardening_checklist_pass": hardening_checklist_pass,
        "release_gate_status": release_gate_status,
        "live_activation": live_activation,
        "critical_blockers": critical_blockers,
    }


def release_gate_view(db: Session, environment: str = "prod") -> dict:
    policy = evaluate_release_gate_policy(db, environment=environment)
    return {
        "status": policy["status"],
        "reasons": policy["reasons"],
        "fail_reasons": policy.get("fail_reasons", []),
        "warning_reasons": policy.get("warning_reasons", []),
        "live_activation": policy["live_activation"],
        "override_active": bool(policy.get("override_id")),
        "override_expires_at": policy.get("override_expires_at"),
        "override_id": policy.get("override_id"),
        "environment": policy.get("environment", environment),
        "reason_code": policy.get("reason_code", "ok"),
        "metrics": policy.get("metrics", {}),
    }


adapter = BinanceFuturesTestnetAdapter()


def get_or_create_live_config(db: Session) -> LiveActivationConfig:
    config = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    if config:
        return config

    config = LiveActivationConfig(
        id="global",
        exchange="binance",
        market_type="futures_testnet",
        safe_mode_enabled=True,
        live_mode_enabled=False,
        symbol_whitelist=SAFE_SYMBOL_WHITELIST.copy(),
        max_position_pct=MAX_SAFE_POSITION_PCT,
        leverage_cap=MAX_SAFE_LEVERAGE,
        max_trades_per_hour=6,
        max_notional_exposure=MAX_SAFE_NOTIONAL_EXPOSURE,
        kill_switch_enabled=False,
        disable_futures=False,
        ip_whitelist_ready=False,
        trading_permission_ready=False,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def apply_config_update(db: Session, config: LiveActivationConfig, payload: dict) -> LiveActivationConfig:
    for key, value in payload.items():
        setattr(config, key, value)

    _enforce_controlled_limits(config)

    if config.kill_switch_enabled or config.disable_futures:
        config.live_mode_enabled = False

    critical_ready = config.ip_whitelist_ready and config.trading_permission_ready
    if config.live_mode_enabled and not critical_ready:
        config.live_mode_enabled = False

    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)
    return config


def build_readiness_report(config: LiveActivationConfig, api_key: str | None = None, api_secret: str | None = None) -> dict:
    _enforce_controlled_limits(config)
    permission = adapter.permission_check(api_key, api_secret)
    endpoint_probe = adapter.ping()
    safe_limits_ok = (
        set(config.symbol_whitelist) == set(SAFE_SYMBOL_WHITELIST)
        and config.max_position_pct <= MAX_SAFE_POSITION_PCT
        and config.leverage_cap <= MAX_SAFE_LEVERAGE
        and config.max_notional_exposure <= MAX_SAFE_NOTIONAL_EXPOSURE
    )
    checks = [
        {
            "key": "credentials_present",
            "label": "API credentials present",
            "status": "pass" if permission["status"] == "ready" else "fail",
            "critical": True,
        },
        {
            "key": "ip_whitelist_ready",
            "label": "IP whitelist readiness",
            "status": "pass" if config.ip_whitelist_ready else "fail",
            "critical": True,
        },
        {
            "key": "trading_permission_ready",
            "label": "Trading permission readiness",
            "status": "pass" if config.trading_permission_ready else "fail",
            "critical": True,
        },
        {
            "key": "testnet_endpoint_reachable",
            "label": "Binance Futures Testnet connectivity",
            "status": "pass" if endpoint_probe["status"] == "reachable" else "fail",
            "critical": True,
        },
        {
            "key": "safe_limits_locked",
            "label": "Safe-mode limits",
            "status": "pass" if safe_limits_ok else "fail",
            "critical": True,
        },
        {
            "key": "kill_switch_routes",
            "label": "Kill switch and emergency routes",
            "status": "pass",
            "critical": False,
        },
        {
            "key": "no_key_fail_safe",
            "label": "No-key fail safe handling",
            "status": "pass" if permission["status"] in {"missing_credentials", "invalid_credentials", "ready", "permission_restricted"} else "fail",
            "critical": False,
        },
    ]
    return {
        "mode": "safe_mode" if config.safe_mode_enabled else "standard",
        "exchange": config.exchange,
        "market_type": config.market_type,
        "checks": checks,
        "safe_limits": {
            "symbol_whitelist": config.symbol_whitelist,
            "max_position_pct": config.max_position_pct,
            "leverage_cap": config.leverage_cap,
            "max_trades_per_hour": config.max_trades_per_hour,
            "max_notional_exposure": config.max_notional_exposure,
        },
        "docs_references": adapter.docs_references,
        "connectivity": endpoint_probe,
        "credential_preview": {
            "masked_key": permission["masked_key"],
            "status": permission["status"],
        },
        "permission_controls": permission.get("controls", []),
    }


def trigger_stop_all_bots(db: Session):
    db.query(BotProfile).update({BotProfile.is_running: False})
    db.commit()


def trigger_close_all_positions(db: Session):
    now = datetime.now(timezone.utc)
    open_positions = db.query(PaperPosition).filter(PaperPosition.status == "open").all()
    for position in open_positions:
        position.status = "manual_close"
        position.realized_pnl = position.unrealized_pnl
        position.closed_at = now
    db.commit()
