from __future__ import annotations

from datetime import datetime, timezone

from models import StrategyTemplate


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
        },
        "validation_result": {
            "ok": len(validation_errors) == 0,
            "errors": validation_errors,
            "override_used": bool(overrides),
        },
    }
