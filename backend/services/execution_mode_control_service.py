import json
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import LiveActivationConfig, UserExecutionIntent
from services.audit_service import create_audit_log

EXECUTION_MODE_KEY = "control_layer:execution_mode"
EXECUTION_MODE_SNAPSHOTS_KEY = "control_layer:execution_mode:snapshots"
LATENCY_THRESHOLDS_KEY = "control_layer:latency_thresholds"
DEFAULT_LATENCY_THRESHOLDS = {
    "scan_latency_ms": 1500,
    "decision_latency_ms": 900,
    "execution_latency_ms": 1600,
}

CANONICAL_MODES = {"LIVE"}
MODE_ALIAS_MAP = {
    "LIVE": "LIVE",
}


def normalize_execution_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    normalized = str(mode).strip().upper()
    return MODE_ALIAS_MAP.get(normalized)


def _decode(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def get_execution_mode(db: Session, cache) -> str:
    raw = _decode(cache.get(EXECUTION_MODE_KEY))
    if raw:
        normalized = normalize_execution_mode(raw)
        if normalized in CANONICAL_MODES:
            return normalized

    cache.set(EXECUTION_MODE_KEY, "LIVE")
    return "LIVE"


def get_latency_thresholds(cache) -> dict:
    raw = _decode(cache.get(LATENCY_THRESHOLDS_KEY))
    if not raw:
        return dict(DEFAULT_LATENCY_THRESHOLDS)
    try:
        payload = json.loads(raw)
    except Exception:
        return dict(DEFAULT_LATENCY_THRESHOLDS)

    return {
        "scan_latency_ms": float(payload.get("scan_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["scan_latency_ms"]),
        "decision_latency_ms": float(payload.get("decision_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["decision_latency_ms"]),
        "execution_latency_ms": float(payload.get("execution_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["execution_latency_ms"]),
    }


def set_latency_thresholds(cache, thresholds: dict) -> dict:
    normalized = {
        "scan_latency_ms": float(thresholds.get("scan_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["scan_latency_ms"]),
        "decision_latency_ms": float(thresholds.get("decision_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["decision_latency_ms"]),
        "execution_latency_ms": float(thresholds.get("execution_latency_ms") or DEFAULT_LATENCY_THRESHOLDS["execution_latency_ms"]),
    }
    cache.set(LATENCY_THRESHOLDS_KEY, json.dumps(normalized))
    return normalized


def infer_requested_execution_mode(intent: UserExecutionIntent) -> str:
    payload = intent.normalized_order_payload or {}
    explicit_mode = payload.get("execution_mode") or payload.get("engine_mode") or payload.get("route_mode")
    if explicit_mode:
        normalized = normalize_execution_mode(explicit_mode)
        if normalized in CANONICAL_MODES:
            return normalized

    return "LIVE"


def enforce_execution_mode_for_intent(
    db: Session,
    cache,
    intent: UserExecutionIntent,
    *,
    actor_user_id: str,
    actor_role: str,
    source: str,
) -> str:
    active_mode = get_execution_mode(db, cache)
    requested_mode = infer_requested_execution_mode(intent)

    canary_mode = str(os.getenv("CANARY_MODE", "false") or "false").strip().lower() in {"1", "true", "yes"}
    mode_enforcement_default = "0" if canary_mode else "1"
    mode_enforced = (
        str(os.getenv("EXECUTION_MODE_ENFORCEMENT_ENABLED", mode_enforcement_default) or mode_enforcement_default)
        .strip()
        .lower()
        in {"1", "true", "yes"}
    )

    if not mode_enforced:
        payload = dict(intent.normalized_order_payload or {})
        payload["execution_mode_applied"] = active_mode
        payload["execution_mode_requested"] = requested_mode
        payload["execution_mode_enforcement"] = "bypassed_canary"
        intent.normalized_order_payload = payload
        intent.queue_mode = active_mode
        return active_mode

    if active_mode != requested_mode:
        create_audit_log(
            db,
            action="EXECUTION_MODE_MISMATCH_REJECT",
            entity_type="execution_intent",
            entity_id=intent.id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="critical",
            details={
                "source": source,
                "active_mode": active_mode,
                "requested_mode": requested_mode,
                "intent_token": intent.intent_token,
            },
        )
        raise ValueError(f"execution_mode_mismatch active={active_mode} requested={requested_mode}")

    payload = dict(intent.normalized_order_payload or {})
    payload["execution_mode_applied"] = active_mode
    intent.normalized_order_payload = payload
    intent.queue_mode = active_mode
    return active_mode


def switch_execution_mode(
    db: Session,
    cache,
    *,
    mode: str,
    reason: str,
    actor_user_id: str,
    actor_role: str,
) -> dict:
    requested_mode = str(mode or "").strip().upper()
    if requested_mode != "LIVE":
        raise ValueError("live_only_mode_enforced")

    normalized_mode = normalize_execution_mode(requested_mode)
    if normalized_mode not in CANONICAL_MODES:
        raise ValueError("invalid_mode")

    previous_mode = get_execution_mode(db, cache)
    cache.set(EXECUTION_MODE_KEY, normalized_mode)

    config = db.query(LiveActivationConfig).filter(LiveActivationConfig.id == "global").first()
    if config is not None:
        config.live_mode_enabled = True
        config.safe_mode_enabled = False
        config.trading_enabled = True
        db.commit()

    kill_switch = cache.get("pipeline:kill_switch")
    if isinstance(kill_switch, bytes):
        kill_switch = kill_switch.decode("utf-8")
    fallback_state = cache.get("control_layer:fallback")
    if isinstance(fallback_state, bytes):
        fallback_state = fallback_state.decode("utf-8")

    kill_switch_payload = {}
    fallback_payload = {}
    try:
        kill_switch_payload = json.loads(kill_switch) if kill_switch else {}
    except Exception:
        kill_switch_payload = {}
    try:
        fallback_payload = json.loads(fallback_state) if fallback_state else {}
    except Exception:
        fallback_payload = {}

    snapshot_payload = {
        "mode": normalized_mode,
        "requested_mode": requested_mode,
        "compatibility_alias_used": False,
        "previous_mode": previous_mode,
        "reason": reason,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "system_health": {
            "kill_switch_active": bool(kill_switch_payload.get("active", False)),
            "fallback_active": bool(fallback_payload.get("active", False)),
            "live_mode_enabled": bool(config.live_mode_enabled) if config else normalized_mode == "LIVE",
            "safe_mode_enabled": bool(config.safe_mode_enabled) if config else False,
            "trading_enabled": bool(config.trading_enabled) if config else normalized_mode == "LIVE",
        },
        "critical_alerts": {"status": "snapshot_only", "items": []},
    }
    cache.rpush(EXECUTION_MODE_SNAPSHOTS_KEY, json.dumps(snapshot_payload))

    audit_row = create_audit_log(
        db,
        action="EXECUTION_MODE_SWITCHED",
        entity_type="execution_mode",
        entity_id="global",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        severity="warning",
        details={
            "previous_mode": previous_mode,
            "new_mode": normalized_mode,
            "requested_mode": requested_mode,
            "compatibility_alias_used": False,
            "reason": reason,
            "snapshot_captured": True,
        },
    )

    return {
        "mode": normalized_mode,
        "requested_mode": requested_mode,
        "compatibility_alias_used": False,
        "compatibility_notice": None,
        "previous_mode": previous_mode,
        "snapshot": snapshot_payload,
        "audit_log_id": audit_row.id,
    }


def read_mode_snapshots(cache, *, limit: int = 10) -> list[dict]:
    rows = cache.lrange(EXECUTION_MODE_SNAPSHOTS_KEY, max(0, -limit), -1)
    items: list[dict] = []
    for row in rows:
        raw = _decode(row)
        if not raw:
            continue
        try:
            items.append(json.loads(raw))
        except Exception:
            continue
    return items[-limit:]
