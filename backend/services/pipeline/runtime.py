import asyncio
import logging
from datetime import datetime, timezone

from db import SessionLocal, redis_client
from models import BotProfile, ExecutionStateTransition, FailedEvent, PaperPosition, SignalEvent, StateRebuildLog, StrategyTemplate, User
from services.audit_service import create_audit_log
from services.execution_policy_service import get_policy_for_strategy
from services.failed_event_service import create_failed_event, mark_failed_event_resolved, mark_failed_event_retry
from services.pipeline.cache_store import get_counter, get_json, incr_counter, set_json, utc_now_iso
from services.pipeline.execution_engine import open_paper_position, refresh_open_positions
from services.pipeline.market_data_engine import MarketDataEngine
from services.pipeline.risk_engine import evaluate_risk
from services.pipeline.strategy_engine import evaluate_strategy
from services.pipeline.universe_engine import build_effective_universe
from services.live_mode_service import enforce_release_gate

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
        self._release_gate_task: asyncio.Task | None = None
        self._last_release_gate_status: str | None = None
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
        self._release_gate_task = asyncio.create_task(self._release_gate_guard_loop(), name="release-gate-guard")
        logger.info("Phase-3 runtime started")

    async def stop(self):
        self._running = False
        await self.market_data_engine.stop()
        for task in [
            self._orchestrator_task,
            self._position_task,
            self._metrics_window_task,
            self._failed_event_task,
            self._release_gate_task,
        ]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _release_gate_guard_loop(self):
        while self._running:
            await asyncio.sleep(30)
            db = SessionLocal()
            try:
                gate = enforce_release_gate(db)
                if gate["status"] != self._last_release_gate_status:
                    self._last_release_gate_status = gate["status"]
                    create_audit_log(
                        db,
                        action="release_gate_status_changed",
                        entity_type="release_gate",
                        entity_id="phase4",
                        actor_user_id=None,
                        actor_role="system",
                        severity="warning" if gate["status"] == "BLOCKED" else "info",
                        details={"status": gate["status"], "reasons": gate["reasons"]},
                    )
            except Exception as exc:
                logger.exception("Release gate guard loop error: %s", exc)
            finally:
                db.close()

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

                        idempotency_key = (
                            f"idempotency:signal:{bot.id}:{event.symbol}:{event.timeframe}:"
                            f"{event.timestamp.strftime('%Y%m%d%H%M')}:{signal.direction}"
                        )
                        if self.cache.get(idempotency_key):
                            incr_counter(self.cache, "metrics:duplicates_blocked:5m", 1)
                            continue
                        self.cache.set(idempotency_key, utc_now_iso())
                        incr_counter(self.cache, "metrics:idempotency_keys:5m", 1)

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
                            cache=self.cache,
                            signal=signal,
                            market_type=bot.market_type,
                            market_price=market_price,
                            spread_bps=spread_bps,
                            atr_pct=atr_pct,
                        )

                        if not risk_decision.approved:
                            if any(
                                tag in {"correlated_cluster_overload", "high_pair_correlation"}
                                for tag in risk_decision.risk_tags
                            ):
                                incr_counter(self.cache, "metrics:correlation_rejections:5m", 1)
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

                        execution_result = open_paper_position(
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
                            execution_context={
                                "spread_bps": spread_bps,
                                "latency_ms": self.market_data_engine.latency_ms,
                            },
                        )
                        incr_counter(self.cache, "metrics:state_transitions:5m", execution_result["transition_count"])

                        if execution_result["position"] is None:
                            create_failed_event(
                                db,
                                event_type="execution_not_filled",
                                entity_type="execution_event",
                                entity_id=execution_result["execution_event"].id,
                                payload={
                                    "final_state": execution_result["final_state"],
                                    "state_path": execution_result["state_path"],
                                    "strategy": signal.strategy_id,
                                    "retry_budget_used": execution_result.get("retry_budget_used", 0),
                                    "partial_fill_ratio": execution_result.get("partial_fill_ratio", 0),
                                },
                                error_message="Execution state machine ended without fill",
                            )
                            create_audit_log(
                                db,
                                action="trade_rejected",
                                entity_type="execution_event",
                                entity_id=execution_result["execution_event"].id,
                                actor_user_id=user.id,
                                actor_role=user.role.value,
                                severity="warning",
                                details={"final_state": execution_result["final_state"]},
                            )
                            continue

                        position = execution_result["position"]
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
            self.cache.set("metrics:duplicates_blocked:5m", "0")
            self.cache.set("metrics:idempotency_keys:5m", "0")
            self.cache.set("metrics:state_transitions:5m", "0")
            self.cache.set("metrics:websocket_reconnects:5m", "0")
            self.cache.set("metrics:correlation_rejections:5m", "0")

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
        pending_failed = db.query(FailedEvent).filter(FailedEvent.status.in_(["pending", "retrying"])).count()
        dead_failed = db.query(FailedEvent).filter(FailedEvent.status == "dead").count()
        release_gate_status = self.cache.get("phase4:release_gate:status") or "UNKNOWN"
        release_gate_last_checked = self.cache.get("phase4:release_gate:last_checked") or "-"
        return {
            "websocket_status": ws.get("status", self.market_data_engine.websocket_status),
            "heartbeat": ws.get("heartbeat", self.market_data_engine.last_heartbeat),
            "signal_rate_last_5m": get_counter(self.cache, "metrics:signals:5m"),
            "paper_trades_last_5m": get_counter(self.cache, "metrics:paper_trades:5m"),
            "open_positions": db.query(PaperPosition).filter(PaperPosition.status == "open").count(),
            "latency_ms": orchestrator.get("latency_ms", self.market_data_engine.latency_ms),
            "queue_depth": self.candle_queue.qsize(),
            "active_bots_running": db.query(BotProfile).filter(BotProfile.is_running.is_(True)).count(),
            "websocket_reconnects_5m": get_counter(self.cache, "metrics:websocket_reconnects:5m"),
            "idempotency_keys_5m": get_counter(self.cache, "metrics:idempotency_keys:5m"),
            "duplicate_signals_blocked_5m": get_counter(self.cache, "metrics:duplicates_blocked:5m"),
            "execution_transitions_5m": get_counter(self.cache, "metrics:state_transitions:5m"),
            "failed_events_pending": pending_failed,
            "failed_events_dead": dead_failed,
            "correlation_rejections_5m": get_counter(self.cache, "metrics:correlation_rejections:5m"),
            "release_gate_status": release_gate_status,
            "release_gate_last_checked": release_gate_last_checked,
        }

    def hardening_summary(self, db):
        monitoring = self.monitoring_snapshot(db)
        last_rebuild = db.query(StateRebuildLog).order_by(StateRebuildLog.started_at.desc()).first()
        return {
            "websocket_reconnects_5m": monitoring["websocket_reconnects_5m"],
            "idempotency_keys_5m": monitoring["idempotency_keys_5m"],
            "duplicate_signals_blocked_5m": monitoring["duplicate_signals_blocked_5m"],
            "execution_transitions_5m": monitoring["execution_transitions_5m"],
            "failed_events_pending": monitoring["failed_events_pending"],
            "failed_events_dead": monitoring["failed_events_dead"],
            "last_state_rebuild_status": last_rebuild.status if last_rebuild else "unknown",
            "last_state_rebuild_at": last_rebuild.finished_at if last_rebuild else None,
        }

    def list_execution_state_transitions(self, db, limit: int = 200):
        return (
            db.query(ExecutionStateTransition)
            .order_by(ExecutionStateTransition.occurred_at.desc())
            .limit(limit)
            .all()
        )


pipeline_runtime = PipelineRuntime(redis_client)