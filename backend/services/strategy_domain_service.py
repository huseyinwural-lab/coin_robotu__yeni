import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    AuditLog,
    CanonicalStrategyRegistry,
    ExecutionIntent,
    ExecutionIntentEvent,
    RegimeSnapshot,
    StrategyDefinition,
    StrategyObservabilityEvent,
    StrategyPromotionRequest,
    StrategyRegimeBinding,
    StrategyVersion,
    StrategyVersionLifecycle,
)
from services.decision_kernel_service import build_context_hash, build_decision_hash
from services.runtime_execution_service import map_decision_to_intent


_CACHE_TTL_SECONDS = 30
_strategy_cache: dict[str, tuple[float, str]] = {}
_version_cache: dict[str, tuple[float, str]] = {}

_LIFECYCLE_DRAFT = "draft"
_LIFECYCLE_VALIDATED = "validated"
_LIFECYCLE_DRY_RUN_PASSED = "dry_run_passed"
_LIFECYCLE_SHADOW = "shadow"
_LIFECYCLE_CANARY = "canary"
_LIFECYCLE_PRODUCTION = "production"
_LIFECYCLE_ROLLED_BACK = "rolled_back"
_LIFECYCLE_ARCHIVED = "archived"

_VALIDATION_PASS = "PASS"
_VALIDATION_FAIL = "FAIL"
_VALIDATION_PENDING = "pending"

_PROMOTION_PENDING = "pending"
_PROMOTION_APPROVED = "approved"
_PROMOTION_REJECTED = "rejected"
_PROMOTION_EXPIRED = "expired"

_ALLOWED_ROLLOUT_STAGES = {_LIFECYCLE_SHADOW, _LIFECYCLE_CANARY}

_DEFAULT_CONFIG_SCHEMA = {
    "required": {
        "momentum_threshold": {"type": "number", "min": 0.001, "max": 1.0},
        "base_size": {"type": "number", "min": 0.00000001, "max": 1000.0},
        "volatility_guard": {"type": "number", "min": 0.01, "max": 5.0},
    },
    "optional": {
        "neutral_threshold": {"type": "number", "min": 0.0, "max": 1.0},
        "allow_short": {"type": "boolean"},
        "max_positions": {"type": "integer", "min": 1, "max": 1000},
    },
    "forbidden": [],
}

_SCHEMA_REGISTRY: dict[str, dict[str, Any]] = {
    "default": _DEFAULT_CONFIG_SCHEMA,
    "trend": _DEFAULT_CONFIG_SCHEMA,
    "breakout": _DEFAULT_CONFIG_SCHEMA,
    "mean_reversion": {
        "required": {
            "momentum_threshold": {"type": "number", "min": 0.001, "max": 1.0},
            "base_size": {"type": "number", "min": 0.00000001, "max": 1000.0},
            "volatility_guard": {"type": "number", "min": 0.01, "max": 5.0},
            "reversion_strength": {"type": "number", "min": 0.0, "max": 1.0},
        },
        "optional": {
            "neutral_threshold": {"type": "number", "min": 0.0, "max": 1.0},
            "allow_short": {"type": "boolean"},
        },
        "forbidden": [],
    },
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 6)
    rank = max(0.0, min(1.0, percentile / 100.0)) * (len(sorted_values) - 1)
    low_index = int(rank)
    high_index = min(low_index + 1, len(sorted_values) - 1)
    weight = rank - low_index
    value = sorted_values[low_index] * (1 - weight) + sorted_values[high_index] * weight
    return round(value, 6)


def _flatten_payload(payload: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key in sorted(payload.keys()):
            new_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_payload(payload.get(key), new_prefix))
        return result
    if isinstance(payload, list):
        return {prefix: payload}
    return {prefix: payload}


def _infer_schema_key(strategy_code: str) -> str:
    normalized = str(strategy_code or "").strip().lower()
    for key in _SCHEMA_REGISTRY:
        if key != "default" and key in normalized:
            return key
    return "default"


def build_version_hash(*, config_json: dict, strategy_id: str, version_number: int, config_schema_version: str) -> str:
    canonical = canonical_json(config_json)
    raw = f"{canonical}|{strategy_id}|{version_number}|{config_schema_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_strategy(db: Session, strategy_id: str) -> StrategyDefinition | None:
    row = db.query(StrategyDefinition).filter(StrategyDefinition.strategy_id == strategy_id).first()
    if row is not None:
        _strategy_cache[strategy_id] = (time.time(), strategy_id)
    return row


def _get_strategy_for_update(db: Session, strategy_id: str) -> StrategyDefinition | None:
    return (
        db.query(StrategyDefinition)
        .filter(StrategyDefinition.strategy_id == strategy_id)
        .with_for_update()
        .first()
    )


def get_version(db: Session, version_id: str) -> StrategyVersion | None:
    row = db.query(StrategyVersion).filter(StrategyVersion.version_id == version_id).first()
    if row is not None:
        _version_cache[version_id] = (time.time(), version_id)
    return row


def get_active_strategy_set(db: Session) -> list[StrategyDefinition]:
    return (
        db.query(StrategyDefinition)
        .filter(StrategyDefinition.status == "active")
        .order_by(StrategyDefinition.updated_at.desc())
        .all()
    )


def get_active_version(db: Session, strategy_id: str) -> StrategyVersion | None:
    strategy = get_strategy(db, strategy_id)
    if strategy is None or strategy.active_version_id is None:
        return None
    return get_version(db, strategy.active_version_id)


def get_version_lifecycle(db: Session, strategy_version_id: str) -> StrategyVersionLifecycle | None:
    return (
        db.query(StrategyVersionLifecycle)
        .filter(StrategyVersionLifecycle.strategy_version_id == strategy_version_id)
        .first()
    )


def list_strategy_version_lifecycles(db: Session, strategy_id: str) -> list[StrategyVersionLifecycle]:
    return (
        db.query(StrategyVersionLifecycle)
        .filter(StrategyVersionLifecycle.strategy_id == strategy_id)
        .order_by(StrategyVersionLifecycle.created_at.desc())
        .all()
    )


def _ensure_version_lifecycle(
    db: Session,
    *,
    strategy_id: str,
    strategy_version_id: str,
    created_by: str,
    lifecycle_state: str = _LIFECYCLE_DRAFT,
) -> StrategyVersionLifecycle:
    existing = get_version_lifecycle(db, strategy_version_id)
    if existing is not None:
        return existing

    row = StrategyVersionLifecycle(
        lifecycle_id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        is_active=False,
        is_production=False,
        lifecycle_state=lifecycle_state,
        validation_status=_VALIDATION_PENDING,
        validation_errors_json=[],
        compatibility_status=_VALIDATION_PENDING,
        compatibility_report_json={},
        dry_run_status=_VALIDATION_PENDING,
        dry_run_report_json={},
        created_by=created_by,
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )
    db.add(row)
    db.flush()
    return row


def _ensure_single_active_lifecycle(db: Session, *, strategy_id: str, target_version_id: str) -> None:
    db.query(StrategyVersionLifecycle).filter(
        StrategyVersionLifecycle.strategy_id == strategy_id,
        StrategyVersionLifecycle.strategy_version_id != target_version_id,
    ).update({"is_active": False}, synchronize_session=False)
    db.query(StrategyVersionLifecycle).filter(
        StrategyVersionLifecycle.strategy_id == strategy_id,
        StrategyVersionLifecycle.strategy_version_id == target_version_id,
    ).update({"is_active": True}, synchronize_session=False)


def _ensure_single_production_lifecycle(db: Session, *, strategy_id: str, target_version_id: str) -> None:
    db.query(StrategyVersionLifecycle).filter(
        StrategyVersionLifecycle.strategy_id == strategy_id,
        StrategyVersionLifecycle.strategy_version_id != target_version_id,
    ).update({"is_production": False}, synchronize_session=False)
    db.query(StrategyVersionLifecycle).filter(
        StrategyVersionLifecycle.strategy_id == strategy_id,
        StrategyVersionLifecycle.strategy_version_id == target_version_id,
    ).update({"is_production": True}, synchronize_session=False)


def get_strategy_config_schema(strategy_code: str) -> dict[str, Any]:
    key = _infer_schema_key(strategy_code)
    return _SCHEMA_REGISTRY.get(key) or _SCHEMA_REGISTRY["default"]


def _validate_field_type(value: Any, expected_type: str) -> bool:
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _validate_config_by_schema(config_json: dict, schema: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    required = schema.get("required") or {}
    optional = schema.get("optional") or {}
    forbidden = set(schema.get("forbidden") or [])

    for field, rules in required.items():
        if field not in config_json:
            issues.append({"field": field, "error_code": "required_missing", "message": f"{field} zorunludur"})
            continue
        value = config_json.get(field)
        expected_type = str((rules or {}).get("type") or "").strip().lower()
        if expected_type and not _validate_field_type(value, expected_type):
            issues.append(
                {
                    "field": field,
                    "error_code": "invalid_type",
                    "message": f"{field} tipi {expected_type} olmalı",
                }
            )
            continue
        min_value = (rules or {}).get("min")
        max_value = (rules or {}).get("max")
        if isinstance(value, (int, float)) and min_value is not None and float(value) < float(min_value):
            issues.append({"field": field, "error_code": "min_violation", "message": f"{field} en az {min_value} olmalı"})
        if isinstance(value, (int, float)) and max_value is not None and float(value) > float(max_value):
            issues.append({"field": field, "error_code": "max_violation", "message": f"{field} en fazla {max_value} olmalı"})
        allowed_values = (rules or {}).get("enum")
        if isinstance(allowed_values, list) and value not in allowed_values:
            issues.append({"field": field, "error_code": "invalid_enum", "message": f"{field} geçersiz enum değeri"})

    for field, rules in optional.items():
        if field not in config_json:
            continue
        value = config_json.get(field)
        expected_type = str((rules or {}).get("type") or "").strip().lower()
        if expected_type and not _validate_field_type(value, expected_type):
            issues.append({"field": field, "error_code": "invalid_type", "message": f"{field} tipi {expected_type} olmalı"})

    for field in forbidden:
        if field in config_json:
            issues.append({"field": field, "error_code": "forbidden_field", "message": f"{field} kullanılamaz"})

    return issues


def _runtime_compatibility_check(config_json: dict) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    base_size = _safe_float(config_json.get("base_size"), 0.0)
    if base_size <= 0:
        errors.append(
            {
                "field": "base_size",
                "error_code": "compatibility_base_size_invalid",
                "message": "base_size runtime için sıfırdan büyük olmalı",
            }
        )

    threshold = _safe_float(config_json.get("momentum_threshold"), -1)
    if threshold <= 0:
        errors.append(
            {
                "field": "momentum_threshold",
                "error_code": "compatibility_threshold_invalid",
                "message": "momentum_threshold runtime için sıfırdan büyük olmalı",
            }
        )

    volatility_guard = _safe_float(config_json.get("volatility_guard"), -1)
    if volatility_guard <= 0:
        errors.append(
            {
                "field": "volatility_guard",
                "error_code": "compatibility_volatility_guard_invalid",
                "message": "volatility_guard runtime için sıfırdan büyük olmalı",
            }
        )

    return {
        "compatible": len(errors) == 0,
        "errors": errors,
        "checked_at": _now_utc().isoformat(),
    }


def create_strategy_definition(
    db: Session,
    *,
    name: str,
    code: str,
    description: str,
    created_by: str,
    owner_user_id: str | None,
    owner_name: str | None,
    category: str,
    tags: list[str] | None,
) -> StrategyDefinition:
    normalized_code = code.strip().lower()
    existing = db.query(StrategyDefinition).filter(StrategyDefinition.code == normalized_code).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_code_exists")

    row = StrategyDefinition(
        strategy_id=str(uuid.uuid4()),
        name=name.strip(),
        code=normalized_code,
        description=description.strip(),
        owner_type="admin",
        owner_user_id=owner_user_id or created_by,
        owner_name=str(owner_name or "ops").strip() or "ops",
        category=str(category or "general").strip().lower() or "general",
        tags=[str(item).strip().lower() for item in (tags or []) if str(item).strip()],
        created_by=created_by,
        status="draft",
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _strategy_cache[row.strategy_id] = (time.time(), row.strategy_id)
    return row


def list_strategy_definitions_filtered(
    db: Session,
    *,
    search: str | None,
    status_filter: str | None,
    lifecycle_state: str | None,
    active_only: bool,
    production_only: bool,
    validation_status: str | None,
    owner_user_id: str | None,
    owner_name: str | None,
    category: str | None,
    tag: str | None,
    sort_by: str,
    sort_order: str,
    page: int,
    page_size: int,
) -> tuple[list[StrategyDefinition], int]:
    query = db.query(StrategyDefinition)

    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                StrategyDefinition.name.ilike(pattern),
                StrategyDefinition.code.ilike(pattern),
                StrategyDefinition.description.ilike(pattern),
                StrategyDefinition.owner_name.ilike(pattern),
            )
        )
    if status_filter:
        query = query.filter(StrategyDefinition.status == status_filter)
    if owner_user_id:
        query = query.filter(StrategyDefinition.owner_user_id == owner_user_id)
    if owner_name:
        query = query.filter(StrategyDefinition.owner_name.ilike(f"%{owner_name.strip()}%"))
    if category:
        query = query.filter(StrategyDefinition.category == category)
    if tag:
        query = query.filter(StrategyDefinition.tags.contains([tag]))

    lifecycle_query = db.query(StrategyVersionLifecycle)
    if lifecycle_state:
        lifecycle_query = lifecycle_query.filter(StrategyVersionLifecycle.lifecycle_state == lifecycle_state)
    if active_only:
        lifecycle_query = lifecycle_query.filter(StrategyVersionLifecycle.is_active.is_(True))
    if production_only:
        lifecycle_query = lifecycle_query.filter(StrategyVersionLifecycle.is_production.is_(True))
    if validation_status:
        lifecycle_query = lifecycle_query.filter(StrategyVersionLifecycle.validation_status == validation_status)

    if lifecycle_state or active_only or production_only or validation_status:
        strategy_ids = [item.strategy_id for item in lifecycle_query.all()]
        if len(strategy_ids) == 0:
            return [], 0
        query = query.filter(StrategyDefinition.strategy_id.in_(strategy_ids))

    total = query.count()

    sort_map = {
        "name": StrategyDefinition.name,
        "code": StrategyDefinition.code,
        "status": StrategyDefinition.status,
        "updated_at": StrategyDefinition.updated_at,
        "created_at": StrategyDefinition.created_at,
        "owner_name": StrategyDefinition.owner_name,
        "category": StrategyDefinition.category,
    }
    sort_column = sort_map.get(str(sort_by or "updated_at"), StrategyDefinition.updated_at)
    order_fn = asc if str(sort_order or "desc").lower() == "asc" else desc

    rows = (
        query.order_by(order_fn(sort_column))
        .offset(max(page - 1, 0) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def create_strategy_version(
    db: Session,
    *,
    strategy_id: str,
    config_json: dict,
    config_schema_version: str,
    created_by: str,
) -> StrategyVersion:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    schema = get_strategy_config_schema(strategy.code)
    validation_issues = _validate_config_by_schema(config_json or {}, schema)
    compatibility = _runtime_compatibility_check(config_json or {})
    compatibility_issues = compatibility.get("errors") or []
    if validation_issues or compatibility_issues:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "strategy_config_validation_failed",
                "issues": validation_issues + compatibility_issues,
            },
        )

    latest = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
        .first()
    )

    if latest is not None:
        same_config = canonical_json(latest.config_json or {}) == canonical_json(config_json or {})
        same_schema = str(latest.config_schema_version) == str(config_schema_version)
        if same_config and same_schema:
            _version_cache[latest.version_id] = (time.time(), latest.version_id)
            return latest

    next_version = (latest.version_number + 1) if latest else 1
    version_hash = build_version_hash(
        config_json=config_json,
        strategy_id=strategy_id,
        version_number=next_version,
        config_schema_version=config_schema_version,
    )

    existing_same_hash = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id, StrategyVersion.version_hash == version_hash)
        .first()
    )
    if existing_same_hash is not None:
        _version_cache[existing_same_hash.version_id] = (time.time(), existing_same_hash.version_id)
        return existing_same_hash

    row = StrategyVersion(
        version_id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        version_number=next_version,
        config_json=config_json,
        config_schema_version=config_schema_version,
        created_by=created_by,
        created_at=_now_utc(),
        version_hash=version_hash,
    )
    db.add(row)
    _ensure_version_lifecycle(
        db,
        strategy_id=strategy_id,
        strategy_version_id=row.version_id,
        created_by=created_by,
        lifecycle_state=_LIFECYCLE_VALIDATED,
    )
    lifecycle = get_version_lifecycle(db, row.version_id)
    if lifecycle is not None:
        lifecycle.validation_status = _VALIDATION_PASS
        lifecycle.validation_errors_json = []
        lifecycle.compatibility_status = _VALIDATION_PASS
        lifecycle.compatibility_report_json = compatibility
        lifecycle.updated_at = _now_utc()
    db.commit()
    db.refresh(row)
    _version_cache[row.version_id] = (time.time(), row.version_id)
    return row


def activate_strategy_version(db: Session, *, strategy_id: str, version_id: str) -> StrategyDefinition:
    strategy = _get_strategy_for_update(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")
    if str(strategy.status or "").lower() == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_archived_cannot_activate")

    version = get_version(db, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    lifecycle = get_version_lifecycle(db, version_id)
    if lifecycle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_version_lifecycle_missing")
    if str(lifecycle.lifecycle_state or "").lower() == _LIFECYCLE_ARCHIVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="stale_version_cannot_activate")
    if lifecycle.validation_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="validation_required_before_activation")
    if lifecycle.compatibility_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="compatibility_required_before_activation")

    strategy.active_version_id = version_id
    strategy.status = "active"
    strategy.updated_at = _now_utc()
    _ensure_single_active_lifecycle(db, strategy_id=strategy_id, target_version_id=version_id)
    if lifecycle.lifecycle_state == _LIFECYCLE_DRAFT:
        lifecycle.lifecycle_state = _LIFECYCLE_VALIDATED
    lifecycle.updated_at = _now_utc()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="concurrent_activation_conflict") from exc
    db.refresh(strategy)
    _strategy_cache[strategy.strategy_id] = (time.time(), strategy.strategy_id)
    return strategy


def archive_strategy(db: Session, *, strategy_id: str) -> StrategyDefinition:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    strategy.status = "archived"
    strategy.archived_at = _now_utc()
    strategy.updated_at = _now_utc()
    db.query(StrategyVersionLifecycle).filter(StrategyVersionLifecycle.strategy_id == strategy_id).update(
        {"is_active": False, "lifecycle_state": _LIFECYCLE_ARCHIVED},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(strategy)
    _strategy_cache[strategy.strategy_id] = (time.time(), strategy.strategy_id)
    return strategy


def create_strategy_regime_binding(
    db: Session,
    *,
    strategy_version_id: str,
    allowed_regimes: list[str],
    blocked_regimes: list[str],
    priority: int,
    gating_policy_version: str,
    created_by: str,
) -> StrategyRegimeBinding:
    version = get_version(db, strategy_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    row = StrategyRegimeBinding(
        binding_id=str(uuid.uuid4()),
        strategy_version_id=strategy_version_id,
        allowed_regimes=sorted(set(allowed_regimes)),
        blocked_regimes=sorted(set(blocked_regimes)),
        priority=priority,
        gating_policy_version=gating_policy_version,
        created_by=created_by,
        created_at=_now_utc(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest_regime_binding(db: Session, strategy_version_id: str) -> StrategyRegimeBinding | None:
    return (
        db.query(StrategyRegimeBinding)
        .filter(StrategyRegimeBinding.strategy_version_id == strategy_version_id)
        .order_by(StrategyRegimeBinding.priority.asc(), StrategyRegimeBinding.created_at.desc())
        .first()
    )


def get_strategy_regime_bindings(db: Session, strategy_version_id: str) -> list[StrategyRegimeBinding]:
    return (
        db.query(StrategyRegimeBinding)
        .filter(StrategyRegimeBinding.strategy_version_id == strategy_version_id)
        .order_by(StrategyRegimeBinding.priority.asc(), StrategyRegimeBinding.created_at.desc())
        .all()
    )


def get_strategy_regime_overview(db: Session, strategy_id: str, *, limit: int = 30) -> dict:
    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
        .all()
    )
    version_ids = [item.version_id for item in versions]

    if version_ids:
        bindings = (
            db.query(StrategyRegimeBinding)
            .filter(StrategyRegimeBinding.strategy_version_id.in_(version_ids))
            .order_by(StrategyRegimeBinding.created_at.desc())
            .all()
        )
        snapshots = (
            db.query(RegimeSnapshot)
            .filter(RegimeSnapshot.strategy_version_id.in_(version_ids))
            .order_by(RegimeSnapshot.created_at.desc())
            .limit(limit)
            .all()
        )
    else:
        bindings = []
        snapshots = []

    reject_logs = (
        db.query(AuditLog)
        .filter(AuditLog.action == "strategy_regime_gated_reject")
        .order_by(AuditLog.created_at.desc())
        .limit(limit * 5)
        .all()
    )
    reject_distribution: dict[str, int] = {}
    for log in reject_logs:
        details = log.details or {}
        if details.get("strategy_id") != strategy_id:
            continue
        reason = details.get("reason_code", "regime_not_allowed")
        reject_distribution[reason] = reject_distribution.get(reason, 0) + 1

    return {
        "bindings": bindings,
        "snapshots": snapshots,
        "reject_distribution": reject_distribution,
    }


def validate_strategy_version_config(db: Session, *, strategy_id: str, version_id: str, actor_user_id: str) -> dict[str, Any]:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    version = get_version(db, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    lifecycle = _ensure_version_lifecycle(
        db,
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        created_by=actor_user_id,
    )

    schema = get_strategy_config_schema(strategy.code)
    validation_issues = _validate_config_by_schema(version.config_json or {}, schema)
    compatibility = _runtime_compatibility_check(version.config_json or {})

    lifecycle.validation_status = _VALIDATION_PASS if len(validation_issues) == 0 else _VALIDATION_FAIL
    lifecycle.validation_errors_json = validation_issues
    lifecycle.compatibility_status = _VALIDATION_PASS if bool(compatibility.get("compatible")) else _VALIDATION_FAIL
    lifecycle.compatibility_report_json = compatibility
    if lifecycle.validation_status == _VALIDATION_PASS and lifecycle.compatibility_status == _VALIDATION_PASS:
        lifecycle.lifecycle_state = _LIFECYCLE_VALIDATED
    else:
        lifecycle.lifecycle_state = _LIFECYCLE_DRAFT
    lifecycle.updated_at = _now_utc()

    db.commit()
    db.refresh(lifecycle)

    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "validation_status": lifecycle.validation_status,
        "compatibility_status": lifecycle.compatibility_status,
        "lifecycle_state": lifecycle.lifecycle_state,
        "issues": validation_issues,
        "compatibility_report": compatibility,
    }


def evaluate_strategy_context_standard(*, strategy_version: StrategyVersion, context_payload: dict) -> dict[str, Any]:
    config = strategy_version.config_json or {}
    features = (context_payload or {}).get("input_features") or {}
    risk_state = (context_payload or {}).get("risk_state") or {}

    momentum_threshold = max(0.000001, _safe_float(config.get("momentum_threshold"), 0.1))
    neutral_threshold = _safe_float(config.get("neutral_threshold"), max(0.01, momentum_threshold * 0.2))
    base_size = max(0.0, _safe_float(config.get("base_size"), 0.001))
    volatility_guard = max(0.000001, _safe_float(config.get("volatility_guard"), 1.0))

    momentum = _safe_float(features.get("momentum"), 0.0)
    volatility = max(0.0, _safe_float(features.get("volatility"), 0.0))
    blocked = bool(risk_state.get("blocked", False))

    reason_codes: list[str] = []
    if blocked:
        action = "REJECT"
        reason_codes.append("risk_gate_blocked")
    elif volatility > volatility_guard:
        action = "REJECT"
        reason_codes.append("volatility_guard_breach")
    elif momentum >= momentum_threshold:
        action = "BUY"
        reason_codes.append("momentum_above_threshold")
    elif momentum <= -momentum_threshold:
        action = "SELL"
        reason_codes.append("momentum_below_threshold")
    elif abs(momentum) <= neutral_threshold:
        action = "HOLD"
        reason_codes.append("momentum_neutral")
    else:
        action = "CLOSE"
        reason_codes.append("momentum_decay")

    confidence = 0.0 if action == "REJECT" else round(min(1.0, abs(momentum) / momentum_threshold), 6)
    risk_score = 1.0 if action == "REJECT" else round(min(1.0, volatility), 6)
    size = round(base_size if action in {"BUY", "SELL"} else 0.0, 8)
    result = "BLOCK" if action == "REJECT" else "PASS"
    score = round(max(0.0, min(100.0, confidence * (1.0 - risk_score) * 100)), 3)

    context_hash = build_context_hash(context_payload or {})
    decision_basis = {
        "result": result,
        "score": score,
        "reason_codes": reason_codes,
        "action": action,
        "size": size,
        "confidence": confidence,
        "risk_score": risk_score,
        "strategy_version_id": strategy_version.version_id,
        "strategy_version_hash": strategy_version.version_hash,
        "context_hash": context_hash,
    }
    decision_hash = build_decision_hash(decision_basis)

    return {
        "result": result,
        "score": score,
        "reason_codes": reason_codes,
        "decision_hash": decision_hash,
        "context_hash": context_hash,
        "decision": {
            "action": action,
            "size": size,
            "confidence": confidence,
            "risk_score": risk_score,
            "strategy_version_id": strategy_version.version_id,
        },
        "decision_trace": {
            "input_features": features,
            "risk_state": risk_state,
            "applied_config": {
                "momentum_threshold": momentum_threshold,
                "neutral_threshold": neutral_threshold,
                "base_size": base_size,
                "volatility_guard": volatility_guard,
            },
            "strategy_version_hash": strategy_version.version_hash,
        },
    }


def run_strategy_version_dry_run(
    db: Session,
    *,
    strategy_id: str,
    version_id: str,
    actor_user_id: str,
    context_payload: dict | None = None,
) -> dict[str, Any]:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    version = get_version(db, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    lifecycle = _ensure_version_lifecycle(
        db,
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        created_by=actor_user_id,
    )
    if lifecycle.validation_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="validation_required_before_dry_run")
    if lifecycle.compatibility_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="compatibility_required_before_dry_run")

    runtime_context = context_payload or {
        "context_id": f"dry-run-{uuid.uuid4().hex[:8]}",
        "timestamp_utc": _now_utc().isoformat(),
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "market_snapshot": {"last_price": 100000.0, "bid": 99995.0, "ask": 100005.0},
        "market_snapshot_hash": "dry-run-snapshot",
        "position_state": {"side": "flat", "qty": 0},
        "risk_state": {"blocked": False},
        "account_state_projection": {"equity": 1000, "free_margin": 900},
        "strategy_version_id": version.version_id,
        "strategy_version_hash": version.version_hash,
        "input_features": {"momentum": 0.12, "volatility": 0.2, "base_size": 0.001},
        "correlation_id": f"dry-run-corr-{uuid.uuid4().hex[:8]}",
    }

    dry_run_result = evaluate_strategy_context_standard(strategy_version=version, context_payload=runtime_context)
    is_passed = str(dry_run_result.get("result") or "BLOCK").upper() == "PASS"

    lifecycle.dry_run_status = _VALIDATION_PASS if is_passed else _VALIDATION_FAIL
    lifecycle.dry_run_report_json = {
        "context": runtime_context,
        "output": dry_run_result,
        "dry_run_at": _now_utc().isoformat(),
    }
    if is_passed:
        lifecycle.lifecycle_state = _LIFECYCLE_DRY_RUN_PASSED
    lifecycle.updated_at = _now_utc()
    db.commit()
    db.refresh(lifecycle)

    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "dry_run_status": lifecycle.dry_run_status,
        "lifecycle_state": lifecycle.lifecycle_state,
        "report": lifecycle.dry_run_report_json,
    }


def rollback_strategy_version(
    db: Session,
    *,
    strategy_id: str,
    target_version_id: str,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    strategy = _get_strategy_for_update(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    target = get_version(db, target_version_id)
    if target is None or target.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    previous_active_id = strategy.active_version_id
    target_lifecycle = _ensure_version_lifecycle(
        db,
        strategy_id=strategy_id,
        strategy_version_id=target_version_id,
        created_by=actor_user_id,
    )
    if target_lifecycle.validation_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rollback_target_not_validated")
    if target_lifecycle.compatibility_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rollback_target_not_compatible")

    strategy.active_version_id = target_version_id
    strategy.status = "active"
    strategy.updated_at = _now_utc()
    _ensure_single_active_lifecycle(db, strategy_id=strategy_id, target_version_id=target_version_id)

    if previous_active_id:
        prev_lifecycle = get_version_lifecycle(db, previous_active_id)
        if prev_lifecycle is not None:
            prev_lifecycle.lifecycle_state = _LIFECYCLE_ROLLED_BACK
            prev_lifecycle.updated_at = _now_utc()

    target_lifecycle.rolled_back_from_version_id = previous_active_id
    if target_lifecycle.lifecycle_state in {_LIFECYCLE_DRAFT, _LIFECYCLE_ROLLED_BACK}:
        target_lifecycle.lifecycle_state = _LIFECYCLE_VALIDATED
    target_lifecycle.updated_at = _now_utc()

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="concurrent_rollback_conflict") from exc
    db.refresh(strategy)
    _strategy_cache[strategy.strategy_id] = (time.time(), strategy.strategy_id)

    return {
        "strategy": strategy,
        "previous_active_version_id": previous_active_id,
        "current_active_version_id": strategy.active_version_id,
        "reason": reason,
    }


def get_strategy_version_diff(
    db: Session,
    *,
    strategy_id: str,
    from_version_id: str,
    to_version_id: str,
) -> dict[str, Any]:
    from_version = get_version(db, from_version_id)
    to_version = get_version(db, to_version_id)
    if from_version is None or from_version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="from_version_not_found")
    if to_version is None or to_version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="to_version_not_found")

    from_flat = _flatten_payload(from_version.config_json or {})
    to_flat = _flatten_payload(to_version.config_json or {})
    all_keys = sorted(set(from_flat.keys()) | set(to_flat.keys()))
    differences: list[dict[str, Any]] = []
    for key in all_keys:
        left = from_flat.get(key)
        right = to_flat.get(key)
        if left != right:
            differences.append({"field": key, "from": left, "to": right})

    return {
        "strategy_id": strategy_id,
        "from_version_id": from_version_id,
        "to_version_id": to_version_id,
        "from_version_number": from_version.version_number,
        "to_version_number": to_version.version_number,
        "difference_count": len(differences),
        "differences": differences,
    }


def replay_strategy_context(db: Session, *, strategy_version_id: str, context_snapshot: dict) -> dict[str, Any]:
    version = get_version(db, strategy_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    first = evaluate_strategy_context_standard(strategy_version=version, context_payload=context_snapshot)
    second = evaluate_strategy_context_standard(strategy_version=version, context_payload=context_snapshot)
    return {
        "strategy_version_id": strategy_version_id,
        "context_snapshot": context_snapshot,
        "output": first,
        "deterministic": first.get("decision_hash") == second.get("decision_hash"),
        "decision_hash_recheck": second.get("decision_hash"),
    }


def compare_strategy_versions(
    db: Session,
    *,
    version_a_id: str,
    version_b_id: str,
    context_snapshot: dict,
) -> dict[str, Any]:
    version_a = get_version(db, version_a_id)
    version_b = get_version(db, version_b_id)
    if version_a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version_a_not_found")
    if version_b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version_b_not_found")
    if version_a.strategy_id != version_b.strategy_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version_strategy_mismatch")

    result_a = evaluate_strategy_context_standard(strategy_version=version_a, context_payload=context_snapshot)
    result_b = evaluate_strategy_context_standard(strategy_version=version_b, context_payload=context_snapshot)

    reasons_a = set(result_a.get("reason_codes") or [])
    reasons_b = set(result_b.get("reason_codes") or [])
    return {
        "strategy_id": version_a.strategy_id,
        "version_a_id": version_a_id,
        "version_b_id": version_b_id,
        "context_hash": result_a.get("context_hash"),
        "result_a": result_a,
        "result_b": result_b,
        "output_diff": {
            "result_changed": result_a.get("result") != result_b.get("result"),
            "action_changed": (result_a.get("decision") or {}).get("action") != (result_b.get("decision") or {}).get("action"),
            "score_delta": round(float(result_b.get("score") or 0.0) - float(result_a.get("score") or 0.0), 6),
            "added_reason_codes": sorted(list(reasons_b - reasons_a)),
            "removed_reason_codes": sorted(list(reasons_a - reasons_b)),
        },
    }


def get_strategy_timeline(db: Session, *, strategy_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(max(limit * 5, 200)).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        details = row.details or {}
        if row.entity_id != strategy_id and details.get("strategy_id") != strategy_id:
            continue
        items.append(
            {
                "audit_id": row.id,
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "action": row.action,
                "severity": row.severity,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "details": details,
            }
        )
        if len(items) >= limit:
            break
    return items


def set_strategy_rollout_stage(
    db: Session,
    *,
    strategy_id: str,
    strategy_version_id: str,
    rollout_stage: str | None,
) -> StrategyVersionLifecycle:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    version = get_version(db, strategy_version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    lifecycle = get_version_lifecycle(db, strategy_version_id)
    if lifecycle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_version_lifecycle_missing")

    stage = str(rollout_stage or "").strip().lower() or None
    if stage is not None and stage not in _ALLOWED_ROLLOUT_STAGES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_rollout_stage")
    if stage is not None and lifecycle.dry_run_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dry_run_required_before_stage")

    lifecycle.rollout_stage = stage
    if stage == _LIFECYCLE_SHADOW:
        lifecycle.lifecycle_state = _LIFECYCLE_SHADOW
    elif stage == _LIFECYCLE_CANARY:
        lifecycle.lifecycle_state = _LIFECYCLE_CANARY
    elif lifecycle.lifecycle_state in {_LIFECYCLE_SHADOW, _LIFECYCLE_CANARY}:
        lifecycle.lifecycle_state = _LIFECYCLE_DRY_RUN_PASSED
    lifecycle.updated_at = _now_utc()

    db.commit()
    db.refresh(lifecycle)
    return lifecycle


def create_strategy_promotion_request(
    db: Session,
    *,
    strategy_id: str,
    strategy_version_id: str,
    requested_by: str,
    requested_role: str,
    request_note: str,
    require_validation: bool,
    require_dry_run: bool,
    requested_stage: str | None,
) -> StrategyPromotionRequest:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")
    if str(strategy.status or "").lower() == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_archived_cannot_promote")

    version = get_version(db, strategy_version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    lifecycle = get_version_lifecycle(db, strategy_version_id)
    if lifecycle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_version_lifecycle_missing")
    if require_validation and lifecycle.validation_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="validation_required_before_promote")
    if require_dry_run and lifecycle.dry_run_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dry_run_required_before_promote")

    request = StrategyPromotionRequest(
        request_id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        requested_by=requested_by,
        requested_role=requested_role,
        status=_PROMOTION_PENDING,
        request_note=str(request_note or "").strip(),
        approval_note="",
        require_validation=bool(require_validation),
        require_dry_run=bool(require_dry_run),
        requested_stage=str(requested_stage or "").strip().lower() or None,
        created_at=_now_utc(),
        expires_at=_now_utc() + timedelta(hours=24),
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def _expire_promotion_requests(db: Session) -> None:
    now_ts = _now_utc()
    db.query(StrategyPromotionRequest).filter(
        StrategyPromotionRequest.status == _PROMOTION_PENDING,
        StrategyPromotionRequest.expires_at < now_ts,
    ).update({"status": _PROMOTION_EXPIRED, "reviewed_at": now_ts}, synchronize_session=False)
    db.flush()


def list_strategy_promotion_requests(
    db: Session,
    *,
    strategy_id: str | None = None,
    status_filter: str | None = None,
    requester_user_id: str | None = None,
    is_super_admin: bool = False,
    limit: int = 100,
) -> list[StrategyPromotionRequest]:
    _expire_promotion_requests(db)
    query = db.query(StrategyPromotionRequest)
    if strategy_id:
        query = query.filter(StrategyPromotionRequest.strategy_id == strategy_id)
    if status_filter:
        query = query.filter(StrategyPromotionRequest.status == str(status_filter).strip().lower())
    if requester_user_id and not is_super_admin:
        query = query.filter(StrategyPromotionRequest.requested_by == requester_user_id)
    return query.order_by(StrategyPromotionRequest.created_at.desc()).limit(limit).all()


def approve_strategy_promotion_request(
    db: Session,
    *,
    request_id: str,
    approved_by_user_id: str,
    approval_note: str,
) -> StrategyPromotionRequest:
    _expire_promotion_requests(db)
    request = (
        db.query(StrategyPromotionRequest)
        .filter(StrategyPromotionRequest.request_id == request_id)
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="promotion_request_not_found")
    if request.status != _PROMOTION_PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="promotion_request_not_pending")

    lifecycle = get_version_lifecycle(db, request.strategy_version_id)
    if lifecycle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_version_lifecycle_missing")
    if bool(request.require_validation) and lifecycle.validation_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="validation_required_before_promote")
    if bool(request.require_dry_run) and lifecycle.dry_run_status != _VALIDATION_PASS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dry_run_required_before_promote")

    strategy = _get_strategy_for_update(db, request.strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")
    strategy.active_version_id = request.strategy_version_id
    strategy.status = "active"
    strategy.updated_at = _now_utc()

    _ensure_single_active_lifecycle(db, strategy_id=request.strategy_id, target_version_id=request.strategy_version_id)
    _ensure_single_production_lifecycle(db, strategy_id=request.strategy_id, target_version_id=request.strategy_version_id)

    lifecycle.lifecycle_state = _LIFECYCLE_PRODUCTION
    lifecycle.promoted_at = _now_utc()
    lifecycle.updated_at = _now_utc()
    if request.requested_stage in _ALLOWED_ROLLOUT_STAGES:
        lifecycle.rollout_stage = request.requested_stage

    request.status = _PROMOTION_APPROVED
    request.approved_by = approved_by_user_id
    request.approval_note = str(approval_note or "").strip()
    request.reviewed_at = _now_utc()

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="promotion_activation_conflict") from exc
    db.refresh(request)
    return request


def reject_strategy_promotion_request(
    db: Session,
    *,
    request_id: str,
    rejected_by_user_id: str,
    rejection_note: str,
) -> StrategyPromotionRequest:
    _expire_promotion_requests(db)
    request = (
        db.query(StrategyPromotionRequest)
        .filter(StrategyPromotionRequest.request_id == request_id)
        .first()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="promotion_request_not_found")
    if request.status != _PROMOTION_PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="promotion_request_not_pending")

    request.status = _PROMOTION_REJECTED
    request.rejected_by = rejected_by_user_id
    request.approval_note = str(rejection_note or "").strip()
    request.reviewed_at = _now_utc()
    db.commit()
    db.refresh(request)
    return request


def resolve_strategy_binding_preview(
    db: Session,
    *,
    strategy_id: str | None,
    strategy_version_id: str | None,
    regime_label: str,
) -> dict[str, Any]:
    resolved_strategy_id = strategy_id
    resolved_version_id = strategy_version_id

    if resolved_version_id:
        version = get_version(db, resolved_version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")
        resolved_strategy_id = version.strategy_id
    elif resolved_strategy_id:
        strategy = get_strategy(db, resolved_strategy_id)
        if strategy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")
        resolved_version_id = strategy.active_version_id
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_id_or_strategy_version_id_required")

    if not resolved_version_id:
        return {
            "strategy_id": resolved_strategy_id,
            "strategy_version_id": None,
            "regime_label": regime_label,
            "winner_binding_id": None,
            "winner_priority": None,
            "has_conflict": False,
            "candidates": [],
        }

    bindings = get_strategy_regime_bindings(db, resolved_version_id)
    normalized_regime = str(regime_label or "").strip().lower()

    candidates: list[dict[str, Any]] = []
    for binding in bindings:
        allowed = [str(item).strip().lower() for item in (binding.allowed_regimes or []) if str(item).strip()]
        blocked = [str(item).strip().lower() for item in (binding.blocked_regimes or []) if str(item).strip()]
        allowed_ok = len(allowed) == 0 or normalized_regime in allowed
        blocked_hit = normalized_regime in blocked
        is_candidate = allowed_ok and not blocked_hit
        candidates.append(
            {
                "binding_id": binding.binding_id,
                "priority": binding.priority,
                "allowed_regimes": binding.allowed_regimes,
                "blocked_regimes": binding.blocked_regimes,
                "created_at": binding.created_at.isoformat() if binding.created_at else None,
                "is_candidate": is_candidate,
                "blocked": blocked_hit,
            }
        )

    filtered = [item for item in candidates if bool(item.get("is_candidate"))]
    filtered = sorted(filtered, key=lambda item: (int(item.get("priority") or 0), str(item.get("created_at") or "")))
    winner = filtered[0] if filtered else None

    return {
        "strategy_id": resolved_strategy_id,
        "strategy_version_id": resolved_version_id,
        "regime_label": normalized_regime,
        "winner_binding_id": winner.get("binding_id") if winner else None,
        "winner_priority": winner.get("priority") if winner else None,
        "has_conflict": len(filtered) > 1,
        "candidates": filtered,
    }


def generate_strategy_execution_preview(
    db: Session,
    *,
    strategy_id: str,
    version_id: str,
    context_payload: dict,
) -> dict[str, Any]:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    version = get_version(db, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    decision = evaluate_strategy_context_standard(strategy_version=version, context_payload=context_payload)
    decision_view = decision.get("decision") or {}
    action = str(decision_view.get("action") or "REJECT").upper()
    symbol = str(context_payload.get("symbol") or "").upper()
    mark_price = _safe_float(((context_payload.get("market_snapshot") or {}).get("last_price")), 0.0)
    quantity = _safe_float(decision_view.get("size"), 0.0)
    notional = round(quantity * mark_price, 6)

    legacy_decision = {
        "action": action,
        "size": quantity,
        "price_reference": {"mark_price": mark_price},
        "reason_codes": decision.get("reason_codes") or [],
        "strategy_version_id": version_id,
        "context_hash": decision.get("context_hash"),
        "decision_hash": decision.get("decision_hash"),
    }
    execution_intent = map_decision_to_intent(
        strategy_id=strategy_id,
        correlation_id=str(context_payload.get("correlation_id") or f"preview-{uuid.uuid4().hex[:8]}"),
        decision_result=legacy_decision,
        context_payload=context_payload,
    )

    account_projection = context_payload.get("account_state_projection") or {}
    equity = max(_safe_float(account_projection.get("equity"), 0.0), 0.0)
    allocation_pct = round((notional / equity) * 100, 4) if equity > 0 else 0.0

    risk_checks = [
        {
            "check": "volatility_guard",
            "status": "PASS" if "volatility_guard_breach" not in (decision.get("reason_codes") or []) else "BLOCK",
            "detail": (decision.get("decision_trace") or {}).get("applied_config", {}).get("volatility_guard"),
        },
        {
            "check": "risk_gate",
            "status": "PASS" if "risk_gate_blocked" not in (decision.get("reason_codes") or []) else "BLOCK",
            "detail": (context_payload.get("risk_state") or {}).get("blocked"),
        },
        {
            "check": "capital_allocation",
            "status": "PASS" if allocation_pct <= 100 else "BLOCK",
            "detail": {"allocation_pct": allocation_pct},
        },
    ]

    blocked_reasons = (decision.get("reason_codes") or []) if decision.get("result") == "BLOCK" else []
    order_preview = (
        {
            "symbol": symbol,
            "side": action,
            "order_type": "MARKET",
            "quantity": quantity,
            "mark_price": mark_price,
            "estimated_notional": notional,
            "time_in_force": "IOC",
        }
        if execution_intent is not None
        else None
    )

    return {
        "decision": decision,
        "execution_intent": execution_intent,
        "order_preview": order_preview,
        "capital_impact": {
            "equity": equity,
            "estimated_notional": notional,
            "allocation_pct": allocation_pct,
            "free_margin": _safe_float(account_projection.get("free_margin"), 0.0),
        },
        "risk_checks": risk_checks,
        "blocked_reasons": blocked_reasons,
        "explainability_trace": {
            "strategy_id": strategy_id,
            "strategy_version_id": version_id,
            "decision_trace": decision.get("decision_trace") or {},
            "selection": {
                "selected_action": action,
                "signal": (decision.get("reason_codes") or [None])[0],
            },
        },
    }


def get_strategy_version_metrics(db: Session, *, strategy_id: str, version_id: str) -> dict[str, Any]:
    observability_rows = (
        db.query(StrategyObservabilityEvent)
        .filter(
            StrategyObservabilityEvent.strategy_id == strategy_id,
            StrategyObservabilityEvent.strategy_version_id == version_id,
        )
        .order_by(StrategyObservabilityEvent.created_at.desc())
        .limit(500)
        .all()
    )
    intent_rows = (
        db.query(ExecutionIntent)
        .filter(
            ExecutionIntent.strategy_id == strategy_id,
            ExecutionIntent.strategy_version_id == version_id,
        )
        .order_by(ExecutionIntent.created_at.desc())
        .limit(500)
        .all()
    )
    perf_snapshot = (
        db.query(CanonicalStrategyRegistry)
        .filter(CanonicalStrategyRegistry.strategy_id == strategy_id)
        .order_by(CanonicalStrategyRegistry.updated_at.desc())
        .first()
    )

    total_obs = len(observability_rows)
    passes = len([row for row in observability_rows if bool(row.hard_gate_pass) and bool(row.threshold_pass)])
    rejects = len([row for row in observability_rows if str(row.event_type or "").lower().endswith("rejected") or bool(row.rejection_reason)])
    drift_alerts = len(
        [
            row
            for row in observability_rows
            if "drift" in str(row.event_type or "").lower() or "drift" in str(row.rejection_reason or "").lower()
        ]
    )

    total_intents = len(intent_rows)
    executed_intents = len([row for row in intent_rows if str(row.status or "").lower() in {"submitted", "approved", "executed", "done"}])
    rejected_intents = len([row for row in intent_rows if str(row.status or "").lower() in {"rejected", "blocked", "cancelled"}])

    event_rows = (
        db.query(ExecutionIntentEvent)
        .filter(ExecutionIntentEvent.intent_id.in_([row.intent_id for row in intent_rows]))
        .order_by(ExecutionIntentEvent.created_at.desc())
        .limit(1000)
        .all()
        if total_intents > 0
        else []
    )

    pnl_contribution = round(
        sum(_safe_float((event.payload or {}).get("paper_pnl"), 0.0) for event in event_rows),
        6,
    )
    slippage_values = [_safe_float((event.payload or {}).get("slippage_bps"), 0.0) for event in event_rows]
    latency_values = [_safe_float((event.payload or {}).get("latency_ms"), 0.0) for event in event_rows]

    slippage_p50 = _percentile(slippage_values, 50)
    slippage_p95 = _percentile(slippage_values, 95)
    latency_p50 = _percentile(latency_values, 50)
    latency_p95 = _percentile(latency_values, 95)

    hit_rate = round((passes / total_obs) * 100, 2) if total_obs > 0 else 0.0
    block_reject_rate = round(((rejects + rejected_intents) / max(total_obs + total_intents, 1)) * 100, 2)
    execution_quality = round((executed_intents / max(total_intents, 1)) * 100, 2) if total_intents > 0 else 0.0
    false_allow_rate = _safe_float(getattr(perf_snapshot, "false_allow_rate", 0.0), 0.0)
    false_reject_rate = _safe_float(getattr(perf_snapshot, "false_reject_rate", 0.0), 0.0)

    slippage_penalty = min(20.0, max(0.0, slippage_p95 / 5.0))
    latency_penalty = min(20.0, max(0.0, latency_p95 / 20.0))
    drift_penalty = min(20.0, float(drift_alerts) * 2.0)
    false_penalty = min(20.0, false_allow_rate + false_reject_rate)
    health_score = round(
        max(
            0.0,
            min(
                100.0,
                (hit_rate * 0.35)
                + (execution_quality * 0.35)
                + ((100.0 - block_reject_rate) * 0.1)
                + ((100.0 - false_allow_rate - false_reject_rate) * 0.2)
                - slippage_penalty
                - latency_penalty
                - drift_penalty
                - false_penalty,
            ),
        ),
        2,
    )

    quality_alerts: list[dict[str, Any]] = []

    def _append_quality_alert(*, key: str, severity: str, value: float, threshold: float, message: str) -> None:
        quality_alerts.append(
            {
                "key": key,
                "severity": severity,
                "value": round(float(value), 4),
                "threshold": round(float(threshold), 4),
                "message": message,
            }
        )

    if slippage_p95 >= 35:
        _append_quality_alert(
            key="slippage_percentile",
            severity="CRITICAL",
            value=slippage_p95,
            threshold=35,
            message="Slippage P95 kritik eşik üstünde",
        )
    elif slippage_p95 >= 20:
        _append_quality_alert(
            key="slippage_percentile",
            severity="WARNING",
            value=slippage_p95,
            threshold=20,
            message="Slippage P95 warning eşiği üstünde",
        )

    if latency_p95 >= 3000:
        _append_quality_alert(
            key="latency_percentile",
            severity="CRITICAL",
            value=latency_p95,
            threshold=3000,
            message="Latency P95 kritik eşik üstünde",
        )
    elif latency_p95 >= 1500:
        _append_quality_alert(
            key="latency_percentile",
            severity="WARNING",
            value=latency_p95,
            threshold=1500,
            message="Latency P95 warning eşiği üstünde",
        )

    if block_reject_rate >= 55:
        _append_quality_alert(
            key="reject_spike",
            severity="CRITICAL",
            value=block_reject_rate,
            threshold=55,
            message="Reject oranında spike tespit edildi",
        )
    elif block_reject_rate >= 35:
        _append_quality_alert(
            key="reject_spike",
            severity="WARNING",
            value=block_reject_rate,
            threshold=35,
            message="Reject oranı warning eşiği üstünde",
        )

    false_signal_spike = false_allow_rate + false_reject_rate
    if false_signal_spike >= 25:
        _append_quality_alert(
            key="false_signal_spike",
            severity="CRITICAL",
            value=false_signal_spike,
            threshold=25,
            message="False signal oranında kritik spike",
        )
    elif false_signal_spike >= 15:
        _append_quality_alert(
            key="false_signal_spike",
            severity="WARNING",
            value=false_signal_spike,
            threshold=15,
            message="False signal oranı warning eşiği üstünde",
        )

    quality_status = "GOOD"
    if any(item.get("severity") == "CRITICAL" for item in quality_alerts):
        quality_status = "CRITICAL"
    elif any(item.get("severity") == "WARNING" for item in quality_alerts):
        quality_status = "WARNING"

    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "sample_sizes": {
            "observability_events": total_obs,
            "execution_intents": total_intents,
            "execution_intent_events": len(event_rows),
        },
        "metrics": {
            "hit_rate": hit_rate,
            "block_reject_rate": block_reject_rate,
            "false_allow_rate": false_allow_rate,
            "false_reject_rate": false_reject_rate,
            "pnl_contribution": pnl_contribution,
            "execution_quality": execution_quality,
            "drift_alerts": drift_alerts,
            "slippage_p50_bps": slippage_p50,
            "slippage_p95_bps": slippage_p95,
            "latency_p50_ms": latency_p50,
            "latency_p95_ms": latency_p95,
            "version_health_score": health_score,
            "quality_status": quality_status,
            "quality_alerts": quality_alerts,
            "quality_correlation": {
                "slippage_to_execution_quality": round(max(0.0, execution_quality - slippage_p95), 4),
                "latency_to_execution_quality": round(max(0.0, execution_quality - (latency_p95 / 10.0)), 4),
            },
        },
    }


def get_strategy_version_metrics_timeseries(
    db: Session,
    *,
    strategy_id: str,
    version_id: str,
    points: int = 60,
) -> dict[str, Any]:
    rows = (
        db.query(StrategyObservabilityEvent)
        .filter(
            StrategyObservabilityEvent.strategy_id == strategy_id,
            StrategyObservabilityEvent.strategy_version_id == version_id,
        )
        .order_by(StrategyObservabilityEvent.created_at.asc())
        .limit(max(points, 10))
        .all()
    )

    series = []
    for row in rows:
        delta = _safe_float(row.score_delta, 0.0)
        pnl = _safe_float(row.pnl_5m, 0.0)
        rejection = 1 if bool(row.rejection_reason) else 0
        series.append(
            {
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "score_delta": delta,
                "pnl_5m": pnl,
                "rejection": rejection,
            }
        )

    score_values = [_safe_float(item.get("score_delta"), 0.0) for item in series]
    if score_values:
        mean_score = sum(score_values) / len(score_values)
        variance = sum((value - mean_score) ** 2 for value in score_values) / len(score_values)
        std_score = variance ** 0.5
    else:
        mean_score = 0.0
        std_score = 0.0
    upper_band = round(mean_score + (2 * std_score), 6)
    lower_band = round(mean_score - (2 * std_score), 6)

    trend_payload = [
        {
            **item,
            "mean_score": round(mean_score, 6),
            "anomaly_upper": upper_band,
            "anomaly_lower": lower_band,
            "is_anomaly": _safe_float(item.get("score_delta"), 0.0) > upper_band
            or _safe_float(item.get("score_delta"), 0.0) < lower_band,
        }
        for item in series
    ]

    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "trend_series": trend_payload,
        "anomaly_band": {
            "mean_score": round(mean_score, 6),
            "upper": upper_band,
            "lower": lower_band,
            "std_dev": round(std_score, 6),
        },
    }


def get_strategy_version_drift_alerts(db: Session, *, strategy_id: str, version_id: str, limit: int = 100) -> dict[str, Any]:
    rows = (
        db.query(StrategyObservabilityEvent)
        .filter(
            StrategyObservabilityEvent.strategy_id == strategy_id,
            StrategyObservabilityEvent.strategy_version_id == version_id,
        )
        .order_by(StrategyObservabilityEvent.created_at.desc())
        .limit(max(limit, 1))
        .all()
    )
    alerts = []
    for row in rows:
        event_type = str(row.event_type or "").lower()
        rejection_reason = str(row.rejection_reason or "")
        if "drift" not in event_type and "drift" not in rejection_reason.lower():
            continue
        alerts.append(
            {
                "event_id": row.id,
                "event_type": row.event_type,
                "rejection_reason": row.rejection_reason,
                "market_regime": row.market_regime,
                "score_delta": row.score_delta,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "drift_alerts": alerts,
        "count": len(alerts),
    }


def get_strategy_version_false_signal_report(db: Session, *, strategy_id: str, version_id: str) -> dict[str, Any]:
    snapshot = (
        db.query(CanonicalStrategyRegistry)
        .filter(CanonicalStrategyRegistry.strategy_id == strategy_id)
        .order_by(CanonicalStrategyRegistry.updated_at.desc())
        .first()
    )
    metrics = get_strategy_version_metrics(db, strategy_id=strategy_id, version_id=version_id)
    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "false_allow_rate": _safe_float(getattr(snapshot, "false_allow_rate", 0.0), 0.0),
        "false_reject_rate": _safe_float(getattr(snapshot, "false_reject_rate", 0.0), 0.0),
        "signal_quality_last_50": _safe_float(getattr(snapshot, "last_50_signal_quality", 0.0), 0.0),
        "execution_quality": (metrics.get("metrics") or {}).get("execution_quality", 0.0),
        "evidence": {
            "sample_sizes": metrics.get("sample_sizes") or {},
            "drift_alerts": (metrics.get("metrics") or {}).get("drift_alerts", 0),
        },
    }


def get_strategy_promotion_readiness(db: Session, *, strategy_id: str, version_id: str) -> dict[str, Any]:
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    version = get_version(db, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_version_not_found")

    lifecycle = get_version_lifecycle(db, version_id)
    if lifecycle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="strategy_version_lifecycle_missing")

    _expire_promotion_requests(db)
    pending_request = (
        db.query(StrategyPromotionRequest)
        .filter(
            StrategyPromotionRequest.strategy_id == strategy_id,
            StrategyPromotionRequest.strategy_version_id == version_id,
            StrategyPromotionRequest.status == _PROMOTION_PENDING,
        )
        .order_by(StrategyPromotionRequest.created_at.desc())
        .first()
    )
    latest_request = (
        db.query(StrategyPromotionRequest)
        .filter(
            StrategyPromotionRequest.strategy_id == strategy_id,
            StrategyPromotionRequest.strategy_version_id == version_id,
        )
        .order_by(StrategyPromotionRequest.created_at.desc())
        .first()
    )

    checks = [
        {
            "key": "validation",
            "status": lifecycle.validation_status,
            "pass": lifecycle.validation_status == _VALIDATION_PASS,
            "message": "Validation PASS olmalı",
        },
        {
            "key": "compatibility",
            "status": lifecycle.compatibility_status,
            "pass": lifecycle.compatibility_status == _VALIDATION_PASS,
            "message": "Compatibility PASS olmalı",
        },
        {
            "key": "dry_run",
            "status": lifecycle.dry_run_status,
            "pass": lifecycle.dry_run_status == _VALIDATION_PASS,
            "message": "Dry-run PASS olmalı",
        },
        {
            "key": "pending_request",
            "status": "PENDING" if pending_request else "NONE",
            "pass": pending_request is not None,
            "message": "Pending promotion request bulunmalı",
        },
    ]
    blockers = [item.get("message") for item in checks if not bool(item.get("pass"))]

    pending_payload = None
    if pending_request is not None:
        pending_payload = {
            "request_id": pending_request.request_id,
            "strategy_id": pending_request.strategy_id,
            "strategy_version_id": pending_request.strategy_version_id,
            "status": pending_request.status,
            "request_note": pending_request.request_note,
            "requested_by": pending_request.requested_by,
            "created_at": pending_request.created_at.isoformat() if pending_request.created_at else None,
            "expires_at": pending_request.expires_at.isoformat() if pending_request.expires_at else None,
        }

    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "checklist": checks,
        "pending_request": pending_payload,
        "latest_request_status": latest_request.status if latest_request else None,
        "is_production": bool(lifecycle.is_production),
        "ready_for_production": len(blockers) == 0,
        "blockers": blockers,
    }


def bulk_archive_strategies(db: Session, *, strategy_ids: list[str]) -> dict[str, Any]:
    success = []
    failed = []
    for strategy_id in strategy_ids:
        try:
            archive_strategy(db, strategy_id=strategy_id)
            success.append(strategy_id)
        except Exception as exc:
            db.rollback()
            failed.append({"strategy_id": strategy_id, "error": str(exc)})
    return {"success_count": len(success), "failed_count": len(failed), "success": success, "failed": failed}


def bulk_validate_strategies(db: Session, *, strategy_ids: list[str], actor_user_id: str) -> dict[str, Any]:
    success = []
    failed = []
    for strategy_id in strategy_ids:
        strategy = get_strategy(db, strategy_id)
        if strategy is None or strategy.active_version_id is None:
            failed.append({"strategy_id": strategy_id, "error": "active_version_missing"})
            continue
        try:
            result = validate_strategy_version_config(
                db,
                strategy_id=strategy_id,
                version_id=strategy.active_version_id,
                actor_user_id=actor_user_id,
            )
            success.append({"strategy_id": strategy_id, "result": result})
        except Exception as exc:
            db.rollback()
            failed.append({"strategy_id": strategy_id, "error": str(exc)})
    return {"success_count": len(success), "failed_count": len(failed), "success": success, "failed": failed}


def bulk_dry_run_strategies(
    db: Session,
    *,
    strategy_ids: list[str],
    actor_user_id: str,
    context_snapshot: dict | None,
) -> dict[str, Any]:
    success = []
    failed = []
    for strategy_id in strategy_ids:
        strategy = get_strategy(db, strategy_id)
        if strategy is None or strategy.active_version_id is None:
            failed.append({"strategy_id": strategy_id, "error": "active_version_missing"})
            continue
        try:
            lifecycle = get_version_lifecycle(db, strategy.active_version_id)
            if lifecycle is None or lifecycle.validation_status != _VALIDATION_PASS:
                validate_strategy_version_config(
                    db,
                    strategy_id=strategy_id,
                    version_id=strategy.active_version_id,
                    actor_user_id=actor_user_id,
                )
            result = run_strategy_version_dry_run(
                db,
                strategy_id=strategy_id,
                version_id=strategy.active_version_id,
                actor_user_id=actor_user_id,
                context_payload=context_snapshot,
            )
            success.append({"strategy_id": strategy_id, "result": result})
        except Exception as exc:
            db.rollback()
            failed.append({"strategy_id": strategy_id, "error": str(exc)})
    return {"success_count": len(success), "failed_count": len(failed), "success": success, "failed": failed}


def bulk_tag_strategies(
    db: Session,
    *,
    strategy_ids: list[str],
    category: str | None,
    tags: list[str] | None,
    owner_name: str | None,
) -> dict[str, Any]:
    rows = db.query(StrategyDefinition).filter(StrategyDefinition.strategy_id.in_(strategy_ids)).all()
    updated = []
    for row in rows:
        if category is not None:
            row.category = str(category).strip().lower() or row.category
        if tags is not None:
            row.tags = [str(item).strip().lower() for item in tags if str(item).strip()]
        if owner_name is not None:
            row.owner_name = str(owner_name).strip() or row.owner_name
        row.updated_at = _now_utc()
        updated.append(row.strategy_id)
    db.commit()
    return {"updated_count": len(updated), "updated": updated, "requested_count": len(strategy_ids)}


def export_strategy_audit_history(db: Session, *, strategy_id: str, format_type: str = "json", limit: int = 1000) -> dict[str, Any]:
    items = get_strategy_timeline(db, strategy_id=strategy_id, limit=limit)
    if str(format_type).lower() == "csv":
        headers = ["audit_id", "timestamp", "action", "severity", "actor_user_id", "actor_role", "entity_type", "entity_id"]
        rows = [
            ",".join(
                [
                    str(item.get("audit_id") or ""),
                    str(item.get("timestamp") or ""),
                    str(item.get("action") or ""),
                    str(item.get("severity") or ""),
                    str(item.get("actor_user_id") or ""),
                    str(item.get("actor_role") or ""),
                    str(item.get("entity_type") or ""),
                    str(item.get("entity_id") or ""),
                ]
            )
            for item in items
        ]
        return {"strategy_id": strategy_id, "format": "csv", "headers": headers, "rows": rows, "count": len(items)}
    return {"strategy_id": strategy_id, "format": "json", "items": items, "count": len(items)}


def get_strategy_rollback_chain(db: Session, *, strategy_id: str, limit: int = 100) -> dict[str, Any]:
    rows = (
        db.query(StrategyVersionLifecycle)
        .filter(
            StrategyVersionLifecycle.strategy_id == strategy_id,
            StrategyVersionLifecycle.rolled_back_from_version_id.isnot(None),
        )
        .order_by(StrategyVersionLifecycle.updated_at.desc())
        .limit(max(limit, 1))
        .all()
    )
    chain = [
        {
            "strategy_version_id": row.strategy_version_id,
            "rolled_back_from_version_id": row.rolled_back_from_version_id,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "lifecycle_state": row.lifecycle_state,
            "is_active": bool(row.is_active),
            "is_production": bool(row.is_production),
        }
        for row in rows
    ]
    return {"strategy_id": strategy_id, "items": chain, "count": len(chain)}


def bulk_export_audit_snapshot(
    db: Session,
    *,
    strategy_ids: list[str],
    format_type: str,
    limit_per_strategy: int,
) -> dict[str, Any]:
    items = [
        export_strategy_audit_history(
            db,
            strategy_id=strategy_id,
            format_type=format_type,
            limit=limit_per_strategy,
        )
        for strategy_id in strategy_ids
    ]
    return {
        "strategy_count": len(strategy_ids),
        "format": format_type,
        "items": items,
    }


def get_strategy_filter_options(db: Session) -> dict[str, Any]:
    rows = db.query(StrategyDefinition).all()
    owner_names = sorted({str(item.owner_name or "").strip() for item in rows if str(item.owner_name or "").strip()})
    categories = sorted({str(item.category or "").strip() for item in rows if str(item.category or "").strip()})
    tags = sorted(
        {
            str(tag).strip()
            for item in rows
            for tag in (item.tags or [])
            if str(tag).strip()
        }
    )
    return {
        "owner_names": owner_names,
        "categories": categories,
        "tags": tags,
    }

