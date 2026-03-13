from datetime import datetime, timezone

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models import StrategyFamilyGate


DEFAULT_FAMILY_GATES: dict[str, dict] = {
    "trend": {
        "is_enabled": True,
        "long_threshold": 5.0,
        "short_threshold": 5.0,
        "min_strategy_count": 1,
        "max_conflict_score": 2.0,
        "regime_match_required": True,
        "risk_clear_required": True,
        "reversal_extra_confirmation": False,
    },
    "breakout": {
        "is_enabled": True,
        "long_threshold": 4.0,
        "short_threshold": 4.0,
        "min_strategy_count": 1,
        "max_conflict_score": 2.0,
        "regime_match_required": True,
        "risk_clear_required": True,
        "reversal_extra_confirmation": False,
    },
    "pullback": {
        "is_enabled": True,
        "long_threshold": 4.0,
        "short_threshold": 4.0,
        "min_strategy_count": 1,
        "max_conflict_score": 2.0,
        "regime_match_required": True,
        "risk_clear_required": True,
        "reversal_extra_confirmation": False,
    },
    "reversal": {
        "is_enabled": True,
        "long_threshold": 3.0,
        "short_threshold": 3.0,
        "min_strategy_count": 1,
        "max_conflict_score": 1.5,
        "regime_match_required": True,
        "risk_clear_required": True,
        "reversal_extra_confirmation": True,
    },
}


def strategy_family_gate_payload(row: StrategyFamilyGate) -> dict:
    return {
        "schema_version": "sprint3.v1",
        "engine_version": "canonical-engine.v3",
        "generated_at": datetime.now(timezone.utc),
        "family": row.family,
        "is_enabled": bool(row.is_enabled),
        "long_threshold": float(row.long_threshold or 0),
        "short_threshold": float(row.short_threshold or 0),
        "min_strategy_count": int(row.min_strategy_count or 1),
        "max_conflict_score": float(row.max_conflict_score or 0),
        "regime_match_required": bool(row.regime_match_required),
        "risk_clear_required": bool(row.risk_clear_required),
        "reversal_extra_confirmation": bool(row.reversal_extra_confirmation),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _ensure_family_gate_table(db: Session):
    inspector = inspect(db.bind)
    if "strategy_family_gates" not in inspector.get_table_names():
        StrategyFamilyGate.__table__.create(bind=db.bind, checkfirst=True)


def seed_strategy_family_gates(db: Session) -> None:
    _ensure_family_gate_table(db)
    existing = {row.family: row for row in db.query(StrategyFamilyGate).all()}
    for family, config in DEFAULT_FAMILY_GATES.items():
        row = existing.get(family)
        if row is None:
            db.add(
                StrategyFamilyGate(
                    family=family,
                    is_enabled=bool(config["is_enabled"]),
                    long_threshold=float(config["long_threshold"]),
                    short_threshold=float(config["short_threshold"]),
                    min_strategy_count=int(config["min_strategy_count"]),
                    max_conflict_score=float(config["max_conflict_score"]),
                    regime_match_required=bool(config["regime_match_required"]),
                    risk_clear_required=bool(config["risk_clear_required"]),
                    reversal_extra_confirmation=bool(config["reversal_extra_confirmation"]),
                )
            )
            continue

        row.is_enabled = bool(config["is_enabled"])
        row.long_threshold = float(config["long_threshold"])
        row.short_threshold = float(config["short_threshold"])
        row.min_strategy_count = int(config["min_strategy_count"])
        row.max_conflict_score = float(config["max_conflict_score"])
        row.regime_match_required = bool(config["regime_match_required"])
        row.risk_clear_required = bool(config["risk_clear_required"])
        row.reversal_extra_confirmation = bool(config["reversal_extra_confirmation"])
        row.updated_at = datetime.now(timezone.utc)
    db.commit()


def list_strategy_family_gates(db: Session) -> list[StrategyFamilyGate]:
    _ensure_family_gate_table(db)
    rows = db.query(StrategyFamilyGate).order_by(StrategyFamilyGate.family.asc()).all()
    if not rows:
        seed_strategy_family_gates(db)
        rows = db.query(StrategyFamilyGate).order_by(StrategyFamilyGate.family.asc()).all()
    return rows


def update_strategy_family_gates(db: Session, updates: list[dict]) -> list[StrategyFamilyGate]:
    _ensure_family_gate_table(db)
    existing = {row.family: row for row in db.query(StrategyFamilyGate).all()}

    for payload in updates:
        family = str(payload.get("family") or "").strip().lower()
        if family not in DEFAULT_FAMILY_GATES:
            continue
        row = existing.get(family)
        if row is None:
            row = StrategyFamilyGate(family=family)
            db.add(row)
            existing[family] = row

        row.is_enabled = bool(payload.get("is_enabled", row.is_enabled))
        row.long_threshold = max(0.0, float(payload.get("long_threshold", row.long_threshold)))
        row.short_threshold = max(0.0, float(payload.get("short_threshold", row.short_threshold)))
        row.min_strategy_count = max(1, int(payload.get("min_strategy_count", row.min_strategy_count)))
        row.max_conflict_score = max(0.0, float(payload.get("max_conflict_score", row.max_conflict_score)))
        row.regime_match_required = bool(payload.get("regime_match_required", row.regime_match_required))
        row.risk_clear_required = bool(payload.get("risk_clear_required", row.risk_clear_required))
        row.reversal_extra_confirmation = bool(payload.get("reversal_extra_confirmation", row.reversal_extra_confirmation))
        row.updated_at = datetime.now(timezone.utc)

    db.commit()
    return list_strategy_family_gates(db)
