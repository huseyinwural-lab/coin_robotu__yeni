import csv
import hashlib
import hmac
import io
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from core.users.user_exchange_connector import decrypt_exchange_secret
from models import CommercialTrade, ExchangeReconciliationLog, PnlRecord, User, UserExchangeConnection
from services.credential_resolution_service import resolve_exchange_credentials

STABLE_QUOTES = ("USDT", "USTC", "BUSD", "USDC", "FDUSD", "USD")
DEFAULT_WINDOW_DAYS = 7
MAX_FUTURES_WINDOW_MS = 7 * 24 * 60 * 60 * 1000
MAX_SPOT_WINDOW_MS = 24 * 60 * 60 * 1000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_environment(value: str | None) -> str:
    candidate = (value or "testnet").strip().lower()
    return candidate if candidate in {"testnet", "live"} else "testnet"


def _normalize_market_types(items: list[str] | None) -> list[str]:
    if not items:
        return ["spot", "futures"]
    normalized = []
    for raw in items:
        candidate = str(raw or "").strip().lower()
        canonical = ""
        if candidate == "spot":
            canonical = "spot"
        elif candidate in {"futures", "usdt_perp", "coin_perp"}:
            canonical = "futures"
        if canonical and canonical not in normalized:
            normalized.append(canonical)
    return normalized or ["spot", "futures"]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dt_to_ms(dt: datetime | None, fallback: int) -> int:
    if dt is None:
        return fallback
    return int(dt.timestamp() * 1000)


def _default_start_ms() -> int:
    return int((_now() - timedelta(days=DEFAULT_WINDOW_DAYS)).timestamp() * 1000)


def _iter_windows(start_ms: int, end_ms: int, max_span_ms: int) -> list[tuple[int, int]]:
    if end_ms <= start_ms:
        return [(start_ms, end_ms)]
    windows: list[tuple[int, int]] = []
    cursor = int(start_ms)
    final = int(end_ms)
    while cursor <= final:
        chunk_end = min(cursor + max_span_ms - 1, final)
        windows.append((cursor, chunk_end))
        cursor = chunk_end + 1
    return windows


def _extract_assets(symbol: str) -> tuple[str, str]:
    upper = str(symbol or "").strip().upper()
    for quote in sorted(STABLE_QUOTES, key=len, reverse=True):
        if upper.endswith(quote) and len(upper) > len(quote):
            return upper[: -len(quote)], quote
    if len(upper) > 3:
        return upper[:-3], upper[-3:]
    return upper, ""


class BinanceCommercialClient:
    def __init__(self, *, api_key: str, api_secret: str, environment: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.environment = _normalize_environment(environment)
        default_spot_base = (
            "https://testnet.binance.vision" if self.environment == "testnet" else "https://api.binance.com"
        )
        default_futures_base = (
            "https://testnet.binancefuture.com" if self.environment == "testnet" else "https://fapi.binance.com"
        )
        if self.environment == "testnet":
            spot_override = os.environ.get("BINANCE_SPOT_TESTNET_BASE_URL") or os.environ.get("BINANCE_SPOT_BASE_URL")
            futures_override = os.environ.get("BINANCE_FUTURES_TESTNET_BASE_URL") or os.environ.get("BINANCE_FUTURES_BASE_URL")
        else:
            spot_override = os.environ.get("BINANCE_SPOT_LIVE_BASE_URL") or os.environ.get("BINANCE_SPOT_BASE_URL")
            futures_override = os.environ.get("BINANCE_FUTURES_LIVE_BASE_URL") or os.environ.get("BINANCE_FUTURES_BASE_URL")

        self.spot_base_url = str(spot_override or default_spot_base).strip().rstrip("/")
        self.futures_base_url = str(futures_override or default_futures_base).strip().rstrip("/")
        generic_proxy_token = os.environ.get("BINANCE_PROXY_TOKEN")
        if self.environment == "testnet":
            spot_token = os.environ.get("BINANCE_SPOT_TESTNET_PROXY_TOKEN")
            futures_token = os.environ.get("BINANCE_FUTURES_TESTNET_PROXY_TOKEN")
        else:
            spot_token = os.environ.get("BINANCE_SPOT_LIVE_PROXY_TOKEN")
            futures_token = os.environ.get("BINANCE_FUTURES_LIVE_PROXY_TOKEN")
        self.spot_proxy_token = spot_token or os.environ.get("BINANCE_SPOT_PROXY_TOKEN") or generic_proxy_token
        self.futures_proxy_token = futures_token or os.environ.get("BINANCE_FUTURES_PROXY_TOKEN") or generic_proxy_token
        self._price_cache: dict[str, float] = {}

    @staticmethod
    def _sign(secret: str, query_string: str) -> str:
        return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

    def _request_headers(self, *, base_url: str) -> dict[str, str]:
        normalized = str(base_url or "").rstrip("/")
        token = self.futures_proxy_token if normalized == self.futures_base_url else self.spot_proxy_token
        headers = {"X-MBX-APIKEY": self.api_key}
        if token:
            headers["X-Proxy-Token"] = token
        return headers

    def _public_headers(self, *, base_url: str) -> dict[str, str]:
        normalized = str(base_url or "").rstrip("/")
        token = self.futures_proxy_token if normalized == self.futures_base_url else self.spot_proxy_token
        if not token:
            return {}
        return {"X-Proxy-Token": token}

    def _signed_request(self, *, method: str, base_url: str, endpoint: str, params: dict | None = None) -> dict | list:
        for attempt in range(3):
            raw_params = {**(params or {})}
            raw_params["timestamp"] = int(time.time() * 1000)
            raw_params["recvWindow"] = 60000
            query_string = urlencode(raw_params)
            signature = self._sign(self.api_secret, query_string)
            url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
            try:
                with httpx.Client(timeout=20.0) as client:
                    response = client.request(method, url, headers=self._request_headers(base_url=base_url))
            except httpx.HTTPError as exc:
                if attempt >= 2:
                    raise ValueError(f"binance_transport_error:{exc}") from exc
                time.sleep(0.7 * (attempt + 1))
                continue

            payload = response.json() if response.content else {}
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(0.7 * (attempt + 1))
                continue
            if response.status_code >= 400:
                code = payload.get("code") if isinstance(payload, dict) else None
                msg = payload.get("msg") if isinstance(payload, dict) else "binance_error"
                raise ValueError(f"binance_request_failed:{response.status_code}:{code}:{msg}")
            return payload
        raise ValueError("binance_request_failed:unknown")

    def _api_key_request(self, *, method: str, base_url: str, endpoint: str) -> dict:
        for attempt in range(3):
            try:
                with httpx.Client(timeout=15.0) as client:
                    response = client.request(method, f"{base_url}{endpoint}", headers=self._request_headers(base_url=base_url))
            except httpx.HTTPError as exc:
                if attempt >= 2:
                    raise ValueError(f"binance_transport_error:{exc}") from exc
                time.sleep(0.5 * (attempt + 1))
                continue

            payload = response.json() if response.content else {}
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                code = payload.get("code") if isinstance(payload, dict) else None
                msg = payload.get("msg") if isinstance(payload, dict) else "binance_error"
                raise ValueError(f"binance_request_failed:{response.status_code}:{code}:{msg}")
            return payload
        raise ValueError("binance_request_failed:unknown")

    def fetch_spot_trades(
        self,
        *,
        symbol: str,
        start_time_ms: int | None,
        end_time_ms: int | None,
        limit: int,
    ) -> list[dict]:
        params: dict = {"symbol": symbol.upper(), "limit": max(1, min(int(limit), 1000))}
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        payload = self._signed_request(method="GET", base_url=self.spot_base_url, endpoint="/api/v3/myTrades", params=params)
        return payload if isinstance(payload, list) else []

    def fetch_futures_trades(
        self,
        *,
        symbol: str | None,
        start_time_ms: int | None,
        end_time_ms: int | None,
        limit: int,
    ) -> list[dict]:
        params: dict = {"limit": max(1, min(int(limit), 1000))}
        if symbol:
            params["symbol"] = symbol.upper()
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        payload = self._signed_request(method="GET", base_url=self.futures_base_url, endpoint="/fapi/v1/userTrades", params=params)
        return payload if isinstance(payload, list) else []

    def fetch_futures_position_risk(self) -> list[dict]:
        payload = self._signed_request(method="GET", base_url=self.futures_base_url, endpoint="/fapi/v2/positionRisk", params={})
        return payload if isinstance(payload, list) else []

    def fetch_spot_account(self) -> dict:
        payload = self._signed_request(method="GET", base_url=self.spot_base_url, endpoint="/api/v3/account", params={})
        return payload if isinstance(payload, dict) else {}

    def fetch_futures_account(self) -> dict:
        payload = self._signed_request(method="GET", base_url=self.futures_base_url, endpoint="/fapi/v2/account", params={})
        return payload if isinstance(payload, dict) else {}

    def fetch_futures_funding_income(self, *, start_time_ms: int | None, end_time_ms: int | None) -> list[dict]:
        params: dict = {"incomeType": "FUNDING_FEE", "limit": 1000}
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        payload = self._signed_request(method="GET", base_url=self.futures_base_url, endpoint="/fapi/v1/income", params=params)
        return payload if isinstance(payload, list) else []

    def get_spot_price(self, symbol: str) -> float:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return 0.0
        if normalized in self._price_cache:
            return self._price_cache[normalized]
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{self.spot_base_url}/api/v3/ticker/price",
                params={"symbol": normalized},
                headers=self._public_headers(base_url=self.spot_base_url),
            )
        payload = response.json() if response.content else {}
        price = _safe_float(payload.get("price"), 0.0) if response.status_code < 400 else 0.0
        self._price_cache[normalized] = price
        return price

    def bootstrap_user_data_streams(self, market_types: list[str]) -> dict:
        streams: dict[str, dict] = {}
        normalized = set(_normalize_market_types(market_types))
        if "spot" in normalized:
            payload = self._api_key_request(method="POST", base_url=self.spot_base_url, endpoint="/api/v3/userDataStream")
            listen_key = str(payload.get("listenKey") or "").strip()
            ws_base = (
                "wss://testnet.binance.vision/ws" if self.environment == "testnet" else "wss://stream.binance.com:9443/ws"
            )
            streams["spot"] = {
                "listen_key": listen_key,
                "ws_url": f"{ws_base}/{listen_key}" if listen_key else "",
            }
        if "futures" in normalized:
            payload = self._api_key_request(method="POST", base_url=self.futures_base_url, endpoint="/fapi/v1/listenKey")
            listen_key = str(payload.get("listenKey") or "").strip()
            ws_base = (
                "wss://stream.binancefuture.com/ws" if self.environment == "testnet" else "wss://fstream.binance.com/ws"
            )
            streams["futures"] = {
                "listen_key": listen_key,
                "ws_url": f"{ws_base}/{listen_key}" if listen_key else "",
            }
        return streams


def _asset_amount_to_usd(
    client: BinanceCommercialClient,
    *,
    amount: float,
    asset: str,
    quote_asset: str,
    executed_price: float,
) -> float:
    clean_amount = _safe_float(amount, 0.0)
    if clean_amount == 0:
        return 0.0
    normalized_asset = str(asset or "").strip().upper()
    normalized_quote = str(quote_asset or "").strip().upper()
    if normalized_asset in STABLE_QUOTES:
        return clean_amount
    if normalized_asset and normalized_asset == normalized_quote and normalized_quote in STABLE_QUOTES:
        return clean_amount
    if normalized_quote in STABLE_QUOTES and normalized_asset:
        if normalized_asset in {"BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"}:
            return clean_amount * max(_safe_float(executed_price, 0.0), 0.0)
    if not normalized_asset:
        return 0.0
    conversion_symbol = f"{normalized_asset}USDT"
    conversion_price = client.get_spot_price(conversion_symbol)
    if conversion_price <= 0:
        return 0.0
    return clean_amount * conversion_price


def _resolve_user_and_market_credentials(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    required_markets: list[str] | None = None,
) -> tuple[User, dict[str, dict]]:
    user = None
    if target_user_id:
        user = db.query(User).filter(User.id == target_user_id).first()
    if user is None and target_user_email:
        user = db.query(User).filter(User.email == target_user_email.strip().lower()).first()
    if user is None:
        raise ValueError("target_user_not_found")

    env = _normalize_environment(environment)
    by_market_credentials: dict[str, dict] = {}
    markets = _normalize_market_types(required_markets)
    for market in markets:
        resolved = resolve_exchange_credentials(
            db,
            user_id=user.id,
            exchange="binance",
            market_type=market,
            environment=env,
            purpose="execution_fallback",
            include_secrets=True,
        )
        by_market_credentials[market] = {
            "connection_id": (resolved.get("audit_metadata") or {}).get("connection_id"),
            "api_key": resolved["api_key"],
            "api_secret": resolved["api_secret"],
            "source": resolved.get("source"),
            "effective_base_url": resolved.get("effective_base_url"),
            "audit_metadata": resolved.get("audit_metadata") or {},
        }

    return user, by_market_credentials


def _build_spot_trade_row(
    *,
    user_id: str,
    connection_id: str,
    environment: str,
    symbol: str,
    payload: dict,
    client: BinanceCommercialClient,
    source: str,
) -> CommercialTrade:
    base_asset, quote_asset = _extract_assets(symbol)
    qty = _safe_float(payload.get("qty"), 0.0)
    price = _safe_float(payload.get("price"), 0.0)
    quote_qty = _safe_float(payload.get("quoteQty"), qty * price)
    commission_amount = _safe_float(payload.get("commission"), 0.0)
    commission_asset = str(payload.get("commissionAsset") or quote_asset or "USDT").upper()
    commission_usd = _asset_amount_to_usd(
        client,
        amount=commission_amount,
        asset=commission_asset,
        quote_asset=quote_asset,
        executed_price=price,
    )
    trade_time = datetime.fromtimestamp((_safe_float(payload.get("time"), 0.0) or 0) / 1000, tz=timezone.utc)

    return CommercialTrade(
        user_id=user_id,
        connection_id=connection_id,
        exchange="binance",
        market_type="spot",
        environment=environment,
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        side="BUY" if bool(payload.get("isBuyer")) else "SELL",
        position_side=None,
        exchange_trade_id=f"spot:{payload.get('id')}",
        order_id=str(payload.get("orderId")) if payload.get("orderId") is not None else None,
        client_order_id=str(payload.get("clientOrderId")) if payload.get("clientOrderId") else None,
        trade_time=trade_time,
        executed_qty=qty,
        executed_price=price,
        quote_qty=quote_qty,
        commission_amount=commission_amount,
        commission_asset=commission_asset,
        commission_usd=commission_usd,
        funding_fee_amount=0.0,
        funding_fee_asset=quote_asset,
        funding_fee_usd=0.0,
        realized_pnl_amount=0.0,
        realized_pnl_asset=quote_asset,
        realized_pnl_usd=0.0,
        is_buyer=bool(payload.get("isBuyer")),
        is_maker=bool(payload.get("isMaker")),
        source=source,
        raw_payload=payload,
        ingested_at=_now(),
        updated_at=_now(),
    )


def _build_futures_trade_row(
    *,
    user_id: str,
    connection_id: str,
    environment: str,
    symbol: str,
    payload: dict,
    client: BinanceCommercialClient,
    source: str,
) -> CommercialTrade:
    base_asset, quote_asset = _extract_assets(symbol)
    qty = _safe_float(payload.get("qty"), 0.0)
    price = _safe_float(payload.get("price"), 0.0)
    quote_qty = _safe_float(payload.get("quoteQty"), qty * price)
    commission_amount = _safe_float(payload.get("commission"), 0.0)
    commission_asset = str(payload.get("commissionAsset") or quote_asset or "USDT").upper()
    realized_pnl_amount = _safe_float(payload.get("realizedPnl"), 0.0)
    realized_pnl_asset = quote_asset or "USDT"

    commission_usd = _asset_amount_to_usd(
        client,
        amount=commission_amount,
        asset=commission_asset,
        quote_asset=quote_asset,
        executed_price=price,
    )
    realized_pnl_usd = _asset_amount_to_usd(
        client,
        amount=realized_pnl_amount,
        asset=realized_pnl_asset,
        quote_asset=quote_asset,
        executed_price=price,
    )
    trade_time = datetime.fromtimestamp((_safe_float(payload.get("time"), 0.0) or 0) / 1000, tz=timezone.utc)

    side = str(payload.get("side") or "BUY").strip().upper() or "BUY"
    return CommercialTrade(
        user_id=user_id,
        connection_id=connection_id,
        exchange="binance",
        market_type="futures",
        environment=environment,
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        side=side,
        position_side=str(payload.get("positionSide") or "BOTH"),
        exchange_trade_id=f"futures:{payload.get('id')}",
        order_id=str(payload.get("orderId")) if payload.get("orderId") is not None else None,
        client_order_id=str(payload.get("clientOrderId")) if payload.get("clientOrderId") else None,
        trade_time=trade_time,
        executed_qty=qty,
        executed_price=price,
        quote_qty=quote_qty,
        commission_amount=commission_amount,
        commission_asset=commission_asset,
        commission_usd=commission_usd,
        funding_fee_amount=0.0,
        funding_fee_asset=quote_asset,
        funding_fee_usd=0.0,
        realized_pnl_amount=realized_pnl_amount,
        realized_pnl_asset=realized_pnl_asset,
        realized_pnl_usd=realized_pnl_usd,
        is_buyer=bool(payload.get("buyer")),
        is_maker=bool(payload.get("maker")),
        source=source,
        raw_payload=payload,
        ingested_at=_now(),
        updated_at=_now(),
    )


def _trade_exists(db: Session, row: CommercialTrade) -> bool:
    found = (
        db.query(CommercialTrade.id)
        .filter(
            CommercialTrade.user_id == row.user_id,
            CommercialTrade.exchange == row.exchange,
            CommercialTrade.market_type == row.market_type,
            CommercialTrade.environment == row.environment,
            CommercialTrade.exchange_trade_id == row.exchange_trade_id,
        )
        .first()
    )
    return found is not None


def run_rest_trade_ingestion(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    market_types: list[str] | None,
    symbols: list[str] | None,
    start_ts: str | None,
    end_ts: str | None,
    limit_per_symbol: int,
    source: str = "rest",
) -> dict:
    env = _normalize_environment(environment)
    markets = _normalize_market_types(market_types)
    clean_symbols = [str(item or "").strip().upper() for item in (symbols or []) if str(item or "").strip()]

    user, market_credentials = _resolve_user_and_market_credentials(
        db,
        target_user_id=target_user_id,
        target_user_email=target_user_email,
        environment=env,
        required_markets=markets,
    )

    start_ms = _dt_to_ms(_parse_iso(start_ts), _default_start_ms())
    end_ms = _dt_to_ms(_parse_iso(end_ts), int(_now().timestamp() * 1000))

    inserted = 0
    duplicate = 0
    fetched = 0
    market_summary: dict[str, dict] = {}

    for market in markets:
        market_ctx = market_credentials[market]
        client = BinanceCommercialClient(
            api_key=market_ctx["api_key"],
            api_secret=market_ctx["api_secret"],
            environment=env,
        )
        if market_ctx.get("effective_base_url"):
            if market == "spot":
                client.spot_base_url = str(market_ctx["effective_base_url"]).rstrip("/")
            else:
                client.futures_base_url = str(market_ctx["effective_base_url"]).rstrip("/")
        connection_id = market_ctx.get("connection_id")
        market_inserted = 0
        market_duplicate = 0
        market_fetched = 0

        if market == "spot":
            if not clean_symbols:
                raise ValueError("spot_symbols_required")
            for symbol in clean_symbols:
                for chunk_start, chunk_end in _iter_windows(start_ms, end_ms, MAX_SPOT_WINDOW_MS):
                    trades = client.fetch_spot_trades(
                        symbol=symbol,
                        start_time_ms=chunk_start,
                        end_time_ms=chunk_end,
                        limit=max(1, min(limit_per_symbol, 1000)),
                    )
                    market_fetched += len(trades)
                    for raw in trades:
                        row = _build_spot_trade_row(
                            user_id=user.id,
                            connection_id=connection_id,
                            environment=env,
                            symbol=symbol,
                            payload=raw,
                            client=client,
                            source=source,
                        )
                        if _trade_exists(db, row):
                            market_duplicate += 1
                            continue
                        db.add(row)
                        market_inserted += 1
        else:
            futures_symbols = clean_symbols or [None]
            for symbol in futures_symbols:
                for chunk_start, chunk_end in _iter_windows(start_ms, end_ms, MAX_FUTURES_WINDOW_MS):
                    trades = client.fetch_futures_trades(
                        symbol=symbol,
                        start_time_ms=chunk_start,
                        end_time_ms=chunk_end,
                        limit=max(1, min(limit_per_symbol, 1000)),
                    )
                    market_fetched += len(trades)
                    for raw in trades:
                        normalized_symbol = str(raw.get("symbol") or symbol or "").upper()
                        row = _build_futures_trade_row(
                            user_id=user.id,
                            connection_id=connection_id,
                            environment=env,
                            symbol=normalized_symbol,
                            payload=raw,
                            client=client,
                            source=source,
                        )
                        if _trade_exists(db, row):
                            market_duplicate += 1
                            continue
                        db.add(row)
                        market_inserted += 1

        market_summary[market] = {
            "fetched": market_fetched,
            "inserted": market_inserted,
            "duplicate": market_duplicate,
        }
        inserted += market_inserted
        duplicate += market_duplicate
        fetched += market_fetched

    db.commit()
    return {
        "status": "ok",
        "user_id": user.id,
        "user_email": user.email,
        "environment": env,
        "market_types": markets,
        "symbols": clean_symbols,
        "time_window": {"start_ts": start_ts, "end_ts": end_ts},
        "fetched": fetched,
        "inserted": inserted,
        "duplicate": duplicate,
        "market_summary": market_summary,
        "source": source,
        "generated_at": _now().isoformat(),
    }


def _build_spot_inventory(trades: list[CommercialTrade]) -> dict[str, dict[str, float]]:
    inventory: dict[str, dict[str, float]] = defaultdict(lambda: {"qty": 0.0, "cost": 0.0})
    rows = sorted([item for item in trades if item.market_type == "spot"], key=lambda item: item.trade_time)
    for row in rows:
        symbol = str(row.symbol or "").upper()
        qty = max(_safe_float(row.executed_qty), 0.0)
        price = max(_safe_float(row.executed_price), 0.0)
        side = str(row.side or "BUY").upper()
        state = inventory[symbol]
        if side == "BUY":
            state["qty"] += qty
            state["cost"] += qty * price
            continue
        if state["qty"] <= 0:
            continue
        sell_qty = min(state["qty"], qty)
        avg_cost = state["cost"] / state["qty"] if state["qty"] > 0 else 0.0
        state["qty"] -= sell_qty
        state["cost"] -= avg_cost * sell_qty
    return inventory


def _spot_unrealized_usd(client: BinanceCommercialClient, trades: list[CommercialTrade]) -> tuple[float, dict[str, dict]]:
    inventory = _build_spot_inventory(trades)
    total = 0.0
    by_symbol: dict[str, dict] = {}
    for symbol, state in inventory.items():
        qty = max(_safe_float(state.get("qty"), 0.0), 0.0)
        cost = max(_safe_float(state.get("cost"), 0.0), 0.0)
        if qty <= 0:
            continue
        mark = client.get_spot_price(symbol)
        mark_value = qty * mark
        unrealized = mark_value - cost
        total += unrealized
        by_symbol[symbol] = {
            "open_qty": round(qty, 8),
            "cost_basis_usd": round(cost, 8),
            "mark_price": round(mark, 8),
            "mark_value_usd": round(mark_value, 8),
            "unrealized_usd": round(unrealized, 8),
        }
    return total, by_symbol


def compute_and_persist_pnl(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    market_types: list[str] | None,
    start_ts: str | None,
    end_ts: str | None,
) -> dict:
    env = _normalize_environment(environment)
    markets = _normalize_market_types(market_types)
    user, market_credentials = _resolve_user_and_market_credentials(
        db,
        target_user_id=target_user_id,
        target_user_email=target_user_email,
        environment=env,
        required_markets=markets,
    )
    futures_client = None
    if "futures" in market_credentials:
        futures_ctx = market_credentials["futures"]
        futures_client = BinanceCommercialClient(
            api_key=futures_ctx["api_key"],
            api_secret=futures_ctx["api_secret"],
            environment=env,
        )
        if futures_ctx.get("effective_base_url"):
            futures_client.futures_base_url = str(futures_ctx["effective_base_url"]).rstrip("/")
    spot_client = None
    if "spot" in market_credentials:
        spot_ctx = market_credentials["spot"]
        spot_client = BinanceCommercialClient(
            api_key=spot_ctx["api_key"],
            api_secret=spot_ctx["api_secret"],
            environment=env,
        )
        if spot_ctx.get("effective_base_url"):
            spot_client.spot_base_url = str(spot_ctx["effective_base_url"]).rstrip("/")
    price_client = spot_client or futures_client
    if price_client is None:
        raise ValueError("binance_credentials_missing")

    start_dt = _parse_iso(start_ts)
    end_dt = _parse_iso(end_ts)

    query = db.query(CommercialTrade).filter(CommercialTrade.user_id == user.id, CommercialTrade.exchange == "binance", CommercialTrade.environment == env)
    if len(markets) == 1:
        query = query.filter(CommercialTrade.market_type == markets[0])
    elif len(markets) > 1:
        query = query.filter(CommercialTrade.market_type.in_(markets))
    if start_dt is not None:
        query = query.filter(CommercialTrade.trade_time >= start_dt)
    if end_dt is not None:
        query = query.filter(CommercialTrade.trade_time <= end_dt)
    trades = query.all()

    realized_gross = sum(_safe_float(item.realized_pnl_usd) for item in trades)
    commission_usd = sum(_safe_float(item.commission_usd) for item in trades)

    start_ms = _dt_to_ms(start_dt, _default_start_ms())
    end_ms = _dt_to_ms(end_dt, int(_now().timestamp() * 1000))
    funding_income_rows = []
    if futures_client is not None and "futures" in markets:
        funding_income_rows = futures_client.fetch_futures_funding_income(start_time_ms=start_ms, end_time_ms=end_ms)
    funding_usd = 0.0
    for row in funding_income_rows:
        income = _safe_float(row.get("income"), 0.0)
        asset = str(row.get("asset") or "USDT").upper()
        funding_usd += _asset_amount_to_usd(price_client, amount=income, asset=asset, quote_asset="USDT", executed_price=1.0)

    futures_unrealized = 0.0
    futures_positions: list[dict] = []
    if futures_client is not None and "futures" in markets:
        try:
            for item in futures_client.fetch_futures_position_risk():
                qty = _safe_float(item.get("positionAmt"), 0.0)
                if qty == 0:
                    continue
                unrealized = _safe_float(item.get("unRealizedProfit"), 0.0)
                futures_unrealized += unrealized
                futures_positions.append(
                    {
                        "symbol": item.get("symbol"),
                        "position_amt": qty,
                        "entry_price": _safe_float(item.get("entryPrice"), 0.0),
                        "mark_price": _safe_float(item.get("markPrice"), 0.0),
                        "unrealized_profit_usd": unrealized,
                    }
                )
        except Exception:
            futures_positions = []

    spot_unrealized = 0.0
    spot_inventory = {}
    if "spot" in markets:
        spot_unrealized, spot_inventory = _spot_unrealized_usd(price_client, trades)
    unrealized_gross = spot_unrealized + futures_unrealized
    trading_fee_usd = commission_usd
    realized_net = realized_gross - trading_fee_usd + funding_usd
    unrealized_net = unrealized_gross
    net_total = realized_net + unrealized_net

    record = PnlRecord(
        user_id=user.id,
        exchange="binance",
        market_type="all",
        environment=env,
        as_of=_now(),
        window_start=start_dt,
        window_end=end_dt,
        trade_count=len(trades),
        trading_fee_usd=round(trading_fee_usd, 8),
        commission_usd=round(commission_usd, 8),
        funding_usd=round(funding_usd, 8),
        realized_gross_usd=round(realized_gross, 8),
        unrealized_gross_usd=round(unrealized_gross, 8),
        realized_net_usd=round(realized_net, 8),
        unrealized_net_usd=round(unrealized_net, 8),
        net_total_usd=round(net_total, 8),
        pnl_source="canonical_trade_engine_v1",
        details={
            "futures_positions": futures_positions,
            "spot_inventory": spot_inventory,
            "funding_events": len(funding_income_rows),
            "market_scope": markets,
            "fee_breakdown": {
                "trading_fee_usd": round(trading_fee_usd, 8),
                "commission_usd": round(commission_usd, 8),
                "funding_usd": round(funding_usd, 8),
            },
        },
        created_at=_now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "status": "ok",
        "user_id": user.id,
        "user_email": user.email,
        "environment": env,
        "trade_count": len(trades),
        "realized": {
            "gross_usd": round(realized_gross, 8),
            "net_usd": round(realized_net, 8),
        },
        "unrealized": {
            "gross_usd": round(unrealized_gross, 8),
            "net_usd": round(unrealized_net, 8),
        },
        "fee_breakdown": {
            "trading_fee_usd": round(trading_fee_usd, 8),
            "commission_usd": round(commission_usd, 8),
            "funding_usd": round(funding_usd, 8),
        },
        "net_total_usd": round(net_total, 8),
        "record_id": record.id,
        "as_of": record.as_of.isoformat() if record.as_of else None,
    }


def run_exchange_reconciliation(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    market_types: list[str] | None,
    symbols: list[str] | None,
    start_ts: str | None,
    end_ts: str | None,
    limit_per_symbol: int,
    drift_tolerance_usd: float | None,
    drift_tolerance_pct: float | None,
) -> dict:
    env = _normalize_environment(environment)
    markets = _normalize_market_types(market_types)
    clean_symbols = [str(item or "").strip().upper() for item in (symbols or []) if str(item or "").strip()]

    user, market_credentials = _resolve_user_and_market_credentials(
        db,
        target_user_id=target_user_id,
        target_user_email=target_user_email,
        environment=env,
        required_markets=markets,
    )
    spot_client = None
    futures_client = None
    if "spot" in market_credentials:
        ctx = market_credentials["spot"]
        spot_client = BinanceCommercialClient(api_key=ctx["api_key"], api_secret=ctx["api_secret"], environment=env)
        if ctx.get("effective_base_url"):
            spot_client.spot_base_url = str(ctx["effective_base_url"]).rstrip("/")
    if "futures" in market_credentials:
        ctx = market_credentials["futures"]
        futures_client = BinanceCommercialClient(api_key=ctx["api_key"], api_secret=ctx["api_secret"], environment=env)
        if ctx.get("effective_base_url"):
            futures_client.futures_base_url = str(ctx["effective_base_url"]).rstrip("/")
    price_client = spot_client or futures_client

    start_dt = _parse_iso(start_ts)
    end_dt = _parse_iso(end_ts)
    start_ms = _dt_to_ms(start_dt, _default_start_ms())
    end_ms = _dt_to_ms(end_dt, int(_now().timestamp() * 1000))

    latest_trade = (
        db.query(CommercialTrade)
        .filter(CommercialTrade.user_id == user.id, CommercialTrade.exchange == "binance", CommercialTrade.environment == env)
        .order_by(CommercialTrade.ingested_at.desc())
        .first()
    )
    freshness_seconds = int((_now() - latest_trade.ingested_at).total_seconds()) if latest_trade and latest_trade.ingested_at else None

    internal_query = db.query(CommercialTrade).filter(
        CommercialTrade.user_id == user.id,
        CommercialTrade.exchange == "binance",
        CommercialTrade.environment == env,
        CommercialTrade.market_type.in_(markets),
    )
    if start_dt is not None:
        internal_query = internal_query.filter(CommercialTrade.trade_time >= start_dt)
    if end_dt is not None:
        internal_query = internal_query.filter(CommercialTrade.trade_time <= end_dt)
    if clean_symbols:
        internal_query = internal_query.filter(CommercialTrade.symbol.in_(clean_symbols))
    internal_trades = internal_query.all()

    internal_id_counts: dict[str, int] = defaultdict(int)
    for row in internal_trades:
        internal_id_counts[row.exchange_trade_id] += 1

    duplicate_trade_count = sum(count - 1 for count in internal_id_counts.values() if count > 1)
    exchange_trade_ids: set[str] = set()
    exchange_realized_usd = 0.0
    requested_symbols = clean_symbols.copy()

    for market in markets:
        if market == "spot":
            if not clean_symbols:
                continue
            if spot_client is None:
                raise ValueError("binance_credentials_missing")
            for symbol in clean_symbols:
                for chunk_start, chunk_end in _iter_windows(start_ms, end_ms, MAX_SPOT_WINDOW_MS):
                    for raw in spot_client.fetch_spot_trades(
                        symbol=symbol,
                        start_time_ms=chunk_start,
                        end_time_ms=chunk_end,
                        limit=max(1, min(limit_per_symbol, 1000)),
                    ):
                        exchange_trade_ids.add(f"spot:{raw.get('id')}")
        else:
            if futures_client is None:
                raise ValueError("binance_credentials_missing")
            futures_symbols = clean_symbols or [None]
            for symbol in futures_symbols:
                for chunk_start, chunk_end in _iter_windows(start_ms, end_ms, MAX_FUTURES_WINDOW_MS):
                    for raw in futures_client.fetch_futures_trades(
                        symbol=symbol,
                        start_time_ms=chunk_start,
                        end_time_ms=chunk_end,
                        limit=max(1, min(limit_per_symbol, 1000)),
                    ):
                        exchange_trade_ids.add(f"futures:{raw.get('id')}")
                        pnl_amount = _safe_float(raw.get("realizedPnl"), 0.0)
                        exchange_realized_usd += _asset_amount_to_usd(
                            price_client,
                            amount=pnl_amount,
                            asset="USDT",
                            quote_asset="USDT",
                            executed_price=1.0,
                        )

    internal_ids = set(internal_id_counts.keys())
    missing_ids = sorted(list(exchange_trade_ids - internal_ids))
    missing_trade_count = len(missing_ids)

    internal_realized_usd = sum(_safe_float(item.realized_pnl_usd) for item in internal_trades if item.market_type == "futures")
    pnl_drift_usd = round(exchange_realized_usd - internal_realized_usd, 8)

    position_drift_usd = 0.0
    if "futures" in markets:
        if futures_client is None:
            raise ValueError("binance_credentials_missing")
        exchange_position_rows = futures_client.fetch_futures_position_risk()
        if clean_symbols:
            allowed_symbols = {item.upper() for item in clean_symbols}
            exchange_position_rows = [row for row in exchange_position_rows if str(row.get("symbol") or "").upper() in allowed_symbols]
        exchange_positions = {str(item.get("symbol") or "").upper(): _safe_float(item.get("positionAmt"), 0.0) for item in exchange_position_rows}
        exchange_marks = {str(item.get("symbol") or "").upper(): _safe_float(item.get("markPrice"), 0.0) for item in exchange_position_rows}
        internal_positions: dict[str, float] = defaultdict(float)
        for row in internal_trades:
            if row.market_type != "futures":
                continue
            multiplier = 1 if str(row.side or "BUY").upper() == "BUY" else -1
            internal_positions[str(row.symbol).upper()] += multiplier * _safe_float(row.executed_qty)
        for symbol in set(exchange_positions.keys()) | set(internal_positions.keys()):
            diff_qty = abs(exchange_positions.get(symbol, 0.0) - internal_positions.get(symbol, 0.0))
            mark_price = exchange_marks.get(symbol, 0.0)
            position_drift_usd += diff_qty * mark_price

    balance_drift_usd = 0.0
    try:
        spot_total = 0.0
        if "spot" in markets:
            if spot_client is None:
                raise ValueError("binance_credentials_missing")
            spot_account = spot_client.fetch_spot_account()
            for item in (spot_account.get("balances") or []):
                asset = str(item.get("asset") or "").upper()
                amount = _safe_float(item.get("free"), 0.0) + _safe_float(item.get("locked"), 0.0)
                if amount <= 0:
                    continue
                if asset in STABLE_QUOTES:
                    spot_total += amount
                else:
                    spot_total += amount * price_client.get_spot_price(f"{asset}USDT")

        futures_account = futures_client.fetch_futures_account() if "futures" in markets and futures_client else {}
        futures_wallet = _safe_float(futures_account.get("totalWalletBalance"), 0.0)
        exchange_equity = spot_total + futures_wallet
        internal_net = sum(_safe_float(item.realized_pnl_usd) for item in internal_trades) - sum(_safe_float(item.commission_usd) for item in internal_trades)
        balance_drift_usd = exchange_equity - internal_net
    except Exception:
        balance_drift_usd = 0.0

    pct_value = _safe_float(drift_tolerance_pct, 0.0)
    if pct_value > 0:
        tolerance_base = max(abs(exchange_realized_usd), abs(internal_realized_usd), 1.0)
        effective_tolerance_usd = max(tolerance_base * (pct_value / 100.0), 0.01)
    else:
        effective_tolerance_usd = max(_safe_float(drift_tolerance_usd, 5.0), 0.01)

    missing_data_alert = bool((freshness_seconds is not None and freshness_seconds > 900) or missing_trade_count > 0)
    drift_within_tolerance = (
        abs(pnl_drift_usd) <= effective_tolerance_usd
        and abs(position_drift_usd) <= effective_tolerance_usd
        and missing_trade_count == 0
    )

    log = ExchangeReconciliationLog(
        user_id=user.id,
        connection_id=market_credentials[markets[0]].get("connection_id") if markets else None,
        exchange="binance",
        market_type="all" if len(markets) > 1 else markets[0],
        environment=env,
        run_source="manual",
        status="completed",
        started_at=_now(),
        completed_at=_now(),
        requested_symbols=requested_symbols,
        internal_trade_count=len(internal_ids),
        exchange_trade_count=len(exchange_trade_ids),
        missing_trade_count=missing_trade_count,
        duplicate_trade_count=duplicate_trade_count,
        balance_drift_usd=round(balance_drift_usd, 8),
        position_drift_usd=round(position_drift_usd, 8),
        pnl_drift_usd=round(pnl_drift_usd, 8),
        drift_tolerance_usd=round(effective_tolerance_usd, 8),
        drift_within_tolerance=drift_within_tolerance,
        freshness_seconds=freshness_seconds,
        missing_data_alert=missing_data_alert,
        missing_symbols=[],
        details={
            "missing_trade_ids": missing_ids[:500],
            "markets": markets,
            "internal_realized_usd": round(internal_realized_usd, 8),
            "exchange_realized_usd": round(exchange_realized_usd, 8),
            "drift_tolerance_pct": pct_value if pct_value > 0 else None,
        },
        created_at=_now(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "status": "ok",
        "log_id": log.id,
        "user_id": user.id,
        "user_email": user.email,
        "environment": env,
        "markets": markets,
        "internal_trade_count": log.internal_trade_count,
        "exchange_trade_count": log.exchange_trade_count,
        "missing_trade_count": log.missing_trade_count,
        "duplicate_trade_count": log.duplicate_trade_count,
        "balance_drift_usd": log.balance_drift_usd,
        "position_drift_usd": log.position_drift_usd,
        "pnl_drift_usd": log.pnl_drift_usd,
        "drift_tolerance_usd": log.drift_tolerance_usd,
        "drift_tolerance_pct": pct_value if pct_value > 0 else None,
        "drift_within_tolerance": bool(log.drift_within_tolerance),
        "freshness_seconds": log.freshness_seconds,
        "missing_data_alert": bool(log.missing_data_alert),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def get_data_quality_snapshot(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    required_market_types: list[str] | None,
) -> dict:
    env = _normalize_environment(environment)
    markets = _normalize_market_types(required_market_types)
    user, _ = _resolve_user_and_market_credentials(
        db,
        target_user_id=target_user_id,
        target_user_email=target_user_email,
        environment=env,
        required_markets=markets,
    )

    latest_by_market: dict[str, CommercialTrade | None] = {}
    for market in markets:
        latest_by_market[market] = (
            db.query(CommercialTrade)
            .filter(
                CommercialTrade.user_id == user.id,
                CommercialTrade.exchange == "binance",
                CommercialTrade.environment == env,
                CommercialTrade.market_type == market,
            )
            .order_by(CommercialTrade.ingested_at.desc())
            .first()
        )

    latest_reconciliation = (
        db.query(ExchangeReconciliationLog)
        .filter(ExchangeReconciliationLog.user_id == user.id, ExchangeReconciliationLog.exchange == "binance", ExchangeReconciliationLog.environment == env)
        .order_by(ExchangeReconciliationLog.created_at.desc())
        .first()
    )

    freshness: dict[str, int | None] = {}
    alert_flags: dict[str, bool] = {}
    for market, row in latest_by_market.items():
        if row is None or row.ingested_at is None:
            freshness[market] = None
            alert_flags[market] = True
            continue
        seconds = int((_now() - row.ingested_at).total_seconds())
        freshness[market] = seconds
        alert_flags[market] = seconds > 900

    return {
        "status": "ok",
        "user_id": user.id,
        "user_email": user.email,
        "environment": env,
        "freshness_seconds": freshness,
        "missing_data_alert": any(alert_flags.values()),
        "market_alerts": alert_flags,
        "latest_reconciliation": {
            "log_id": latest_reconciliation.id if latest_reconciliation else None,
            "drift_within_tolerance": bool(latest_reconciliation.drift_within_tolerance) if latest_reconciliation else None,
            "freshness_seconds": latest_reconciliation.freshness_seconds if latest_reconciliation else None,
            "created_at": latest_reconciliation.created_at.isoformat() if latest_reconciliation and latest_reconciliation.created_at else None,
        },
    }


def get_live_transition_gate(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    required_market_types: list[str] | None,
) -> dict:
    env = _normalize_environment(environment)
    markets = _normalize_market_types(required_market_types)
    user, _ = _resolve_user_and_market_credentials(
        db,
        target_user_id=target_user_id,
        target_user_email=target_user_email,
        environment=env,
        required_markets=markets,
    )

    latest_trade = None
    market_ingest_coverage: dict[str, bool] = {}
    for market in markets:
        market_latest = (
            db.query(CommercialTrade)
            .filter(
                CommercialTrade.user_id == user.id,
                CommercialTrade.exchange == "binance",
                CommercialTrade.environment == env,
                CommercialTrade.market_type == market,
            )
            .order_by(CommercialTrade.ingested_at.desc())
            .first()
        )
        market_ingest_coverage[market] = market_latest is not None
        if latest_trade is None and market_latest is not None:
            latest_trade = market_latest

    if latest_trade is None:
        latest_trade = (
            db.query(CommercialTrade)
            .filter(CommercialTrade.user_id == user.id, CommercialTrade.exchange == "binance", CommercialTrade.environment == env)
            .order_by(CommercialTrade.ingested_at.desc())
            .first()
        )
    latest_pnl = (
        db.query(PnlRecord)
        .filter(PnlRecord.user_id == user.id, PnlRecord.exchange == "binance", PnlRecord.environment == env)
        .order_by(PnlRecord.as_of.desc())
        .first()
    )
    latest_reconciliation = (
        db.query(ExchangeReconciliationLog)
        .filter(ExchangeReconciliationLog.user_id == user.id, ExchangeReconciliationLog.exchange == "binance", ExchangeReconciliationLog.environment == env)
        .order_by(ExchangeReconciliationLog.created_at.desc())
        .first()
    )

    ingest_ok = all(market_ingest_coverage.values()) if market_ingest_coverage else latest_trade is not None
    pnl_ok = latest_pnl is not None and int(latest_pnl.trade_count or 0) > 0 and ingest_ok
    reconcile_scope_ok = False
    if latest_reconciliation is not None:
        if len(markets) > 1:
            reconcile_scope_ok = str(latest_reconciliation.market_type or "") == "all"
        else:
            reconcile_scope_ok = str(latest_reconciliation.market_type or "") in {"all", markets[0]}
    reconcile_ok = latest_reconciliation is not None and bool(latest_reconciliation.drift_within_tolerance) and reconcile_scope_ok

    return {
        "status": "ok",
        "user_id": user.id,
        "user_email": user.email,
        "environment": env,
        "required_market_types": markets,
        "controls": {
            "trade_ingest_ok": ingest_ok,
            "pnl_ok": pnl_ok,
            "reconciliation_ok": reconcile_ok,
            "market_ingest_coverage": market_ingest_coverage,
        },
        "live_transition_ready": bool(ingest_ok and pnl_ok and reconcile_ok),
        "evidence": {
            "latest_trade_ingested_at": latest_trade.ingested_at.isoformat() if latest_trade and latest_trade.ingested_at else None,
            "latest_pnl_as_of": latest_pnl.as_of.isoformat() if latest_pnl and latest_pnl.as_of else None,
            "latest_reconciliation_log_id": latest_reconciliation.id if latest_reconciliation else None,
            "latest_reconciliation_created_at": latest_reconciliation.created_at.isoformat() if latest_reconciliation and latest_reconciliation.created_at else None,
        },
    }


def export_standardized_trades_csv(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    market_type: str | None,
    symbol: str | None,
    start_ts: str | None,
    end_ts: str | None,
) -> tuple[bytes, str]:
    env = _normalize_environment(environment)
    user, _ = _resolve_user_and_market_credentials(
        db,
        target_user_id=target_user_id,
        target_user_email=target_user_email,
        environment=env,
    )
    query = db.query(CommercialTrade).filter(CommercialTrade.user_id == user.id, CommercialTrade.exchange == "binance", CommercialTrade.environment == env)
    if market_type:
        candidate = str(market_type).strip().lower()
        if candidate == "spot":
            query = query.filter(CommercialTrade.market_type == "spot")
        elif candidate in {"futures", "usdt_perp", "coin_perp"}:
            query = query.filter(CommercialTrade.market_type == "futures")
    if symbol:
        query = query.filter(CommercialTrade.symbol == str(symbol).strip().upper())
    start_dt = _parse_iso(start_ts)
    end_dt = _parse_iso(end_ts)
    if start_dt is not None:
        query = query.filter(CommercialTrade.trade_time >= start_dt)
    if end_dt is not None:
        query = query.filter(CommercialTrade.trade_time <= end_dt)

    rows = query.order_by(CommercialTrade.trade_time.asc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = [
        "trade_id",
        "user_id",
        "exchange",
        "market_type",
        "environment",
        "symbol",
        "base_asset",
        "quote_asset",
        "side",
        "position_side",
        "trade_time",
        "exchange_trade_id",
        "order_id",
        "client_order_id",
        "executed_qty",
        "executed_price",
        "quote_qty",
        "commission_amount",
        "commission_asset",
        "commission_usd",
        "funding_fee_amount",
        "funding_fee_asset",
        "funding_fee_usd",
        "realized_pnl_amount",
        "realized_pnl_asset",
        "realized_pnl_usd",
        "is_buyer",
        "is_maker",
        "source",
        "ingested_at",
    ]
    writer.writerow(header)
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.user_id,
                row.exchange,
                row.market_type,
                row.environment,
                row.symbol,
                row.base_asset,
                row.quote_asset,
                row.side,
                row.position_side,
                row.trade_time.isoformat() if row.trade_time else "",
                row.exchange_trade_id,
                row.order_id,
                row.client_order_id,
                row.executed_qty,
                row.executed_price,
                row.quote_qty,
                row.commission_amount,
                row.commission_asset,
                row.commission_usd,
                row.funding_fee_amount,
                row.funding_fee_asset,
                row.funding_fee_usd,
                row.realized_pnl_amount,
                row.realized_pnl_asset,
                row.realized_pnl_usd,
                row.is_buyer,
                row.is_maker,
                row.source,
                row.ingested_at.isoformat() if row.ingested_at else "",
            ]
        )
    payload = buffer.getvalue().encode("utf-8")
    filename = f"canonical_trades_{user.id}_{env}.csv"
    return payload, filename


def bootstrap_user_websocket_streams(
    db: Session,
    *,
    target_user_id: str | None,
    target_user_email: str | None,
    environment: str,
    market_types: list[str] | None,
) -> dict:
    env = _normalize_environment(environment)
    markets = _normalize_market_types(market_types)
    user, market_credentials = _resolve_user_and_market_credentials(
        db,
        target_user_id=target_user_id,
        target_user_email=target_user_email,
        environment=env,
        required_markets=markets,
    )
    streams: dict[str, dict] = {}
    for market in markets:
        ctx = market_credentials[market]
        client = BinanceCommercialClient(api_key=ctx["api_key"], api_secret=ctx["api_secret"], environment=env)
        if ctx.get("effective_base_url"):
            if market == "spot":
                client.spot_base_url = str(ctx["effective_base_url"]).rstrip("/")
            else:
                client.futures_base_url = str(ctx["effective_base_url"]).rstrip("/")
        partial = client.bootstrap_user_data_streams([market])
        streams.update(partial)
    return {
        "status": "ok",
        "user_id": user.id,
        "user_email": user.email,
        "environment": env,
        "streams": streams,
        "note": "REST ingestion tamamlandıktan sonra bu listenKey akışları websocket worker'a bağlanmalıdır.",
        "generated_at": _now().isoformat(),
    }
