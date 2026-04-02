import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone

import websockets

from services.indicator_screener.market_data_provider import BinanceMarketDataProvider, MarketDataProviderError
from services.pipeline.cache_store import append_candle, incr_counter, set_json, utc_now_iso
from services.pipeline.events import CandleClosedEvent
from services.pipeline.spot_strategy_service import (
    MIN_15M_CANDLES,
    bootstrap_market_data_store,
    get_spot_tradable_universe,
)
from services.quote_asset_policy import ALLOWED_QUOTE_ASSETS, filter_allowed_quote_symbols

logger = logging.getLogger(__name__)


class MarketDataEngine:
    def __init__(self, cache, candle_queue: asyncio.Queue):
        self.cache = cache
        self.candle_queue = candle_queue
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.websocket_status = "disconnected"
        self.last_heartbeat = utc_now_iso()
        self.latency_ms = 0.0
        self.latest_prices: dict[str, float] = {}
        self._last_bootstrap_day: str | None = None

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="market-data-engine")

    async def stop(self):
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        while not self._stop_event.is_set():
            symbols = self._load_symbols()
            today = datetime.now(timezone.utc).date().isoformat()
            if self._last_bootstrap_day != today:
                await asyncio.to_thread(bootstrap_market_data_store, self.cache, symbols, MIN_15M_CANDLES)
                self._last_bootstrap_day = today

            url = self._build_stream_url(symbols)
            try:
                self.websocket_status = "connecting"
                async with websockets.connect(url, ping_interval=20, close_timeout=5) as socket:
                    self.websocket_status = "connected"
                    set_json(self.cache, "pipeline:websocket", {"status": self.websocket_status, "url": url})
                    while not self._stop_event.is_set():
                        started = asyncio.get_event_loop().time()
                        raw = await asyncio.wait_for(socket.recv(), timeout=30)
                        self.latency_ms = round((asyncio.get_event_loop().time() - started) * 1000, 2)
                        self.last_heartbeat = utc_now_iso()
                        set_json(
                            self.cache,
                            "pipeline:websocket",
                            {
                                "status": self.websocket_status,
                                "heartbeat": self.last_heartbeat,
                                "latency_ms": self.latency_ms,
                            },
                        )
                        await self._process_message(raw)
            except Exception as exc:
                logger.warning("Market data websocket reconnect triggered: %s", exc)
                self.websocket_status = "reconnecting"
                incr_counter(self.cache, "metrics:websocket_reconnects:5m", 1)
                await self._emit_synthetic_data(symbols)
                await asyncio.sleep(5)

    def _load_symbols(self) -> list[str]:
        dynamic_universe = get_spot_tradable_universe(self.cache)
        dynamic_symbols = [symbol.upper() for symbol in dynamic_universe.get("symbols", []) if symbol]
        if dynamic_symbols:
            return filter_allowed_quote_symbols(dynamic_symbols)[:55]

        provider = BinanceMarketDataProvider()
        try:
            payload = provider.get_tradable_symbols(exchange="binance", market_type="spot")
            provider_symbols = [
                str(row.get("symbol") or "").upper().strip()
                for row in (payload.get("rows") or [])
                if bool(row.get("is_tradable", False)) and str(row.get("quote_asset") or "").upper() in ALLOWED_QUOTE_ASSETS
            ]
            provider_symbols = filter_allowed_quote_symbols(provider_symbols)
            if provider_symbols:
                return provider_symbols[:55]
        except MarketDataProviderError:
            pass

        effective_universe_raw = self.cache.get("universe:effective")
        if not effective_universe_raw:
            return []
        try:
            payload = json.loads(effective_universe_raw)
        except json.JSONDecodeError:
            return []

        merged = payload.get("spot_symbols", []) + payload.get("futures_symbols", [])
        symbols = filter_allowed_quote_symbols([symbol.upper() for symbol in merged if symbol])
        return symbols[:55]

    def _build_stream_url(self, symbols: list[str]) -> str:
        streams: list[str] = []
        for symbol in symbols:
            lower = symbol.lower()
            streams.extend([f"{lower}@ticker", f"{lower}@kline_15m", f"{lower}@kline_1h", f"{lower}@depth5@100ms"])

        stream_payload = "/".join(streams)
        base_url = str(os.getenv("BINANCE_WS_STREAM_BASE_URL") or "wss://stream.binance.com:9443/stream").strip()
        if not base_url:
            base_url = "wss://stream.binance.com:9443/stream"

        if "{streams}" in base_url:
            return base_url.replace("{streams}", stream_payload)

        normalized = base_url.rstrip("/")
        if "streams=" in normalized:
            return f"{normalized}{stream_payload}"
        if normalized.endswith("/stream"):
            return f"{normalized}?streams={stream_payload}"
        return f"{normalized}/stream?streams={stream_payload}"

    async def _process_message(self, raw_message: str):
        payload = json.loads(raw_message)
        data = payload.get("data", {})
        event_type = data.get("e")

        if event_type == "24hrTicker":
            symbol = data["s"].upper()
            last_price = float(data.get("c", 0))
            quote_volume = float(data.get("q", 0))
            self.latest_prices[symbol] = last_price
            set_json(
                self.cache,
                f"market:ticker:{symbol}",
                {"symbol": symbol, "last_price": last_price, "quote_volume": quote_volume, "updated_at": utc_now_iso()},
            )
            return

        if event_type == "depthUpdate":
            symbol = data["s"].upper()
            bids = data.get("b", [])
            asks = data.get("a", [])
            if bids and asks:
                top_bid = float(bids[0][0])
                top_ask = float(asks[0][0])
                spread_bps = ((top_ask - top_bid) / top_ask * 10000) if top_ask else 0
                set_json(
                    self.cache,
                    f"market:spread:{symbol}",
                    {
                        "symbol": symbol,
                        "top_bid": top_bid,
                        "top_ask": top_ask,
                        "spread_bps": round(spread_bps, 4),
                        "updated_at": utc_now_iso(),
                    },
                )
            return

        if event_type == "kline":
            kline = data.get("k", {})
            symbol = data["s"].upper()
            timeframe = kline.get("i")
            candle = {
                "open": float(kline.get("o", 0)),
                "high": float(kline.get("h", 0)),
                "low": float(kline.get("l", 0)),
                "close": float(kline.get("c", 0)),
                "volume": float(kline.get("v", 0)),
                "quote_volume": float(kline.get("q", 0)),
                "start": kline.get("t"),
                "end": kline.get("T"),
                "is_closed": bool(kline.get("x")),
            }
            append_candle(self.cache, f"market:candles:{symbol}:{timeframe}", candle)
            if timeframe == "15m":
                append_candle(self.cache, f"market_data_store:{symbol}:15m", candle)
            if candle["is_closed"]:
                incr_counter(self.cache, "metrics:candle_closed_count", 1)
                await self.candle_queue.put(
                    CandleClosedEvent(symbol=symbol, timeframe=timeframe, timestamp=datetime.now(timezone.utc))
                )

    async def _emit_synthetic_data(self, symbols: list[str]):
        now = datetime.now(timezone.utc)
        for symbol in symbols:
            base_price = self.latest_prices.get(symbol, random.uniform(95, 105))
            next_price = round(base_price + random.uniform(-0.9, 0.9), 4)
            self.latest_prices[symbol] = next_price

            set_json(
                self.cache,
                f"market:ticker:{symbol}",
                {
                    "symbol": symbol,
                    "last_price": next_price,
                    "quote_volume": random.uniform(1_500_000, 12_000_000),
                    "updated_at": utc_now_iso(),
                },
            )
            set_json(
                self.cache,
                f"market:spread:{symbol}",
                {
                    "symbol": symbol,
                    "top_bid": next_price - 0.1,
                    "top_ask": next_price + 0.1,
                    "spread_bps": round((0.2 / next_price) * 10000, 4),
                    "updated_at": utc_now_iso(),
                },
            )

            synthetic_candle = {
                "open": next_price - random.uniform(0.3, 0.8),
                "high": next_price + random.uniform(0.2, 0.9),
                "low": next_price - random.uniform(0.2, 0.9),
                "close": next_price,
                "volume": random.uniform(1000, 12000),
                "quote_volume": random.uniform(1_500_000, 12_000_000),
                "start": int(now.timestamp() * 1000),
                "end": int(now.timestamp() * 1000),
                "is_closed": True,
            }
            append_candle(self.cache, f"market:candles:{symbol}:15m", synthetic_candle)
            append_candle(self.cache, f"market:candles:{symbol}:1h", synthetic_candle)
            await self.candle_queue.put(CandleClosedEvent(symbol=symbol, timeframe="15m", timestamp=now))
