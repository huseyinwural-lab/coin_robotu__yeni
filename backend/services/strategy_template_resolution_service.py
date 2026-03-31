from __future__ import annotations

from datetime import datetime, timezone

from models import AuditLog, BacktestResultCard, BotProfile, StrategyTemplate, UserTradeProjection
from schemas import StrategyTemplateResponse

PROMOTION_STEPS = ["DRAFT", "VALIDATED", "BACKTEST_PASSED", "ACTIVE", "DEPRECATED", "ROLLED_BACK"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_param_schema(parameters: dict) -> dict:
    schema = {}
    for key, value in (parameters or {}).items():
        schema[key] = {"type": type(value).__name__, "default": value}
    return schema


def _state_rank(state: str | None) -> int:
    current = str(state or "").upper()
    if current in PROMOTION_STEPS:
        return PROMOTION_STEPS.index(current)
    return -1


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_outcome_analytics(trades: list[UserTradeProjection]) -> tuple[dict, list[dict], list[dict], dict]:
    recent_outcomes = []
    trace_spine = []

    for row in trades[:20]:
        recent_outcomes.append(
            {
                "trade_id": row.trade_id,
                "symbol": row.symbol,
                "status": row.status,
                "realized_pnl": row.realized_pnl,
                "unrealized_pnl": row.unrealized_pnl,
                "opened_at": row.opened_at,
                "closed_at": row.closed_at,
                "trace": {
                    "strategy_template_id": row.strategy_template_id,
                    "strategy_version_id": row.strategy_version_id,
                    "scan_run_id": row.scan_run_id,
                    "signal_id": row.signal_id,
                    "decision_card_id": row.decision_card_id,
                    "intent_id": row.intent_id,
                    "trade_id": row.trade_id,
                    "execution_trace_id": row.execution_trace_id,
                },
            }
        )

    for row in trades[:50]:
        trace_spine.append(
            {
                "strategy_template_id": row.strategy_template_id,
                "strategy_version_id": row.strategy_version_id,
                "scan_run_id": row.scan_run_id,
                "signal_id": row.signal_id,
                "decision_card_id": row.decision_card_id,
                "intent_id": row.intent_id,
                "trade_id": row.trade_id,
                "execution_trace_id": row.execution_trace_id,
            }
        )

    closed_like = [row for row in trades if str(row.status or "").upper() in {"CLOSED", "FILLED"}]
    wins = [row for row in closed_like if _safe_float(row.realized_pnl) > 0]
    gross_profit = sum(max(_safe_float(row.realized_pnl), 0.0) for row in closed_like)
    gross_loss_abs = abs(sum(min(_safe_float(row.realized_pnl), 0.0) for row in closed_like))
    profit_factor = round(gross_profit / gross_loss_abs, 4) if gross_loss_abs > 0 else (999.0 if gross_profit > 0 else 0.0)
    win_rate = round((len(wins) / len(closed_like)) * 100.0, 2) if closed_like else 0.0
    avg_realized = round(sum(_safe_float(row.realized_pnl) for row in closed_like) / len(closed_like), 6) if closed_like else 0.0
    avg_slippage = round(sum(_safe_float(row.slippage) for row in trades if row.slippage is not None) / max(len([r for r in trades if r.slippage is not None]), 1), 6)

    trace_complete = 0
    for spine in trace_spine:
        required_values = [
            spine.get("strategy_template_id"),
            spine.get("strategy_version_id"),
            spine.get("scan_run_id"),
            spine.get("signal_id"),
            spine.get("decision_card_id"),
            spine.get("intent_id"),
            spine.get("trade_id"),
            spine.get("execution_trace_id"),
        ]
        if all(required_values):
            trace_complete += 1
    trace_coverage_pct = round((trace_complete / len(trace_spine)) * 100.0, 2) if trace_spine else 0.0

    status_counts: dict[str, int] = {}
    for row in trades:
        key = str(row.status or "UNKNOWN").upper()
        status_counts[key] = status_counts.get(key, 0) + 1

    learning_feedback = {
        "feedback_loop_status": "ACTIVE",
        "recommendations": [
            {
                "code": "tighten_entry_filter",
                "priority": "HIGH" if win_rate < 45 and len(closed_like) >= 10 else "LOW",
                "reason": "Win rate düşükse giriş filtresi sıkılaştırılmalı",
            },
            {
                "code": "execution_profile_review",
                "priority": "MEDIUM" if abs(avg_slippage) > 0.35 else "LOW",
                "reason": "Slippage yüksekse execution profile gözden geçirilmeli",
            },
            {
                "code": "trace_instrumentation_gap",
                "priority": "HIGH" if trace_coverage_pct < 80 else "LOW",
                "reason": "Trace spine kapsaması düşükse pipeline id geçişleri tamamlanmalı",
            },
        ],
    }

    analytics = {
        "performance_summary": {
            "trade_count": len(trades),
            "closed_trade_count": len(closed_like),
            "win_rate": win_rate,
            "avg_realized_pnl": avg_realized,
            "profit_factor": profit_factor,
            "avg_slippage": avg_slippage,
            "status_distribution": status_counts,
        },
        "trace_quality": {
            "trace_complete_count": trace_complete,
            "trace_total_count": len(trace_spine),
            "trace_coverage_pct": trace_coverage_pct,
        },
        "learning_feedback": learning_feedback,
    }

    return analytics, recent_outcomes, trace_spine, learning_feedback


def _build_promotion_lifecycle(*, template: StrategyTemplate, audits: list[AuditLog]) -> list[dict]:
    audit_map = {
        "strategy_template_validated": "VALIDATED",
        "strategy_template_backtest_passed": "BACKTEST_PASSED",
        "strategy_template_promoted_active": "ACTIVE",
        "strategy_template_activated": "ACTIVE",
        "strategy_template_deprecated": "DEPRECATED",
        "strategy_template_rolled_back": "ROLLED_BACK",
    }
    first_seen_at: dict[str, datetime] = {}
    for row in reversed(audits):
        state = audit_map.get(str(row.action or ""))
        if state and state not in first_seen_at:
            first_seen_at[state] = row.created_at

    current_rank = _state_rank(template.lifecycle_state)
    lifecycle = []
    for idx, state in enumerate(PROMOTION_STEPS):
        if idx < current_rank:
            phase_status = "completed"
        elif idx == current_rank:
            phase_status = "current"
        else:
            phase_status = "pending"
        lifecycle.append(
            {
                "state": state,
                "phase_status": phase_status,
                "event_at": first_seen_at.get(state),
                "is_current": str(template.lifecycle_state or "").upper() == state,
            }
        )
    return lifecycle


def resolve_strategy_template(db, *, template_id: str | None = None, strategy_type: str | None = None) -> StrategyTemplate | None:
    query = db.query(StrategyTemplate)
    if template_id:
        return query.filter(StrategyTemplate.id == template_id).first()
    if strategy_type:
        return (
            query.filter(StrategyTemplate.strategy_type == strategy_type, StrategyTemplate.is_active.is_(True))
            .order_by(StrategyTemplate.updated_at.desc())
            .first()
        )
    return None


def resolve_effective_strategy_config(db, *, template_id: str | None = None, strategy_type: str | None = None, override_params: dict | None = None) -> dict:
    template = resolve_strategy_template(db, template_id=template_id, strategy_type=strategy_type)
    if template is None:
        return {"template_id": None, "effective_runtime_config": {}, "validation_result": {"ok": False, "reason": "template_not_found"}}
    base_params = dict(template.parameters or {})
    overrides = dict(override_params or {})
    effective = {**base_params, **overrides}
    param_schema = dict(template.param_schema or _default_param_schema(base_params))
    validation_errors = []
    for key, meta in param_schema.items():
        expected = str(meta.get("type") or "")
        if key not in effective:
            continue
        value = effective[key]
        if expected == "int" and not isinstance(value, int):
            validation_errors.append(f"{key}:expected_int")
        if expected == "float" and not isinstance(value, (int, float)):
            validation_errors.append(f"{key}:expected_float")
    return {
        "template_id": template.id,
        "template_code": template.template_code,
        "version_group_id": template.version_group_id,
        "version_num": template.version_num,
        "lifecycle_state": template.lifecycle_state,
        "effective_runtime_config": {
            "strategy_type": template.strategy_type,
            "template_name": template.name,
            "parameters": effective,
            "logic_schema": template.logic_schema or {},
            "indicator_schema": template.indicator_schema or {},
            "execution_profile_ref": template.execution_profile_ref,
            "risk_hint_ref": template.risk_hint_ref,
            "allowed_venues": template.allowed_venues or [],
            "allowed_modes": template.allowed_modes or [],
        },
        "validation_result": {
            "ok": len(validation_errors) == 0,
            "errors": validation_errors,
            "override_used": bool(overrides),
            "execution_compatibility": "PASS" if (template.allowed_modes or ["paper", "mock", "live_ready_disabled"]) else "FAIL",
            "runtime_eligible": template.lifecycle_state == "ACTIVE" and len(validation_errors) == 0,
            "lifecycle_state": template.lifecycle_state,
        },
    }


def ensure_seed_strategy_templates(db, *, created_by: str) -> None:
    seeds = [
        ("trend_following", {"ema_fast": 20, "ema_slow": 50}, {"indicators": ["ema_fast", "ema_slow"], "timeframe": "15m", "params": {"ema_fast": 20, "ema_slow": 50, "source": "close"}}, {"entry_rules": {"long_condition": "ema_fast > ema_slow", "threshold": 0}, "exit_rules": {"stop_loss_pct": 1.5, "take_profit_pct": 3.0, "exit_condition": "ema_fast < ema_slow"}, "risk_hints": {"position_size_hint_pct": 2.0, "max_exposure_hint_pct": 20.0}}),
        ("mean_reversion", {"rsi_period": 14, "rsi_low": 30, "rsi_high": 70}, {"indicators": ["rsi"], "timeframe": "15m", "params": {"rsi_period": 14}}, {"entry_rules": {"long_condition": "rsi < rsi_low", "threshold": 30}, "exit_rules": {"stop_loss_pct": 1.2, "take_profit_pct": 2.4, "exit_condition": "rsi > 50"}, "risk_hints": {"position_size_hint_pct": 1.5, "max_exposure_hint_pct": 15.0}}),
        ("breakout", {"range_period": 20, "breakout_buffer": 0.2}, {"indicators": ["range_high", "range_low"], "timeframe": "1h", "params": {"range_period": 20}}, {"entry_rules": {"long_condition": "price > range_high", "threshold": 0.2}, "exit_rules": {"stop_loss_pct": 1.8, "take_profit_pct": 4.0, "exit_condition": "price < range_low"}, "risk_hints": {"position_size_hint_pct": 1.8, "max_exposure_hint_pct": 18.0}}),
        ("volatility_expansion", {"atr_period": 14, "atr_threshold": 1.8}, {"indicators": ["atr"], "timeframe": "1h", "params": {"atr_period": 14}}, {"entry_rules": {"long_condition": "atr > atr_threshold", "threshold": 1.8}, "exit_rules": {"stop_loss_pct": 2.0, "take_profit_pct": 4.5, "exit_condition": "atr < 1.2"}, "risk_hints": {"position_size_hint_pct": 1.2, "max_exposure_hint_pct": 12.0}}),
    ]
    existing_codes = {str(getattr(row, "template_code", None) or row[0] or "") for row in db.query(StrategyTemplate.template_code).all()}
    for name, params, indicator_schema, logic_schema in seeds:
        if name in existing_codes:
            continue
        template = StrategyTemplate(
            name=name.replace("_", " ").title(),
            template_code=name,
            version_group_id=name,
            version_num=1,
            lifecycle_state="ACTIVE",
            strategy_type=name,
            parameters=params,
            param_schema={key: {"type": type(value).__name__, "default": value} for key, value in params.items()},
            logic_schema=logic_schema,
            indicator_schema=indicator_schema,
            execution_profile_ref="default",
            risk_hint_ref="balanced",
            allowed_venues=["binance"],
            allowed_modes=["paper", "mock", "live_ready_disabled"],
            is_active=True,
            created_by=created_by,
            last_validated_at=_now(),
        )
        db.add(template)
    db.commit()


def build_strategy_template_detail(db, *, template_id: str) -> dict | None:
    template = db.query(StrategyTemplate).filter(StrategyTemplate.id == template_id).first()
    if template is None:
        return None
    current_active = (
        db.query(StrategyTemplate)
        .filter(StrategyTemplate.version_group_id == template.version_group_id, StrategyTemplate.is_active.is_(True))
        .order_by(StrategyTemplate.version_num.desc())
        .first()
    )
    version_history = (
        db.query(StrategyTemplate)
        .filter(StrategyTemplate.version_group_id == template.version_group_id)
        .order_by(StrategyTemplate.version_num.desc())
        .all()
    )
    backtest = None
    if template.backtest_result_ref:
        backtest = db.query(BacktestResultCard).filter(BacktestResultCard.id == template.backtest_result_ref).first()
    else:
        backtest = db.query(BacktestResultCard).filter(BacktestResultCard.strategy_type == template.strategy_type).order_by(BacktestResultCard.updated_at.desc()).first()
    group_template_ids = [row.id for row in version_history]
    bots = db.query(BotProfile).filter(BotProfile.strategy_template_id.in_(group_template_ids)).all() if group_template_ids else []
    trades = (
        db.query(UserTradeProjection)
        .filter(UserTradeProjection.strategy_template_id.in_(group_template_ids))
        .order_by(UserTradeProjection.updated_at.desc())
        .limit(100)
        .all()
        if group_template_ids
        else []
    )
    audits = db.query(AuditLog).filter(AuditLog.entity_type == "strategy_template", AuditLog.entity_id == template.id).order_by(AuditLog.created_at.desc()).limit(50).all()
    resolved = resolve_effective_strategy_config(db, template_id=template.id)
    outcome_analytics, recent_outcomes, trace_spine, learning_feedback = _build_outcome_analytics(trades)
    promotion_lifecycle = _build_promotion_lifecycle(template=template, audits=audits)
    backtest_summary = {
        "latest_backtest": {
            "win_rate": getattr(backtest, "win_rate", None),
            "drawdown": getattr(backtest, "max_drawdown", None),
            "sample_size": getattr(backtest, "sample_size", None),
            "run_date": getattr(backtest, "updated_at", None),
        }
        if backtest
        else None,
        "validation_status": "PASS" if backtest else "NO_BACKTEST",
        "promotion_eligibility": bool(backtest and getattr(backtest, "win_rate", 0) >= 50 and getattr(backtest, "profit_factor", 0) >= 1.0),
    }
    return {
        "template": StrategyTemplateResponse.model_validate(template),
        "current_active_version": StrategyTemplateResponse.model_validate(current_active) if current_active else None,
        "version_history": [StrategyTemplateResponse.model_validate(row) for row in version_history],
        "param_editor_summary": {
            "param_schema": template.param_schema or {},
            "logic_schema": template.logic_schema or {},
            "indicator_schema": template.indicator_schema or {},
        },
        "scanner_bindings": {
            "selected_template": template.template_code,
            "effective_params": (resolved.get("effective_runtime_config") or {}).get("parameters") or {},
            "scan_usage_count": len([row for row in trades if row.scan_run_id]),
        },
        "bot_bindings": [
            {"bot_id": bot.id, "bot_name": bot.name, "status": bot.is_running, "symbol_source": getattr(bot, "symbol_source_type", "manual")}
            for bot in bots
        ],
        "backtest_summary": backtest_summary,
        "execution_compatibility": {
            "execution_profile_ref": template.execution_profile_ref,
            "risk_hint_ref": template.risk_hint_ref,
            "allowed_venues": template.allowed_venues or [],
            "allowed_modes": template.allowed_modes or [],
            "compatibility": resolved.get("validation_result", {}).get("execution_compatibility"),
        },
        "related_trades": [
            {
                "trade_id": row.trade_id,
                "status": row.status,
                "symbol": row.symbol,
                "strategy_template_id": row.strategy_template_id,
                "strategy_version_id": row.strategy_version_id,
                "scan_run_id": row.scan_run_id,
                "signal_id": row.signal_id,
                "decision_card_id": row.decision_card_id,
                "intent_id": row.intent_id,
                "execution_trace_id": row.execution_trace_id,
            }
            for row in trades[:20]
        ],
        "audit_timeline": [
            {"action": row.action, "actor": row.actor_user_id, "at": row.created_at, "details": row.details or {}}
            for row in audits
        ],
        "promotion_eligibility": backtest_summary,
        "promotion_lifecycle": promotion_lifecycle,
        "outcome_analytics": outcome_analytics,
        "recent_outcomes": recent_outcomes,
        "global_trace_spine": trace_spine,
        "learning_feedback_loop": learning_feedback,
    }
