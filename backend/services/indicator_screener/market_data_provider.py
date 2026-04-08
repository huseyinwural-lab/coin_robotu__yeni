import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from db import redis_client


ALLOWED_TIMEFRAMES = {"3m", "15m", "1h", "4h", "1d"}
STABLE_ASSETS = {
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "DAI",
    "USDP",
    "EUR",
    "TRY",
}
LEVERAGED_SUFFIXES = {"UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S"}


class MarketDataProviderError(RuntimeError):
    pass


class DataCorruptionError(MarketDataProviderError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ms_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _set_cache_json(key: str, payload: dict, ttl_seconds: int):
    redis_client.set(key, json.dumps(payload))
    if hasattr(redis_client, "expire"):
        redis_client.expire(key, ttl_seconds)


def _get_cache_json(key: str) -> dict | None:
    raw = redis_client.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class BinanceMarketDataProvider:
    def __init__(self):
        self._spot_base_urls = [
            "https://api.binance.com",
            "https://api1.binance.com",
            "https://api2.binance.com",
            "https://api.binance.us",
        ]
        self._futures_base_urls = [
            "https://fapi.binance.com",
            "https://fapi.binance.com",
        ]

    def _resolve_endpoint_candidates(self, market_type: str, endpoint_type: str) -> list[str]:
        market = (market_type or "spot").strip().lower()
        if market not in {"spot", "futures"}:
            raise MarketDataProviderError("market_type sadece 'spot' veya 'futures' olabilir")

        if market == "spot":
            if endpoint_type == "symbols":
                path = "/api/v3/exchangeInfo"
            elif endpoint_type == "ticker24h":
                path = "/api/v3/ticker/24hr"
            elif endpoint_type == "tickerPrice":
                path = "/api/v3/ticker/price"
            else:
                path = "/api/v3/klines"
            return [f"{base}{path}" for base in self._spot_base_urls]

        if endpoint_type == "symbols":
            path = "/fapi/v1/exchangeInfo"
        elif endpoint_type == "ticker24h":
            path = "/fapi/v1/ticker/24hr"
        elif endpoint_type == "tickerPrice":
            path = "/fapi/v1/ticker/price"
        else:
            path = "/fapi/v1/klines"
        return [f"{base}{path}" for base in self._futures_base_urls]

    def _request_with_fallback(
        self,
        url_candidates: list[str],
        params: dict | None = None,
        timeout_seconds: int = 15,
    ) -> tuple[dict | list, str]:
        last_error = None
        for url in url_candidates:
            try:
                response = requests.get(url, params=params or {}, timeout=timeout_seconds)
                if response.status_code == 451:
                    last_error = f"451 restricted on {url}"
                    continue
                response.raise_for_status()
                return response.json(), url
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
        raise MarketDataProviderError(f"Binance endpointlerine erişilemedi: {last_error}")

    @staticmethod
    def _parse_positive_price(value, *, field_name: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise DataCorruptionError(f"{field_name}_invalid") from exc
        if not math.isfinite(parsed) or parsed <= 0:
            raise DataCorruptionError(f"{field_name}_invalid")
        return parsed

    @staticmethod
    def _parse_non_negative_float(value):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed) or parsed < 0:
            return None
        return parsed

    @staticmethod
    def _cache_has_invalid_prices(payload: dict) -> bool:
        rows = payload.get("rows") if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return True
        for row in rows:
            if not isinstance(row, dict):
                return True
            value = row.get("last_price")
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return True
            if not math.isfinite(numeric) or numeric <= 0:
                return True
        return False

    def _resolve_last_price_for_symbol(
        self,
        *,
        market_type: str,
        symbol: str,
        price_map: dict[str, float],
        ticker_map: dict[str, dict],
    ) -> float:
        if symbol in price_map:
            return self._parse_positive_price(price_map[symbol], field_name="ticker_price")

        ticker = ticker_map.get(symbol, {})
        if isinstance(ticker, dict) and ticker.get("lastPrice") not in [None, ""]:
            return self._parse_positive_price(ticker.get("lastPrice"), field_name="ticker_24h_last_price")

        kline_candidates = self._resolve_endpoint_candidates(market_type, "candles")
        raw_klines, _ = self._request_with_fallback(
            kline_candidates,
            params={"symbol": symbol, "interval": "1m", "limit": 1},
            timeout_seconds=6,
        )
        if not isinstance(raw_klines, list) or len(raw_klines) == 0 or len(raw_klines[0]) < 5:
            raise DataCorruptionError(f"kline_price_missing:{symbol}")
        return self._parse_positive_price(raw_klines[0][4], field_name="kline_close_price")

    def get_tradable_symbols(self, *, exchange: str, market_type: str, force_refresh: bool = False) -> dict:
        normalized_exchange = (exchange or "binance").strip().lower()
        if normalized_exchange != "binance":
            raise MarketDataProviderError("İlk sürümde yalnızca Binance destekleniyor")

        normalized_market_type = (market_type or "spot").strip().lower()
        cache_key = f"indicator_screener:symbols:{normalized_exchange}:{normalized_market_type}"
        if not force_refresh:
            cached = _get_cache_json(cache_key)
            if cached:
                if not self._cache_has_invalid_prices(cached):
                    cached["cache_hit"] = True
                    return cached
                try:
                    redis_client.delete(cache_key)
                except Exception:
                    pass

        endpoint_candidates = self._resolve_endpoint_candidates(normalized_market_type, "symbols")
        payload, used_url = self._request_with_fallback(endpoint_candidates, timeout_seconds=15)

        price_payload: list[dict] = []
        price_provider_url = None
        try:
            price_candidates = self._resolve_endpoint_candidates(normalized_market_type, "tickerPrice")
            price_response, price_provider_url = self._request_with_fallback(price_candidates, timeout_seconds=8)
            if isinstance(price_response, list):
                price_payload = price_response
        except MarketDataProviderError:
            price_payload = []

        ticker_candidates = self._resolve_endpoint_candidates(normalized_market_type, "ticker24h")
        ticker_payload: list[dict] = []
        ticker_provider_url = None
        try:
            ticker_response, ticker_provider_url = self._request_with_fallback(ticker_candidates, timeout_seconds=12)
            if isinstance(ticker_response, list):
                ticker_payload = ticker_response
        except MarketDataProviderError:
            ticker_payload = []

        price_map: dict[str, float] = {}
        for row in price_payload:
            symbol = str(row.get("symbol", "")).upper()
            if not symbol:
                continue
            try:
                price_map[symbol] = self._parse_positive_price(row.get("price"), field_name="ticker_price")
            except DataCorruptionError:
                continue

        ticker_map: dict[str, dict] = {}
        for row in ticker_payload:
            symbol = str(row.get("symbol", "")).upper()
            if symbol:
                ticker_map[symbol] = row

        rows: list[dict] = []
        symbols: list[str] = []
        price_resolution_errors: list[dict] = []
        for row in payload.get("symbols", []):
            symbol = str(row.get("symbol", "")).upper()
            if not symbol:
                continue
            quote_asset = str(row.get("quoteAsset", "")).upper()
            base_asset = str(row.get("baseAsset", "")).upper()

            if normalized_market_type == "spot":
                is_tradable = row.get("status") == "TRADING" and bool(row.get("isSpotTradingAllowed", True))
            else:
                is_tradable = row.get("status") == "TRADING" and row.get("contractType") in {"PERPETUAL", "CURRENT_MONTH", "NEXT_MONTH"}

            ticker = ticker_map.get(symbol, {})
            quote_volume_24h = self._parse_non_negative_float((ticker or {}).get("quoteVolume"))
            bid_price = self._parse_non_negative_float((ticker or {}).get("bidPrice"))
            ask_price = self._parse_non_negative_float((ticker or {}).get("askPrice"))

            try:
                last_price = self._resolve_last_price_for_symbol(
                    market_type=normalized_market_type,
                    symbol=symbol,
                    price_map=price_map,
                    ticker_map=ticker_map,
                )
            except (DataCorruptionError, MarketDataProviderError) as exc:
                price_resolution_errors.append({"symbol": symbol, "error": str(exc)[:140]})
                continue

            spread_pct_24h = (
                abs(ask_price - bid_price) / last_price * 100
                if bid_price and ask_price and bid_price > 0 and ask_price > 0
                else None
            )

            leveraged_token = any(base_asset.endswith(suffix) for suffix in LEVERAGED_SUFFIXES)
            stablecoin_pair = base_asset in STABLE_ASSETS and quote_asset in STABLE_ASSETS

            rows.append(
                {
                    "symbol": symbol,
                    "quote_asset": quote_asset,
                    "base_asset": base_asset,
                    "status": str(row.get("status") or "UNKNOWN"),
                    "is_tradable": bool(is_tradable),
                    "margin_eligible": bool(row.get("isMarginTradingAllowed", False)),
                    "futures_eligible": normalized_market_type == "futures",
                    "volume_24h": quote_volume_24h,
                    "spread_pct_24h": spread_pct_24h,
                    "last_price": last_price,
                    "leveraged_token": leveraged_token,
                    "stablecoin_pair": stablecoin_pair,
                }
            )
            symbols.append(symbol)

        rows.sort(key=lambda item: item["symbol"])
        symbols = sorted(set(symbols))
        if len(rows) == 0:
            raise DataCorruptionError("no_valid_market_prices_from_binance")

        result = {
            "exchange": normalized_exchange,
            "market_type": normalized_market_type,
            "symbols": symbols,
            "rows": rows,
            "symbol_count": len(symbols),
            "generated_at": _utc_now_iso(),
            "cache_hit": False,
            "source": f"{normalized_exchange}_{normalized_market_type}_exchange_info",
            "provider_url": used_url,
            "ticker_provider_url": ticker_provider_url,
            "price_provider_url": price_provider_url,
            "price_resolution_error_count": len(price_resolution_errors),
            "price_resolution_errors": price_resolution_errors[:120],
        }
        if not self._cache_has_invalid_prices(result):
            _set_cache_json(cache_key, result, ttl_seconds=300)
        return result

    def fetch_candles(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        candle_limit: int = 140,
        force_refresh: bool = False,
    ) -> dict:
        normalized_exchange = (exchange or "binance").strip().lower()
        if normalized_exchange != "binance":
            raise MarketDataProviderError("İlk sürümde yalnızca Binance destekleniyor")

        normalized_market_type = (market_type or "spot").strip().lower()
        normalized_timeframe = (timeframe or "15m").strip().lower()
        if normalized_timeframe not in ALLOWED_TIMEFRAMES:
            raise MarketDataProviderError(f"Desteklenmeyen timeframe: {timeframe}")

        normalized_symbol = (symbol or "").strip().upper()
        if not normalized_symbol:
            raise MarketDataProviderError("Sembol boş olamaz")

        bounded_limit = max(80, min(int(candle_limit), 500))
        cache_key = (
            f"indicator_screener:candles:{normalized_exchange}:{normalized_market_type}:"
            f"{normalized_symbol}:{normalized_timeframe}:{bounded_limit}"
        )

        if not force_refresh:
            cached = _get_cache_json(cache_key)
            if cached:
                cached["cache_hit"] = True
                cached["fresh_fetch"] = False
                cached["evaluated_at"] = _utc_now_iso()
                return cached

        endpoint_candidates = self._resolve_endpoint_candidates(normalized_market_type, "candles")
        request_limit = min(500, bounded_limit + 2)
        raw_candles, used_url = self._request_with_fallback(
            endpoint_candidates,
            params={
                "symbol": normalized_symbol,
                "interval": normalized_timeframe,
                "limit": request_limit,
            },
            timeout_seconds=8,
        )

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        normalized_candles: list[dict] = []
        for candle in raw_candles:
            if len(candle) < 7:
                continue
            close_time = int(candle[6])
            if close_time > now_ms:
                continue
            normalized_candles.append(
                {
                    "open_time": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                    "close_time": close_time,
                }
            )

        if len(normalized_candles) > bounded_limit:
            normalized_candles = normalized_candles[-bounded_limit:]

        if len(normalized_candles) < 60:
            raise MarketDataProviderError(f"Yetersiz kapalı candle verisi ({normalized_symbol})")

        last_candle_time = normalized_candles[-1]["close_time"] if normalized_candles else None
        result = {
            "symbol": normalized_symbol,
            "exchange": normalized_exchange,
            "market_type": normalized_market_type,
            "timeframe": normalized_timeframe,
            "candles": normalized_candles,
            "candle_count": len(normalized_candles),
            "last_candle_time": _ms_to_iso(last_candle_time),
            "data_source": f"{normalized_exchange}_{normalized_market_type}_rest_api",
            "provider_url": used_url,
            "cache_hit": False,
            "fresh_fetch": True,
            "evaluated_at": _utc_now_iso(),
        }
        _set_cache_json(cache_key, result, ttl_seconds=45)
        return result

    def get_tradable_symbols_parallel(
        self,
        *,
        exchange: str,
        include_spot: bool = True,
        include_futures: bool = True,
        force_refresh: bool = False,
    ) -> dict:
        normalized_exchange = (exchange or "binance").strip().lower()
        if normalized_exchange != "binance":
            raise MarketDataProviderError("İlk sürümde yalnızca Binance destekleniyor")

        market_types: list[str] = []
        if include_spot:
            market_types.append("spot")
        if include_futures:
            market_types.append("futures")
        if not market_types:
            raise MarketDataProviderError("En az bir market türü seçilmelidir")

        markets: dict[str, dict] = {}
        errors: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(2, len(market_types))) as executor:
            future_map = {
                executor.submit(
                    self.get_tradable_symbols,
                    exchange=normalized_exchange,
                    market_type=market_type,
                    force_refresh=force_refresh,
                ): market_type
                for market_type in market_types
            }
            for future in as_completed(future_map):
                market_type = future_map[future]
                try:
                    payload = future.result()
                    markets[market_type] = payload
                except Exception as exc:
                    errors.append({"market_type": market_type, "error": str(exc)[:300]})

        combined_rows: list[dict] = []
        for market_type, payload in markets.items():
            for row in payload.get("rows") or []:
                combined_rows.append({**row, "market_type": market_type})

        combined_rows.sort(key=lambda item: float(item.get("volume_24h") or 0), reverse=True)

        return {
            "exchange": normalized_exchange,
            "include_spot": bool(include_spot),
            "include_futures": bool(include_futures),
            "generated_at": _utc_now_iso(),
            "markets": markets,
            "rows": combined_rows,
            "symbol_count": len(combined_rows),
            "error_count": len(errors),
            "errors": errors,
        }

    def fetch_indicator_and_execution_candles(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        indicator_timeframe: str = "1h",
        execution_timeframe: str = "15m",
        indicator_limit: int = 180,
        execution_limit: int = 140,
        force_refresh: bool = False,
    ) -> dict:
        with ThreadPoolExecutor(max_workers=2) as executor:
            indicator_future = executor.submit(
                self.fetch_candles,
                exchange=exchange,
                market_type=market_type,
                symbol=symbol,
                timeframe=indicator_timeframe,
                candle_limit=indicator_limit,
                force_refresh=force_refresh,
            )
            execution_future = executor.submit(
                self.fetch_candles,
                exchange=exchange,
                market_type=market_type,
                symbol=symbol,
                timeframe=execution_timeframe,
                candle_limit=execution_limit,
                force_refresh=force_refresh,
            )
            indicator_payload = indicator_future.result()
            execution_payload = execution_future.result()

        return {
            "exchange": exchange,
            "market_type": market_type,
            "symbol": symbol,
            "indicator_timeframe": indicator_timeframe,
            "execution_timeframe": execution_timeframe,
            "indicator": indicator_payload,
            "execution": execution_payload,
            "generated_at": _utc_now_iso(),
        }
