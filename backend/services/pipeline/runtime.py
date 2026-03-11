import asyncio
import logging
from datetime import datetime, timezone

from db import SessionLocal, redis_client
from models import BotProfile, FailedEvent, PaperPosition, SignalEvent, StrategyTemplate, User
from services.audit_service import create_audit_log
from services.execution_policy_service import get_policy_for_strategy
from services.failed_event_service import create_failed_event, mark_failed_event_resolved, mark_failed_event_retry
from services.pipeline.cache_store import get_counter, get_json, incr_counter, set_json, utc_now_iso
from services.pipeline.execution_engine import open_paper_position, refresh_open_positions
from services.pipeline.market_data_engine import MarketDataEngine
from services.pipeline.risk_engine import evaluate_risk
from services.pipeline.strategy_engine import evaluate_strategy
from services.pipeline.universe_engine import build_effective_universe

logger = logging.getLogger(__name__)


class PipelineRuntime:
    def __init__(self, cache):
        self.cache = cache
        self.candle_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self.market_data_engine = MarketDataEngine(cache, self.candle_queue)
        self._orchestrator_task: asyncio.Task | None = None
        self._position_task: asyncio.Task | None = None
        self._metrics_window_task: asyncio.Task | None = None
        self._failed_event_task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        await self.market_data_engine.start()
        self._orchestrator_task = asyncio.create_task(self._orchestrate(), name="signal-orchestrator")
        self._position_task = asyncio.create_task(self._refresh_positions_loop(), name="position-engine")
        self._metrics_window_task = asyncio.create_task(self._rolling_metrics_reset(), name="metrics-window")
        self._failed_event_task = asyncio.create_task(self._failed_event_recovery_loop(), name="failed-event-recovery")
        logger.info("Phase-3 runtime started")

    async def stop(self):
        self._running = False
        await self.market_data_engine.stop()
        for task in [self._orchestrator_task, self._position_task, self._metrics_window_task, self._failed_event_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _orchestrate(self):
        while self._running:
            event = await self.candle_queue.get()
            started = asyncio.get_event_loop().time()
            db = SessionLocal()
            try:
                universe = build_effective_universe(db, self.cache)
                bots = (
                    db.query(BotProfile)
                    .filter(BotProfile.is_enabled.is_(True), BotProfile.is_running.is_(True), BotProfile.timeframe == event.timeframe)
                    .all()
                )
                for bot in bots:
                    try:
                        symbol_set = {symbol.upper() for symbol in bot.symbols}
                        if event.symbol not in symbol_set:
                            continue
                        if bot.market_type == "spot" and event.symbol not in universe["spot_symbols"]:
                            continue
                        if bot.market_type == "futures" and event.symbol not in universe["futures_symbols"]:
                            continue

                        user = db.query(User).filter(User.id == bot.user_id).first()
                        if user is None:
                            continue

                        strategy_template = (
                            db.query(StrategyTemplate)
                            .filter(StrategyTemplate.strategy_type == bot.strategy_type, StrategyTemplate.is_active.is_(True))
                            .order_by(StrategyTemplate.updated_at.desc())
                            .first()
                        )
                        params = strategy_template.parameters if strategy_template else {}
                        primary_candles = get_json(self.cache, f"market:candles:{event.symbol}:15m") or []
                        secondary_candles = get_json(self.cache, f"market:candles:{event.symbol}:1h") or []
                        spread_payload = get_json(self.cache, f"market:spread:{event.symbol}") or {}
                        spread_bps = float(spread_payload.get("spread_bps", 9999))

                        signal = evaluate_strategy(
                            strategy_type=bot.strategy_type,
                            symbol=event.symbol,
                            primary_candles=primary_candles,
                            secondary_candles=secondary_candles,
                            spread_bps=spread_bps,
                            params=params,
                        )

                        if signal.signal == "none":
                            continue

                        signal_event = SignalEvent(
                            bot_profile_id=bot.id,
                            user_id=user.id,
                            symbol=signal.symbol,
                            market_type=bot.market_type,
                            timeframe=bot.timeframe,
                            strategy_id=signal.strategy_id,
                            signal=signal.signal,
                            direction=signal.direction,
                            confidence=signal.confidence,
                            reason_codes=signal.reason_codes,
                        )
                        db.add(signal_event)
                        db.flush()

                        create_audit_log(
                            db,
                            action="signal_generated",
                            entity_type="signal_event",
                            entity_id=signal_event.id,
                            actor_user_id=user.id,
                            actor_role=user.role.value,
                            details={"symbol": signal.symbol, "direction": signal.direction, "strategy": signal.strategy_id},
                        )
                        incr_counter(self.cache, "metrics:signals:5m", 1)

                        ticker_payload = get_json(self.cache, f"market:ticker:{event.symbol}") or {}
                        market_price = float(ticker_payload.get("last_price", signal.proposed_entry))
                        atr_pct = (
                            abs(signal.proposed_entry - signal.proposed_stop) / signal.proposed_entry
                            if signal.proposed_entry
                            else 1
                        )
                        risk_decision = evaluate_risk(
                            db,
                            current_user=user,
                            signal=signal,
                            market_price=market_price,
                            spread_bps=spread_bps,
                            atr_pct=atr_pct,
                        )

                        if not risk_decision.approved:
                            create_audit_log(
                                db,
                                action="risk_rejection",
                                entity_type="signal_event",
                                entity_id=signal_event.id,
                                actor_user_id=user.id,
                                actor_role=user.role.value,
                                severity="warning",
                                details={"tags": risk_decision.risk_tags},
                            )
                            continue

                        policy = get_policy_for_strategy(db, bot.strategy_type)
                        execution_policy_payload = {
                            "style": policy.execution_style,
                            "order_preference": policy.order_preference,
                            "timeout_seconds": policy.timeout_seconds,
                            "fallback_behavior": policy.fallback_behavior,
                            "partial_fill_tolerance_pct": policy.partial_fill_tolerance_pct,
                            "execution_urgency": policy.execution_urgency,
                            "retry_limit": policy.retry_limit,
                        }

                        position = open_paper_position(
                            db,
                            user=user,
                            bot=bot,
                            symbol=signal.symbol,
                            direction=signal.direction,
                            market_price=market_price,
                            quantity=risk_decision.size,
                            leverage=risk_decision.leverage,
                            stop_loss=risk_decision.stop,
                            take_profit=risk_decision.take_profit,
                            execution_policy=execution_policy_payload,
                            response_payload={
                                "state": "filled",
                                "mode": "paper",
                                "strategy_id": signal.strategy_id,
                                "risk_tags": risk_decision.risk_tags,
                            },
                        )
                        create_audit_log(
                            db,
                            action="trade_open",
                            entity_type="paper_position",
                            entity_id=position.id,
                            actor_user_id=user.id,
                            actor_role=user.role.value,
                            details={
                                "symbol": position.symbol,
                                "side": position.side,
                                "quantity": position.quantity,
                                "execution_style": policy.execution_style,
                            },
                        )
                        incr_counter(self.cache, "metrics:paper_trades:5m", 1)
                    except Exception as bot_exc:
                        logger.exception("Pipeline bot processing failure (%s): %s", bot.id, bot_exc)
                        create_failed_event(
                            db,
                            event_type="pipeline_chain_failure",
                            entity_type="bot_profile",
                            entity_id=bot.id,
                            payload={"symbol": event.symbol, "timeframe": event.timeframe},
                            error_message=str(bot_exc),
                        )

                latency_ms = round((asyncio.get_event_loop().time() - started) * 1000, 2)
                set_json(
                    self.cache,
                    "pipeline:orchestrator",
                    {
                        "last_processed_at": utc_now_iso(),
                        "last_symbol": event.symbol,
                        "latency_ms": latency_ms,
                        "queue_depth": self.candle_queue.qsize(),
                    },
                )
            except Exception as exc:
                logger.exception("Orchestrator error: %s", exc)
                create_failed_event(
                    db,
                    event_type="orchestrator_loop_failure",
                    entity_type="candle_event",
                    entity_id=f"{event.symbol}:{event.timeframe}",
                    payload={"symbol": event.symbol, "timeframe": event.timeframe},
                    error_message=str(exc),
                )
            finally:
                db.close()

    async def _refresh_positions_loop(self):
        while self._running:
            await asyncio.sleep(5)
            db = SessionLocal()
            latest_prices = {}
            try:
                latest_prices = self.market_data_engine.latest_prices.copy()
                closed_positions = refresh_open_positions(db, latest_prices)
                for position in closed_positions:
                    user = db.query(User).filter(User.id == position.user_id).first()
                    if user is None:
                        continue
                    create_audit_log(
                        db,
                        action="trade_close",
                        entity_type="paper_position",
                        entity_id=position.id,
                        actor_user_id=user.id,
                        actor_role=user.role.value,
                        details={"reason": position.status, "realized_pnl": position.realized_pnl},
                    )
            except Exception as exc:
                logger.exception("Position refresh error: %s", exc)
                create_failed_event(
                    db,
                    event_type="position_refresh_failure",
                    entity_type="position_engine",
                    entity_id="refresh_loop",
                    payload={"latest_prices_count": len(latest_prices)},
                    error_message=str(exc),
                )
            finally:
                db.close()

    async def _rolling_metrics_reset(self):
        while self._running:
            await asyncio.sleep(300)
            self.cache.set("metrics:signals:5m", "0")
            self.cache.set("metrics:paper_trades:5m", "0")

    async def _failed_event_recovery_loop(self):
        while self._running:
            await asyncio.sleep(10)
            db = SessionLocal()
            try:
                queue = (
                    db.query(FailedEvent)
                    .filter(FailedEvent.status.in_(["pending", "retrying"]))
                    .order_by(FailedEvent.created_at.asc())
                    .limit(20)
                    .all()
                )
                for failed_event in queue:
                    try:
                        # Phase-3 first version: deterministic retry/resolve flow
                        if failed_event.retry_count >= 1:
                            mark_failed_event_resolved(db, failed_event)
                        else:
                            mark_failed_event_retry(db, failed_event)
                    except Exception:
                        mark_failed_event_retry(db, failed_event)
            except Exception as exc:
                logger.exception("Failed event recovery loop error: %s", exc)
            finally:
                db.close()

    def monitoring_snapshot(self, db):
        ws = get_json(self.cache, "pipeline:websocket") or {}
        orchestrator = get_json(self.cache, "pipeline:orchestrator") or {}
        return {
            "websocket_status": ws.get("status", self.market_data_engine.websocket_status),
            "heartbeat": ws.get("heartbeat", self.market_data_engine.last_heartbeat),
            "signal_rate_last_5m": get_counter(self.cache, "metrics:signals:5m"),
            "paper_trades_last_5m": get_counter(self.cache, "metrics:paper_trades:5m"),
            "open_positions": db.query(PaperPosition).filter(PaperPosition.status == "open").count(),
            "latency_ms": orchestrator.get("latency_ms", self.market_data_engine.latency_ms),
            "queue_depth": self.candle_queue.qsize(),
            "active_bots_running": db.query(BotProfile).filter(BotProfile.is_running.is_(True)).count(),
        }


pipeline_runtime = PipelineRuntime(redis_client)