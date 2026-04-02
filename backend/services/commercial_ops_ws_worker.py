import asyncio
import json
import threading
import time
from datetime import datetime, timezone

import websockets
from sqlalchemy.orm import Session

from db import SessionLocal
from models import CommercialTrade
from services.commercial_ops_p0_service import (
    BinanceCommercialClient,
    _build_futures_trade_row,
    _build_spot_trade_row,
    _normalize_environment,
    _normalize_market_types,
    _resolve_user_and_market_credentials,
    _safe_float,
    _trade_exists,
)
from services.revenue_engine_service import upsert_revenue_for_trades


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommercialOpsWsWorker:
    def __init__(
        self,
        *,
        user_id: str,
        user_email: str,
        environment: str,
        market_types: list[str],
        api_key: str,
        api_secret: str,
        connection_map: dict,
    ):
        self.user_id = user_id
        self.user_email = user_email
        self.environment = environment
        self.market_types = _normalize_market_types(market_types)
        self.client = BinanceCommercialClient(api_key=api_key, api_secret=api_secret, environment=environment)
        self.connection_map = connection_map

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.started_at = _now_iso()
        self.last_event_at: str | None = None
        self.last_error: str | None = None
        self.reconnect_count = 0
        self.inserted_count = 0
        self.duplicate_count = 0
        self.events_processed = 0
        self.market_streams: dict[str, dict] = {}

    @property
    def worker_key(self) -> str:
        return f"{self.user_id}:{self.environment}:{','.join(sorted(self.market_types))}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"commercial-ws-{self.user_id[:6]}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)

    def status(self) -> dict:
        return {
            "worker_key": self.worker_key,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "environment": self.environment,
            "market_types": self.market_types,
            "is_running": self.is_running,
            "started_at": self.started_at,
            "last_event_at": self.last_event_at,
            "last_error": self.last_error,
            "reconnect_count": self.reconnect_count,
            "events_processed": self.events_processed,
            "inserted_count": self.inserted_count,
            "duplicate_count": self.duplicate_count,
            "market_streams": self.market_streams,
        }

    def _run(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        try:
            self.market_streams = self.client.bootstrap_user_data_streams(self.market_types)
        except Exception as exc:
            self.last_error = f"bootstrap_failed:{exc}"
            return

        tasks = [asyncio.create_task(self._consume_market(market)) for market in self.market_types]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _consume_market(self, market: str) -> None:
        stream = self.market_streams.get(market) or {}
        ws_url = str(stream.get("ws_url") or "").strip()
        if not ws_url:
            self.last_error = f"missing_ws_url:{market}"
            return

        backoff = 1
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20, close_timeout=5) as socket:
                    backoff = 1
                    while not self._stop_event.is_set():
                        raw = await asyncio.wait_for(socket.recv(), timeout=35)
                        payload = json.loads(raw)
                        self._handle_event(market, payload)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                self.reconnect_count += 1
                self.last_error = f"{market}_stream_error:{exc}"
                await asyncio.sleep(min(backoff, 20))
                backoff = min(backoff * 2, 20)

    def _handle_event(self, market: str, payload: dict) -> None:
        self.last_event_at = _now_iso()
        self.events_processed += 1

        if market == "futures":
            self._handle_futures_event(payload)
        elif market == "spot":
            self._handle_spot_event(payload)

    def _handle_futures_event(self, payload: dict) -> None:
        if str(payload.get("e") or "") != "ORDER_TRADE_UPDATE":
            return
        order = payload.get("o") or {}
        trade_id = order.get("t")
        qty = _safe_float(order.get("l"), 0.0)
        if trade_id in (None, "") or qty <= 0:
            return

        symbol = str(order.get("s") or "").upper()
        raw = {
            "id": trade_id,
            "symbol": symbol,
            "qty": order.get("l"),
            "price": order.get("L") or order.get("ap") or 0,
            "quoteQty": _safe_float(order.get("l"), 0.0) * _safe_float(order.get("L") or order.get("ap"), 0.0),
            "commission": order.get("n") or 0,
            "commissionAsset": order.get("N") or "USDT",
            "realizedPnl": order.get("rp") or 0,
            "side": order.get("S") or "BUY",
            "positionSide": order.get("ps") or "BOTH",
            "buyer": str(order.get("S") or "BUY").upper() == "BUY",
            "maker": bool(order.get("m")),
            "time": order.get("T") or payload.get("T") or int(time.time() * 1000),
            "orderId": order.get("i"),
            "clientOrderId": order.get("c"),
        }
        connection_id = self.connection_map.get("futures", self.connection_map.get("spot")).id
        row = _build_futures_trade_row(
            user_id=self.user_id,
            connection_id=connection_id,
            environment=self.environment,
            symbol=symbol,
            payload=raw,
            client=self.client,
            source="websocket",
        )
        self._persist_trade(row)

    def _handle_spot_event(self, payload: dict) -> None:
        if str(payload.get("e") or "") != "executionReport":
            return
        if str(payload.get("x") or "") != "TRADE":
            return
        trade_id = payload.get("t")
        qty = _safe_float(payload.get("l"), 0.0)
        if trade_id in (None, "") or qty <= 0:
            return

        symbol = str(payload.get("s") or "").upper()
        raw = {
            "id": trade_id,
            "time": payload.get("T") or int(time.time() * 1000),
            "orderId": payload.get("i"),
            "clientOrderId": payload.get("c"),
            "price": payload.get("L") or payload.get("p") or 0,
            "qty": payload.get("l") or 0,
            "quoteQty": payload.get("Y") or (_safe_float(payload.get("l"), 0.0) * _safe_float(payload.get("L"), 0.0)),
            "commission": payload.get("n") or 0,
            "commissionAsset": payload.get("N") or "USDT",
            "isBuyer": str(payload.get("S") or "BUY").upper() == "BUY",
            "isMaker": bool(payload.get("m")),
        }
        connection_id = self.connection_map.get("spot", self.connection_map.get("futures")).id
        row = _build_spot_trade_row(
            user_id=self.user_id,
            connection_id=connection_id,
            environment=self.environment,
            symbol=symbol,
            payload=raw,
            client=self.client,
            source="websocket",
        )
        self._persist_trade(row)

    def _persist_trade(self, row: CommercialTrade) -> None:
        db: Session = SessionLocal()
        try:
            if _trade_exists(db, row):
                with self._lock:
                    self.duplicate_count += 1
                return
            db.add(row)
            db.flush()
            upsert_revenue_for_trades(db, trades=[row])
            db.commit()
            with self._lock:
                self.inserted_count += 1
        except Exception as exc:
            db.rollback()
            self.last_error = f"persist_error:{exc}"
        finally:
            db.close()


_WS_WORKERS: dict[str, CommercialOpsWsWorker] = {}


def start_ws_worker(
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

    anchor_market = markets[0]
    if len(markets) > 1:
        spot_ctx = market_credentials.get("spot")
        futures_ctx = market_credentials.get("futures")
        if spot_ctx and futures_ctx and (
            spot_ctx["api_key"] != futures_ctx["api_key"]
            or spot_ctx["api_secret"] != futures_ctx["api_secret"]
        ):
            raise ValueError("ws_requires_single_market_or_shared_credentials")

    anchor_ctx = market_credentials[anchor_market]
    connection_map = {market: market_credentials[market]["connection"] for market in markets}
    worker_key = f"{user.id}:{env}:{','.join(sorted(markets))}"
    current = _WS_WORKERS.get(worker_key)
    if current and current.is_running:
        return {"status": "already_running", "worker": current.status()}

    worker = CommercialOpsWsWorker(
        user_id=user.id,
        user_email=user.email,
        environment=env,
        market_types=markets,
        api_key=anchor_ctx["api_key"],
        api_secret=anchor_ctx["api_secret"],
        connection_map=connection_map,
    )
    _WS_WORKERS[worker_key] = worker
    worker.start()
    return {"status": "started", "worker": worker.status()}


def stop_ws_worker(*, target_user_id: str, environment: str, market_types: list[str] | None) -> dict:
    env = _normalize_environment(environment)
    if market_types:
        markets = _normalize_market_types(market_types)
        worker_key = f"{target_user_id}:{env}:{','.join(sorted(markets))}"
        worker = _WS_WORKERS.get(worker_key)
        if worker is None:
            return {"status": "not_found", "worker_key": worker_key}
        worker.stop()
        return {"status": "stopped", "worker": worker.status(), "stopped_count": 1}

    matching = [key for key, worker in _WS_WORKERS.items() if worker.user_id == target_user_id and worker.environment == env]
    if not matching:
        return {"status": "not_found", "worker_key": f"{target_user_id}:{env}:*"}

    latest = None
    for key in matching:
        worker = _WS_WORKERS.get(key)
        if worker is None:
            continue
        worker.stop()
        latest = worker
    return {
        "status": "stopped",
        "worker": latest.status() if latest else None,
        "stopped_count": len(matching),
    }


def ws_worker_status(*, target_user_id: str | None, environment: str | None) -> dict:
    env = _normalize_environment(environment or "live") if environment else None
    payload = []
    for key, worker in _WS_WORKERS.items():
        if target_user_id and worker.user_id != target_user_id:
            continue
        if env and worker.environment != env:
            continue
        payload.append(worker.status())
    return {"status": "ok", "workers": payload, "count": len(payload)}
