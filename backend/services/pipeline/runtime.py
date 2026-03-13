import asyncio
import logging
from datetime import datetime, timezone

from db import SessionLocal, redis_client
from models import (
    BotProfile,
    ExecutionStateTransition,
    FailedEvent,
    PaperPosition,
    PositionLedgerEvent,
    SignalEvent,
    StateRebuildLog,
    StrategyTemplate,
    User,
    UserRole,
    UserScannerAutomationConfig,
    UserScannerAutomationProfile,
)
from core.users.user_scanner_signal_service import run_user_scanner
from services.audit_service import create_audit_log
from services.execution_policy_service import get_policy_for_strategy
from services.failed_event_service import create_failed_event, mark_failed_event_resolved, mark_failed_event_retry
from services.pipeline.cache_store import get_counter, get_json, incr_counter, set_json, utc_now_iso
from services.pipeline.execution_engine import open_paper_position, refresh_open_positions
from services.pipeline.kill_switch_service import (
    evaluate_kill_switch,
    kill_switch_state,
    pause_all_bots_for_kill_switch,
)
from services.pipeline.market_data_engine import MarketDataEngine
from services.pipeline.risk_engine import evaluate_risk
from services.pipeline.spot_dynamic_score_engine import run_dynamic_selection_cycle
from services.pipeline.spot_strategy_service import (
    bootstrap_market_data_store,
    generate_daily_strategy_report,
    refresh_spot_tradable_universe,
    update_indicator_cache,
)
from services.strategy_observability_service import log_risk_outcome_event, log_strategy_observability_events
from services.pipeline.strategy_engine import evaluate_strategy
from services.pipeline.universe_engine import build_effective_universe
from services.live_mode_service import enforce_release_gate

logger = logging.getLogger(__name__)

SPOT_STRATEGY_TYPES = {
    "spot_pullback",
    "spot_pullback_v1",
    "spot_range_reversion",
    "spot_range_reversion_v1",
    "spot_volatility_breakout",
    "spot_volatility_breakout_v1",
}


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
        self._kill_switch_task: asyncio.Task | None = None
        self._spot_universe_task: asyncio.Task | None = None
        self._daily_report_task: asyncio.Task | None = None
        self._scanner_automation_task: asyncio.Task | None = None
        self._last_release_gate_status: str | None = None
        self._last_kill_switch_active: bool = False
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
        self._kill_switch_task = asyncio.create_task(self._kill_switch_guard_loop(), name="kill-switch-guard")
        self._spot_universe_task = asyncio.create_task(self._spot_universe_refresh_loop(), name="spot-universe-refresh")
        self._daily_report_task = asyncio.create_task(self._daily_strategy_report_loop(), name="spot-daily-report")
        self._scanner_automation_task = asyncio.create_task(
            self._scanner_automation_loop(),
            name="user-scanner-automation",
        )
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
            self._kill_switch_task,
            self._spot_universe_task,
            self._daily_report_task,
            self._scanner_automation_task,
        ]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _scanner_automation_loop(self):
        while self._running:
            await asyncio.sleep(15)
            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                profile_rows = (
                    db.query(UserScannerAutomationProfile)
                    .filter(UserScannerAutomationProfile.auto_enabled.is_(True))
                    .all()
                )
                profiled_user_ids = {row.user_id for row in profile_rows}

                legacy_rows = (
                    db.query(UserScannerAutomationConfig)
                    .filter(UserScannerAutomationConfig.auto_enabled.is_(True))
                    .all()
                )

                for row in profile_rows:
                    interval_seconds = max(180, int(row.interval_seconds or 180))
                    if row.last_run_at:
                        last_run_at = row.last_run_at
                        if last_run_at.tzinfo is None:
                            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
                        if (now - last_run_at).total_seconds() < interval_seconds:
                            continue

                    user = (
                        db.query(User)
                        .filter(
                            User.id == row.user_id,
                            User.role == UserRole.USER,
                            User.is_active.is_(True),
                            User.approval_status == "approved",
                        )
                        .first()
                    )
                    if user is None:
                        continue

                    try:
                        result = run_user_scanner(
                            db,
                            user.id,
                            requested_mode=None,
                            max_results=int(row.max_results or 25),
                            symbol_source=str(row.symbol_source or "crypto"),
                            selected_symbols=list(row.selected_symbols or []),
                            symbol_selection_mode=str(row.symbol_selection_mode or "top_active_50"),
                        )
                        row.last_run_at = now
                        row.last_run_status = "success"
                        row.last_run_error = None
                        row.last_run_id = str(result.get("run_id") or "")
                        row.last_actionable_count = int(result.get("actionable_count") or 0)
                    except Exception as exc:
                        row.last_run_at = now
                        row.last_run_status = "error"
                        row.last_run_error = str(exc)[:240]

                for row in legacy_rows:
                    if row.user_id in profiled_user_ids:
                        continue
                    interval_seconds = max(180, int(row.interval_seconds or 180))
                    if row.last_run_at:
                        last_run_at = row.last_run_at
                        if last_run_at.tzinfo is None:
                            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
                        if (now - last_run_at).total_seconds() < interval_seconds:
                            continue

                    user = (
                        db.query(User)
                        .filter(
                            User.id == row.user_id,
                            User.role == UserRole.USER,
                            User.is_active.is_(True),
                            User.approval_status == "approved",
                        )
                        .first()
                    )
                    if user is None:
                        continue

                    try:
                        result = run_user_scanner(
                            db,
                            user.id,
                            requested_mode=None,
                            max_results=int(row.max_results or 25),
                            symbol_source=str(row.symbol_source or "crypto"),
                            selected_symbols=list(row.selected_symbols or []),
                            symbol_selection_mode=str(row.symbol_selection_mode or "top_active_50"),
                        )
                        row.last_run_at = now
                        row.last_run_status = "success"
                        row.last_run_error = None
                        row.last_run_id = str(result.get("run_id") or "")
                        row.last_actionable_count = int(result.get("actionable_count") or 0)
                    except Exception as exc:
                        row.last_run_at = now
                        row.last_run_status = "error"
                        row.last_run_error = str(exc)[:240]

                db.commit()
            except Exception as exc:
                logger.exception("Scanner automation loop error: %s", exc)
            finally:
                db.close()

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

    async def _kill_switch_guard_loop(self):
        while self._running:
            await asyncio.sleep(10)
            db = SessionLocal()
            try:
                state = evaluate_kill_switch(db, self.cache, self.market_data_engine)
                if state["active"] and not self._last_kill_switch_active:
                    stopped_bots = pause_all_bots_for_kill_switch(db)
                    create_audit_log(
                        db,
                        action="kill_switch_triggered",
                        entity_type="kill_switch",
                        entity_id="global",
                        actor_user_id=None,
                        actor_role="system",
                        severity="critical",
                        details={
                            "reasons": state["reasons"],
                            "stopped_bots": stopped_bots,
                            "mode": "block_new_orders_only",
                        },
                    )
                self._last_kill_switch_active = state["active"]
            except Exception as exc:
                logger.exception("Kill switch guard loop error: %s", exc)
            finally:
                db.close()

    async def _spot_universe_refresh_loop(self):
        while self._running:
            db = SessionLocal()
            try:
                cached = get_json(self.cache, "universe:spot:tradable") or {}
                generated_at = str(cached.get("generated_at", ""))
                current_day = datetime.now(timezone.utc).date().isoformat()
                should_refresh = not generated_at.startswith(current_day)
                if should_refresh:
                    payload = refresh_spot_tradable_universe(self.cache)
                    symbols = payload.get("symbols", [])
                    if "BTCUSDT" not in symbols:
                        symbols = [*symbols, "BTCUSDT"]
                    bootstrap_result = bootstrap_market_data_store(self.cache, symbols)
                    create_audit_log(
                        db,
                        action="SPOT_UNIVERSE_REFRESHED",
                        entity_type="spot_universe",
                        entity_id=current_day,
                        actor_user_id=None,
                        actor_role="system",
                        severity="info",
                        details={
                            "symbol_count": payload.get("count", 0),
                            "seeded": bootstrap_result.get("seeded", 0),
                            "failed": bootstrap_result.get("failed", []),
                        },
                    )
            except Exception as exc:
                logger.exception("Spot universe refresh loop error: %s", exc)
            finally:
                db.close()
            await asyncio.sleep(3600)

    async def _daily_strategy_report_loop(self):
        while self._running:
            await asyncio.sleep(3600)
            now = datetime.now(timezone.utc)
            if now.hour != 0:
                continue
            db = SessionLocal()
            try:
                report = generate_daily_strategy_report(db, self.cache)
                create_audit_log(
                    db,
                    action="DAILY_STRATEGY_REPORT_GENERATED",
                    entity_type="strategy_report",
                    entity_id=report["date"],
                    actor_user_id=None,
                    actor_role="system",
                    severity="info",
                    details={"daily_trades": report.get("daily_trades", 0), "win_rate": report.get("win_rate", 0)},
                )
                for key in [
                    "spot_strategy:signals_total:day",
                    "spot_strategy:signals_after_hard_gate:day",
                    "spot_strategy:signals_above_threshold:day",
                    "spot_strategy:signals_selected:day",
                    "spot_strategy:rejected:trend_strength_weak",
                    "spot_strategy:rejected:btc_regime_hostile",
                    "spot_strategy:rejected:freeze_guard",
                    "spot_strategy:rejected:threshold",
                    "spot_strategy:executed_signals:day",
                    "spot_strategy:signal_score_sum:day",
                    "spot_strategy:avg_signal_score:day",
                ]:
                    self.cache.set(key, "0")
            except Exception as exc:
                logger.exception("Daily strategy report loop error: %s", exc)
            finally:
                db.close()

    def _apply_spot_metrics_counters(self, metrics: dict):
        counter_map = {
            "signals_total": "spot_strategy:signals_total:day",
            "signals_after_hard_gate": "spot_strategy:signals_after_hard_gate:day",
            "signals_above_threshold": "spot_strategy:signals_above_threshold:day",
            "signals_selected": "spot_strategy:signals_selected:day",
            "signals_rejected_trend_strength": "spot_strategy:rejected:trend_strength_weak",
            "signals_rejected_btc_regime": "spot_strategy:rejected:btc_regime_hostile",
            "signals_rejected_freeze_guard": "spot_strategy:rejected:freeze_guard",
            "signals_rejected_threshold": "spot_strategy:rejected:threshold",
        }
        for metric_key, cache_key in counter_map.items():
            value = int(metrics.get(metric_key, 0))
            if value > 0:
                incr_counter(self.cache, cache_key, value)

    def _process_spot_pullback_selection(self, db, *, bot: BotProfile, user: User, event, universe: dict, params: dict):
        if event.timeframe != "15m" or event.symbol != "BTCUSDT":
            return

        idempotency_key = f"idempotency:spot-pullback-cycle:{bot.id}:{event.timestamp.strftime('%Y%m%d%H%M')}"
        if self.cache.get(idempotency_key):
            incr_counter(self.cache, "metrics:duplicates_blocked:5m", 1)
            return
        self.cache.set(idempotency_key, utc_now_iso())

        open_positions = (
            db.query(PaperPosition)
            .filter(PaperPosition.user_id == user.id, PaperPosition.market_type == "spot", PaperPosition.status == "open")
            .all()
        )
        open_symbols = {position.symbol.upper() for position in open_positions}
        max_open_positions = int(params.get("max_open_positions", 3))
        available_slots = max(max_open_positions - len(open_positions), 0)

        symbols = [symbol.upper() for symbol in universe.get("spot_symbols", [])]
        selection = run_dynamic_selection_cycle(
            self.cache,
            symbols=symbols,
            open_symbols=open_symbols,
            available_slots=available_slots,
            params=params,
        )
        metrics = selection.get("metrics", {})
        self._apply_spot_metrics_counters(metrics)

        cycle_entity_id = f"{bot.id}:{event.timestamp.strftime('%Y%m%d%H%M')}"
        cycle_audit_log = create_audit_log(
            db,
            action="SPOT_SELECTION_CYCLE_COMPLETED",
            entity_type="spot_selection_cycle",
            entity_id=cycle_entity_id,
            actor_user_id=user.id,
            actor_role=user.role.value,
            severity="info",
            details={
                "symbol_count": selection.get("symbol_count", 0),
                "signals_selected": metrics.get("signals_selected", 0),
                "market_regime": selection.get("market_regime"),
                "active_strategy_id": selection.get("active_strategy_id"),
                "active_strategy_enabled": selection.get("active_strategy_enabled"),
                "btc_regime": selection.get("btc_regime"),
                "threshold": selection.get("threshold"),
                "freeze_guard": selection.get("freeze_guard"),
            },
        )

        regime_state = selection.get("regime_state", {})
        if regime_state.get("changed"):
            create_audit_log(
                db,
                action="SPOT_MARKET_REGIME_CHANGED",
                entity_type="spot_market_regime",
                entity_id=cycle_entity_id,
                actor_user_id=user.id,
                actor_role=user.role.value,
                severity="info",
                details={
                    "active_regime": regime_state.get("active_regime"),
                    "raw_regime": regime_state.get("raw_regime"),
                    "pending_count": regime_state.get("pending_count"),
                    "confirmation_candles": 2,
                },
            )

        clamp_events = selection.get("multiplier_clamp_events", [])
        if clamp_events:
            create_audit_log(
                db,
                action="SPOT_MULTIPLIER_CLAMP_APPLIED",
                entity_type="spot_selection_cycle",
                entity_id=cycle_entity_id,
                actor_user_id=user.id,
                actor_role=user.role.value,
                severity="warning",
                details={"events": clamp_events},
            )

        log_strategy_observability_events(
            db,
            selection_cycle_id=cycle_entity_id,
            audit_log_id=cycle_audit_log.id,
            bot_profile_id=bot.id,
            user_id=user.id,
            strategy_id=selection.get("active_strategy_id", "spot_pullback_v1"),
            strategy_name=selection.get("active_strategy_name", "SPOT_TREND_PULLBACK"),
            market_regime=selection.get("market_regime", "RANGING"),
            multiplier_version=selection.get("multiplier_version", "v1"),
            multiplier_set=selection.get("multiplier_set", {}),
            ranked=selection.get("ranked", []),
            selected=selection.get("selected", []),
        )

        selected_candidates = selection.get("selected", [])
        for candidate in selected_candidates:
            signal_event = SignalEvent(
                bot_profile_id=bot.id,
                user_id=user.id,
                symbol=candidate["symbol"],
                market_type=bot.market_type,
                timeframe=bot.timeframe,
                strategy_id=candidate.get("strategy_id", "spot_pullback_v1"),
                signal="long",
                direction="long",
                confidence=round(candidate.get("adjusted_score", 0.0) / 100, 4),
                reason_codes=["selected_dynamic_score_engine"],
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
                details={
                    "symbol": candidate["symbol"],
                    "direction": "long",
                    "strategy": candidate.get("strategy_id", "spot_pullback_v1"),
                    "selection_rank": candidate.get("selection_rank"),
                },
            )
            incr_counter(self.cache, "metrics:signals:5m", 1)

            signal = evaluate_strategy(
                strategy_type=candidate.get("strategy_id", "spot_pullback_v1"),
                symbol=candidate["symbol"],
                primary_candles=get_json(self.cache, f"market:candles:{candidate['symbol']}:15m") or [],
                secondary_candles=get_json(self.cache, f"market:candles:{candidate['symbol']}:1h") or [],
                spread_bps=float((get_json(self.cache, f"market:spread:{candidate['symbol']}") or {}).get("spread_bps", 9999)),
                params=params,
                context={"btc_candles": get_json(self.cache, "market:candles:BTCUSDT:15m") or []},
            )
            signal.signal = "long"
            signal.direction = "long"
            signal.strategy_id = candidate.get("strategy_id", signal.strategy_id)
            signal.proposed_entry = float(candidate.get("entry", signal.proposed_entry))
            signal.proposed_stop = float(candidate.get("stop", signal.proposed_stop))
            signal.proposed_take_profit = float(candidate.get("take_profit", signal.proposed_take_profit))
            signal.signal_strength = round(candidate.get("adjusted_score", 0.0) / 100, 4)
            signal.signal_score = float(candidate.get("adjusted_score", 0.0))
            signal.reason_codes = ["selected_dynamic_score_engine"]
            signal.metadata = {
                **(signal.metadata or {}),
                "strategy_name": candidate.get("strategy_name", "SPOT_TREND_PULLBACK"),
                "market_regime": candidate.get("market_regime"),
                "multiplier_version": candidate.get("multiplier_version"),
                "multiplier_set": candidate.get("multiplier_set"),
                "base_score": candidate.get("base_score"),
                "adjusted_score": candidate.get("adjusted_score"),
                "score_delta": candidate.get("score_delta"),
                "selection_rank": candidate.get("selection_rank"),
            }

            ticker_payload = get_json(self.cache, f"market:ticker:{candidate['symbol']}") or {}
            market_price = float(ticker_payload.get("last_price", candidate.get("entry", signal.proposed_entry)))
            atr_pct = abs(signal.proposed_entry - signal.proposed_stop) / signal.proposed_entry if signal.proposed_entry else 1
            risk_decision = evaluate_risk(
                db,
                current_user=user,
                cache=self.cache,
                signal=signal,
                market_type=bot.market_type,
                market_price=market_price,
                spread_bps=float((get_json(self.cache, f"market:spread:{candidate['symbol']}") or {}).get("spread_bps", 9999)),
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
                    details={
                        "tags": risk_decision.risk_tags,
                        "risk_check_result": "rejected",
                        "capital_allocation": risk_decision.capital_allocation,
                    },
                )
                log_risk_outcome_event(
                    db,
                    selection_cycle_id=cycle_entity_id,
                    audit_log_id=None,
                    bot_profile_id=bot.id,
                    user_id=user.id,
                    symbol=candidate["symbol"],
                    strategy_id=candidate.get("strategy_id", "spot_pullback_v1"),
                    strategy_name=candidate.get("strategy_name", "SPOT_TREND_PULLBACK"),
                    market_regime=candidate.get("market_regime", "RANGING"),
                    multiplier_version=candidate.get("multiplier_version", "v1"),
                    multiplier_set=candidate.get("multiplier_set", {}),
                    base_score=float(candidate.get("base_score", 0.0)),
                    adjusted_score=float(candidate.get("adjusted_score", 0.0)),
                    score_delta=float(candidate.get("score_delta", 0.0)),
                    selection_rank=candidate.get("selection_rank"),
                    trend_strength=candidate.get("trend_strength"),
                    relative_volume=float(candidate.get("relative_volume", 0.0) or 0.0),
                    risk_check_result="rejected",
                    capital_allocation=risk_decision.capital_allocation,
                    reason_codes=risk_decision.risk_tags,
                )
                continue

            log_risk_outcome_event(
                db,
                selection_cycle_id=cycle_entity_id,
                audit_log_id=None,
                bot_profile_id=bot.id,
                user_id=user.id,
                symbol=candidate["symbol"],
                strategy_id=candidate.get("strategy_id", "spot_pullback_v1"),
                strategy_name=candidate.get("strategy_name", "SPOT_TREND_PULLBACK"),
                market_regime=candidate.get("market_regime", "RANGING"),
                multiplier_version=candidate.get("multiplier_version", "v1"),
                multiplier_set=candidate.get("multiplier_set", {}),
                base_score=float(candidate.get("base_score", 0.0)),
                adjusted_score=float(candidate.get("adjusted_score", 0.0)),
                score_delta=float(candidate.get("score_delta", 0.0)),
                selection_rank=candidate.get("selection_rank"),
                trend_strength=candidate.get("trend_strength"),
                relative_volume=float(candidate.get("relative_volume", 0.0) or 0.0),
                risk_check_result="approved",
                capital_allocation=risk_decision.capital_allocation,
                reason_codes=risk_decision.risk_tags,
            )

            policy = get_policy_for_strategy(db, candidate.get("strategy_id", bot.strategy_type))
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
                    "risk_check_result": "approved",
                    "capital_allocation": risk_decision.capital_allocation,
                    "strategy_name": candidate.get("strategy_name", "SPOT_TREND_PULLBACK"),
                    "market_regime": candidate.get("market_regime"),
                    "multiplier_version": candidate.get("multiplier_version"),
                    "multiplier_set": candidate.get("multiplier_set"),
                    "base_score": candidate.get("base_score"),
                    "adjusted_score": candidate.get("adjusted_score"),
                    "score_delta": candidate.get("score_delta"),
                    "selection_rank": candidate.get("selection_rank"),
                },
                execution_context={
                    "spread_bps": float((get_json(self.cache, f"market:spread:{candidate['symbol']}") or {}).get("spread_bps", 9999)),
                    "latency_ms": self.market_data_engine.latency_ms,
                },
            )
            incr_counter(self.cache, "metrics:state_transitions:5m", execution_result["transition_count"])

            if execution_result["position"] is None:
                incr_counter(self.cache, "metrics:execution_errors:5m", 1)
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
                    "selection_rank": candidate.get("selection_rank"),
                },
            )
            create_audit_log(
                db,
                action="TRADE_OPENED",
                entity_type="paper_position",
                entity_id=position.id,
                actor_user_id=user.id,
                actor_role=user.role.value,
                severity="info",
                details={
                    "symbol": position.symbol,
                    "strategy_id": candidate.get("strategy_id", "spot_pullback_v1"),
                    "strategy_name": candidate.get("strategy_name", "SPOT_TREND_PULLBACK"),
                    "market_regime": candidate.get("market_regime"),
                    "multiplier_version": candidate.get("multiplier_version"),
                    "base_score": candidate.get("base_score"),
                    "adjusted_score": candidate.get("adjusted_score"),
                    "score_delta": candidate.get("score_delta"),
                    "selection_rank": candidate.get("selection_rank"),
                    "risk_check_result": "approved",
                    "capital_allocation": risk_decision.capital_allocation,
                    "lifecycle_state": "OPEN",
                },
            )
            incr_counter(self.cache, "spot_strategy:executed_signals:day", 1)
            total_score = float(self.cache.get("spot_strategy:signal_score_sum:day") or 0)
            executed = int(self.cache.get("spot_strategy:executed_signals:day") or 1)
            total_score += float(candidate.get("adjusted_score", 0.0))
            self.cache.set("spot_strategy:signal_score_sum:day", str(total_score))
            self.cache.set("spot_strategy:avg_signal_score:day", str(round(total_score / max(executed, 1), 4)))
            incr_counter(self.cache, "metrics:paper_trades:5m", 1)

    async def _orchestrate(self):
        while self._running:
            event = await self.candle_queue.get()
            started = asyncio.get_event_loop().time()
            db = SessionLocal()
            try:
                if kill_switch_state(self.cache).get("active", False):
                    continue
                universe = build_effective_universe(db, self.cache)
                if event.timeframe == "15m":
                    symbol_candles = get_json(self.cache, f"market:candles:{event.symbol}:15m") or []
                    if symbol_candles:
                        update_indicator_cache(self.cache, event.symbol, symbol_candles)
                bots = (
                    db.query(BotProfile)
                    .filter(BotProfile.is_enabled.is_(True), BotProfile.is_running.is_(True), BotProfile.timeframe == event.timeframe)
                    .all()
                )
                for bot in bots:
                    try:
                        symbol_set = {symbol.upper() for symbol in bot.symbols}
                        if bot.strategy_type in SPOT_STRATEGY_TYPES and (not symbol_set or "*" in symbol_set):
                            symbol_set = {symbol.upper() for symbol in universe["spot_symbols"]}
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

                        if bot.strategy_type in SPOT_STRATEGY_TYPES:
                            self._process_spot_pullback_selection(
                                db,
                                bot=bot,
                                user=user,
                                event=event,
                                universe=universe,
                                params=params,
                            )
                            continue

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
                            context={"btc_candles": get_json(self.cache, "market:candles:BTCUSDT:15m") or []},
                        )

                        if signal.signal == "none":
                            if bot.strategy_type in SPOT_STRATEGY_TYPES:
                                incr_counter(self.cache, "spot_strategy:signals_total:day", 1)
                                if signal.reason_codes:
                                    reason = signal.reason_codes[0]
                                    reason_map = {
                                        "trend_strength_weak": "spot_strategy:rejected:trend_strength_weak",
                                        "btc_regime_hostile": "spot_strategy:rejected:btc_regime_hostile",
                                        "volume_spike_missing": "spot_strategy:rejected:relative_volume_low",
                                        "signal_score_below_executable": "spot_strategy:rejected:pullback_quality_low",
                                    }
                                    counter_key = reason_map.get(reason)
                                    if counter_key:
                                        incr_counter(self.cache, counter_key, 1)
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
                        if bot.strategy_type in SPOT_STRATEGY_TYPES:
                            incr_counter(self.cache, "spot_strategy:signals_total:day", 1)
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
                            if any(tag in {"missing_policy", "invalid_leverage_cap", "max_risk_per_trade_exceeded"} for tag in risk_decision.risk_tags):
                                incr_counter(self.cache, "metrics:risk_anomalies:5m", 1)
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
                                details={
                                    "tags": risk_decision.risk_tags,
                                    "risk_check_result": "rejected",
                                    "capital_allocation": risk_decision.capital_allocation,
                                },
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
                                "risk_check_result": "approved",
                                "capital_allocation": risk_decision.capital_allocation,
                                "signal_score": signal.signal_score,
                                "signal_strength": signal.signal_strength,
                                "signal_metadata": signal.metadata,
                            },
                            execution_context={
                                "spread_bps": spread_bps,
                                "latency_ms": self.market_data_engine.latency_ms,
                            },
                        )
                        incr_counter(self.cache, "metrics:state_transitions:5m", execution_result["transition_count"])

                        if execution_result["position"] is None:
                            incr_counter(self.cache, "metrics:execution_errors:5m", 1)
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
                        if bot.strategy_type in SPOT_STRATEGY_TYPES:
                            incr_counter(self.cache, "spot_strategy:executed_signals:day", 1)
                            total_score = float(self.cache.get("spot_strategy:signal_score_sum:day") or 0)
                            executed = int(self.cache.get("spot_strategy:executed_signals:day") or 1)
                            total_score += float(signal.signal_score)
                            self.cache.set("spot_strategy:signal_score_sum:day", str(total_score))
                            self.cache.set(
                                "spot_strategy:avg_signal_score:day",
                                str(round(total_score / max(executed, 1), 4)),
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
                        if bot.strategy_type in SPOT_STRATEGY_TYPES:
                            create_audit_log(
                                db,
                                action="TRADE_OPENED",
                                entity_type="paper_position",
                                entity_id=position.id,
                                actor_user_id=user.id,
                                actor_role=user.role.value,
                                severity="info",
                                details={
                                    "symbol": position.symbol,
                                    "signal_score": signal.signal_score,
                                    "lifecycle_state": "OPEN",
                                },
                            )
                        incr_counter(self.cache, "metrics:paper_trades:5m", 1)
                    except Exception as bot_exc:
                        logger.exception("Pipeline bot processing failure (%s): %s", bot.id, bot_exc)
                        incr_counter(self.cache, "metrics:execution_errors:5m", 1)
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
                    open_event = (
                        db.query(PositionLedgerEvent)
                        .filter(
                            PositionLedgerEvent.position_id == position.id,
                            PositionLedgerEvent.event_type == "trade_open",
                        )
                        .order_by(PositionLedgerEvent.created_at.asc())
                        .first()
                    )
                    strategy_id = ((open_event.payload or {}).get("strategy_id") if open_event else None) or ""

                    create_audit_log(
                        db,
                        action="trade_close",
                        entity_type="paper_position",
                        entity_id=position.id,
                        actor_user_id=user.id,
                        actor_role=user.role.value,
                        details={"reason": position.status, "realized_pnl": position.realized_pnl},
                    )
                    if strategy_id in SPOT_STRATEGY_TYPES:
                        if position.status == "stop_hit":
                            create_audit_log(
                                db,
                                action="STOP_LOSS_TRIGGERED",
                                entity_type="paper_position",
                                entity_id=position.id,
                                actor_user_id=user.id,
                                actor_role=user.role.value,
                                severity="warning",
                                details={"symbol": position.symbol, "realized_pnl": position.realized_pnl},
                            )
                        elif position.status == "tp_hit":
                            create_audit_log(
                                db,
                                action="TAKE_PROFIT_TRIGGERED",
                                entity_type="paper_position",
                                entity_id=position.id,
                                actor_user_id=user.id,
                                actor_role=user.role.value,
                                severity="info",
                                details={"symbol": position.symbol, "realized_pnl": position.realized_pnl},
                            )
                        create_audit_log(
                            db,
                            action="TRADE_CLOSED",
                            entity_type="paper_position",
                            entity_id=position.id,
                            actor_user_id=user.id,
                            actor_role=user.role.value,
                            severity="info",
                            details={
                                "symbol": position.symbol,
                                "state": "TAKE_PROFIT" if position.status == "tp_hit" else "STOPPED",
                                "realized_pnl": position.realized_pnl,
                            },
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
            self.cache.set("metrics:execution_errors:5m", "0")
            self.cache.set("metrics:risk_anomalies:5m", "0")

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
        kill_state = kill_switch_state(self.cache)
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
            "execution_errors_5m": get_counter(self.cache, "metrics:execution_errors:5m"),
            "risk_anomalies_5m": get_counter(self.cache, "metrics:risk_anomalies:5m"),
            "global_trading_pause": bool(kill_state.get("active", False)),
            "kill_switch_reasons": kill_state.get("reasons", []),
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