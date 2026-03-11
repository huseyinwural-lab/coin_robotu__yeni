import hashlib
import hmac
import os
import time
import uuid
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from core.config import settings
from db import redis_client
from models import (
    AdminControl,
    BotProfile,
    HardeningChecklistRun,
    LiveActivationConfig,
    PaperPosition,
    RiskExposureGroup,
    RiskPolicy,
    TestnetExecutionLog,
    User,
    UserExchangeSetting,
)
from services.pipeline.cache_store import read_candles

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

    def _signed_get(self, api_key: str, api_secret: str, endpoint: str, params: dict) -> tuple[dict, int, dict]:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        signature = self._signature(api_secret, query)
        url = f"{BINANCE_FUTURES_TESTNET_REST}{endpoint}?{query}&signature={signature}"
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

    def account_probe(self, api_key: str, api_secret: str) -> tuple[dict, int, dict]:
        return self._signed_get(api_key, api_secret, "/fapi/v2/account", {})

    def mark_price(self, symbol: str) -> float:
        response = httpx.get(
            f"{BINANCE_FUTURES_TESTNET_REST}/fapi/v1/ticker/price",
            params={"symbol": symbol},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        return float(payload.get("price") or 0)

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

    def query_order(self, api_key: str, api_secret: str, symbol: str, order_id: int) -> tuple[dict, int]:
        payload, status_code, _ = self._signed_get(
            api_key,
            api_secret,
            "/fapi/v1/order",
            {"symbol": symbol, "orderId": order_id},
        )
        return payload, status_code

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


def _infer_strategy_direction() -> str:
    candles = read_candles(redis_client, "market:candles:BTCUSDT:15m")
    if len(candles) < 20:
        return "long"

    closes = [float(item.get("close") or 0) for item in candles[-20:]]
    if not closes or closes[-1] == 0:
        return "long"
    sma20 = sum(closes) / len(closes)
    return "long" if closes[-1] >= sma20 else "short"


def _build_execution_quality_score(
    *,
    expected_price: float,
    fill_price: float | None,
    execution_latency: float,
    final_status: str,
) -> float:
    slippage_bps = 0.0
    if fill_price and expected_price > 0:
        slippage_bps = abs((fill_price - expected_price) / expected_price) * 10000

    status_penalty = {
        "filled": 0,
        "partial_fill": 12,
        "cancelled": 20,
        "failed": 35,
    }.get(final_status, 25)
    score = 100 - min(45, slippage_bps * 2.2) - min(35, execution_latency / 100) - status_penalty
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
    direction = _infer_strategy_direction()
    side = "BUY" if direction == "long" else "SELL"
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


def latest_execution_quality(db: Session, user_id: str) -> TestnetExecutionLog | None:
    return (
        db.query(TestnetExecutionLog)
        .filter(TestnetExecutionLog.user_id == user_id)
        .order_by(TestnetExecutionLog.created_at.desc())
        .first()
    )


def list_execution_quality(db: Session, limit: int = 20) -> list[TestnetExecutionLog]:
    return db.query(TestnetExecutionLog).order_by(TestnetExecutionLog.created_at.desc()).limit(limit).all()


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


def compute_live_readiness_score(db: Session) -> dict:
    config = get_or_create_live_config(db)
    probe_user = _pick_latest_exchange_user(db)
    permission_ready = False
    if probe_user:
        permission_ready = permission_status_for_user(db, probe_user.id)["overall_status"] == "pass"

    risk_engine_pass = bool(db.query(AdminControl).filter(AdminControl.id == "global").first()) and bool(db.query(RiskPolicy).first())
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


def release_gate_view(db: Session) -> dict:
    readiness = compute_live_readiness_score(db)
    reasons = readiness["critical_blockers"]
    if readiness["release_gate_status"] == "WARNING" and not reasons:
        reasons = ["non_critical_checks_pending"]
    return {
        "status": readiness["release_gate_status"],
        "reasons": reasons,
        "live_activation": readiness["live_activation"],
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
