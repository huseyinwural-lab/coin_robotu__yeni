import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from sqlalchemy.orm import Session

from models import BotProfile, LiveActivationConfig, PaperPosition

BINANCE_FUTURES_TESTNET_REST = "https://testnet.binancefuture.com"
BINANCE_FUTURES_TESTNET_WS = "wss://stream.binancefuture.com/ws"
SAFE_SYMBOL_WHITELIST = ["BTCUSDT"]
MAX_SAFE_POSITION_PCT = 0.1
MAX_SAFE_LEVERAGE = 1
MAX_SAFE_NOTIONAL_EXPOSURE = 150


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

    def _signed_account_probe(self, api_key: str, api_secret: str) -> tuple[dict, int]:
        params = {"timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        signature = self._signature(api_secret, query)
        url = f"{BINANCE_FUTURES_TESTNET_REST}/fapi/v2/account?{query}&signature={signature}"
        response = httpx.get(url, headers={"X-MBX-APIKEY": api_key}, timeout=8)
        payload = response.json() if response.content else {}
        return payload, response.status_code

    def permission_check(self, api_key: str | None, api_secret: str | None) -> dict:
        has_key = bool(api_key and api_key.strip())
        has_secret = bool(api_secret and api_secret.strip())
        key = api_key.strip() if api_key else None
        secret = api_secret.strip() if api_secret else None
        probe = self.ping()

        if not has_key or not has_secret:
            return {
                "api_key_present": has_key,
                "api_secret_present": has_secret,
                "masked_key": self.mask_api_key(key),
                "credential_fingerprint": self.credential_fingerprint(key, secret),
                "status": "missing_credentials",
                "message": "API key/secret eksik. Sistem fail-safe modda kaldı, canlı emir gönderilmez.",
            }

        try:
            payload, status_code = self._signed_account_probe(key, secret)
            if status_code == 200:
                can_trade = bool(payload.get("canTrade", True))
                return {
                    "api_key_present": has_key,
                    "api_secret_present": has_secret,
                    "masked_key": self.mask_api_key(key),
                    "credential_fingerprint": self.credential_fingerprint(key, secret),
                    "status": "ready" if can_trade else "permission_restricted",
                    "message": "Credentials doğrulandı (testnet)." if can_trade else "Credentials doğrulandı ancak trade yetkisi kapalı.",
                }

            error_code = payload.get("code") if isinstance(payload, dict) else None
            if status_code in {401, 403} or error_code in {-2015, -2014, -1022}:
                return {
                    "api_key_present": has_key,
                    "api_secret_present": has_secret,
                    "masked_key": self.mask_api_key(key),
                    "credential_fingerprint": self.credential_fingerprint(key, secret),
                    "status": "invalid_credentials",
                    "message": "API key/secret geçersiz veya imza doğrulaması başarısız.",
                }

            return {
                "api_key_present": has_key,
                "api_secret_present": has_secret,
                "masked_key": self.mask_api_key(key),
                "credential_fingerprint": self.credential_fingerprint(key, secret),
                "status": "exchange_error",
                "message": f"Exchange yanıtı beklenmeyen durumda: status={status_code}, probe={probe['status']}",
            }
        except httpx.HTTPError as exc:
            return {
                "api_key_present": has_key,
                "api_secret_present": has_secret,
                "masked_key": self.mask_api_key(key),
                "credential_fingerprint": self.credential_fingerprint(key, secret),
                "status": "exchange_unreachable",
                "message": f"Testnet doğrulama isteği başarısız: {exc}",
            }


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
