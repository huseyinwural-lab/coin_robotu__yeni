from __future__ import annotations

from datetime import datetime, timezone

from models import AuditLog, BacktestResultCard, BotProfile, StrategyTemplate
from schemas import StrategyTemplateResponse


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_param_schema(parameters: dict) -> dict:
    schema = {}
    for key, value in (parameters or {}).items():
        schema[key] = {"type": type(value).__name__, "default": value}
    return schema


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
        },
    }


def ensure_seed_strategy_templates(db, *, created_by: str) -> None:
    if db.query(StrategyTemplate).count() > 0:
        return
    seeds = [
        ("trend_following", {"ema_fast": 20, "ema_slow": 50}, {"indicators": ["ema_fast", "ema_slow"], "timeframe": "15m", "params": {"ema_fast": 20, "ema_slow": 50, "source": "close"}}, {"entry_rules": {"long_condition": "ema_fast > ema_slow", "threshold": 0}, "exit_rules": {"stop_loss_pct": 1.5, "take_profit_pct": 3.0, "exit_condition": "ema_fast < ema_slow"}, "risk_hints": {"position_size_hint_pct": 2.0, "max_exposure_hint_pct": 20.0}}),
        ("mean_reversion", {"rsi_period": 14, "rsi_low": 30, "rsi_high": 70}, {"indicators": ["rsi"], "timeframe": "15m", "params": {"rsi_period": 14}}, {"entry_rules": {"long_condition": "rsi < rsi_low", "threshold": 30}, "exit_rules": {"stop_loss_pct": 1.2, "take_profit_pct": 2.4, "exit_condition": "rsi > 50"}, "risk_hints": {"position_size_hint_pct": 1.5, "max_exposure_hint_pct": 15.0}}),
        ("breakout", {"range_period": 20, "breakout_buffer": 0.2}, {"indicators": ["range_high", "range_low"], "timeframe": "1h", "params": {"range_period": 20}}, {"entry_rules": {"long_condition": "price > range_high", "threshold": 0.2}, "exit_rules": {"stop_loss_pct": 1.8, "take_profit_pct": 4.0, "exit_condition": "price < range_low"}, "risk_hints": {"position_size_hint_pct": 1.8, "max_exposure_hint_pct": 18.0}}),
        ("volatility_expansion", {"atr_period": 14, "atr_threshold": 1.8}, {"indicators": ["atr"], "timeframe": "1h", "params": {"atr_period": 14}}, {"entry_rules": {"long_condition": "atr > atr_threshold", "threshold": 1.8}, "exit_rules": {"stop_loss_pct": 2.0, "take_profit_pct": 4.5, "exit_condition": "atr < 1.2"}, "risk_hints": {"position_size_hint_pct": 1.2, "max_exposure_hint_pct": 12.0}}),
    ]
    for name, params, indicator_schema, logic_schema in seeds:
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
    bots = db.query(BotProfile).filter(BotProfile.strategy_template_id == template.id).all()
    audits = db.query(AuditLog).filter(AuditLog.entity_type == "strategy_template", AuditLog.entity_id == template.id).order_by(AuditLog.created_at.desc()).limit(50).all()
    resolved = resolve_effective_strategy_config(db, template_id=template.id)
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
        "audit_timeline": [
            {"action": row.action, "actor": row.actor_user_id, "at": row.created_at, "details": row.details or {}}
            for row in audits
        ],
        "promotion_eligibility": backtest_summary,
    }
