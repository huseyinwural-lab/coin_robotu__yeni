import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import PaperPosition, UserExchangeConnection
from services.connection_reliability_service import (
    deterministic_jitter_seconds,
    get_connection_reliability_policy,
)
from services.live_mode_service import adapter, validate_exchange_credentials_for_user


logger = logging.getLogger(__name__)

TRANSIENT_REASONS = {
    "exchange_unreachable",
    "network_error",
    "timeout",
    "rate_limit",
    "exchange_error_503",
}
HARD_OFFLINE_REASONS = {
    "missing_credentials",
    "invalid_key",
    "ip_restriction",
    "missing_trade_permission",
    "exchange_error_451",
}


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _seconds_since(value, *, now: datetime) -> float:
    parsed = _parse_iso(value)
    if parsed is None:
        return float("inf")
    return max(0.0, (now - parsed).total_seconds())


def _retry_schedule(snapshot: dict, *, policy: dict) -> tuple[int, int, str]:
    retry_policy = policy.get("retry") or {}
    max_retry_attempts = int(retry_policy.get("max_retry_attempts") or 8)
    initial_backoff = int(retry_policy.get("initial_backoff_seconds") or 1)
    max_backoff = int(retry_policy.get("max_backoff_seconds") or 20)
    multiplier = float(retry_policy.get("backoff_multiplier") or 2.0)

    try:
        prev_attempt = int(snapshot.get("retry_attempt") or 0)
    except (TypeError, ValueError):
        prev_attempt = 0

    next_attempt = min(prev_attempt + 1, max_retry_attempts)
    backoff_seconds = int(round(initial_backoff * (multiplier ** max(0, next_attempt - 1))))
    backoff_seconds = min(max(backoff_seconds, initial_backoff), max_backoff)
    next_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)).isoformat()
    return next_attempt, backoff_seconds, next_retry_at


def _signed_check_interval_seconds(*, environment: str, has_open_position: bool, connection_id: str) -> int:
    policy = get_connection_reliability_policy()
    health_policy = policy.get("health") or {}
    signed_policy = health_policy.get("signed_interval_seconds") or {}

    env = (environment or "").strip().lower()
    env_key = "testnet" if env == "testnet" else "live"
    env_policy = signed_policy.get(env_key) or {}
    base_interval = int(env_policy.get("open_position") or 8) if has_open_position else int(env_policy.get("idle") or 28)
    jitter_max = int(health_policy.get("signed_interval_jitter_seconds") or 0)
    jitter = deterministic_jitter_seconds(seed=connection_id or f"{env_key}-fallback", max_abs=jitter_max)
    return max(1, base_interval + jitter)


def _build_open_position_index(db: Session) -> dict[tuple[str, str], int]:
    rows = (
        db.query(PaperPosition.user_id, PaperPosition.market_type, func.count(PaperPosition.id))
        .filter(PaperPosition.status == "open")
        .group_by(PaperPosition.user_id, PaperPosition.market_type)
        .all()
    )
    return {(str(user_id), str(market_type or "spot").lower()): int(count) for user_id, market_type, count in rows}


def _run_fast_liveness_probe(row: UserExchangeConnection, snapshot: dict) -> tuple[dict, bool]:
    now = datetime.now(timezone.utc)
    policy = get_connection_reliability_policy()
    health_policy = policy.get("health") or {}
    liveness_policy = health_policy.get("liveness_interval_seconds") or {}
    transient_threshold = int(health_policy.get("transient_failures_before_reconnect") or 2)
    success_reset_threshold = int(health_policy.get("success_resets_failure_count") or 2)

    probe_snapshot = dict(snapshot)
    probe_snapshot["liveness_checked_at"] = now.isoformat()
    env_key = "testnet" if str(row.environment or "").lower() == "testnet" else "live"
    probe_snapshot["liveness_interval_seconds"] = int(liveness_policy.get(env_key) or (4 if env_key == "testnet" else 8))

    if str(row.exchange or "").strip().lower() != "binance":
        probe_snapshot["liveness_status"] = "unsupported_exchange"
        probe_snapshot["liveness_message"] = "No fast liveness probe adapter for this exchange yet."
        return probe_snapshot, False

    started = time.perf_counter()
    ping = adapter.ping()
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    reachable = str(ping.get("status") or "").lower() == "reachable"
    probe_snapshot["liveness_status"] = "reachable" if reachable else "unreachable"
    probe_snapshot["liveness_message"] = ping.get("message") or ""
    probe_snapshot["liveness_server_time"] = ping.get("server_time")
    probe_snapshot["liveness_latency_ms"] = latency_ms

    raw_latency_history = probe_snapshot.get("liveness_latency_history")
    latency_history = raw_latency_history if isinstance(raw_latency_history, list) else []
    latency_history.append(
        {
            "at": now.isoformat(),
            "latency_ms": latency_ms,
            "source": "health_loop_liveness",
        }
    )
    probe_snapshot["liveness_latency_history"] = latency_history[-300:]

    reason_codes = [str(code).strip().lower() for code in (probe_snapshot.get("reason_codes") or []) if str(code).strip()]
    primary_reason = reason_codes[0] if reason_codes else None

    if not reachable and primary_reason not in HARD_OFFLINE_REASONS:
        transient_failure_count = int(probe_snapshot.get("transient_failure_count") or 0) + 1
        probe_snapshot["transient_failure_count"] = transient_failure_count
        probe_snapshot["transient_success_count"] = 0

        if transient_failure_count < transient_threshold:
            probe_snapshot.update(
                {
                    "reason_codes": ["network_error"],
                    "last_error_reason": "network_error",
                    "is_reconnecting": False,
                    "action_required": "monitoring_transient_network",
                    "action_required_message": f"Transient liveness failure {transient_failure_count}/{transient_threshold}; reconnect bekleniyor.",
                }
            )
            return probe_snapshot, True

        retry_attempt, retry_backoff_seconds, next_retry_at = _retry_schedule(probe_snapshot, policy=policy)
        probe_snapshot.update(
            {
                "validation_success": False,
                "is_valid": False,
                "can_trade": False,
                "reason_codes": ["network_error"],
                "last_error_reason": "network_error",
                "is_reconnecting": True,
                "connection_health": "degraded",
                "retry_attempt": retry_attempt,
                "retry_backoff_seconds": retry_backoff_seconds,
                "next_retry_at": next_retry_at,
                "transient_failure_count": transient_failure_count,
            }
        )
    elif reachable:
        transient_success_count = int(probe_snapshot.get("transient_success_count") or 0) + 1
        probe_snapshot["transient_success_count"] = transient_success_count

        if transient_success_count >= success_reset_threshold:
            probe_snapshot["transient_failure_count"] = 0
            probe_snapshot["is_reconnecting"] = False
            probe_snapshot["retry_attempt"] = 0
            probe_snapshot["retry_backoff_seconds"] = 0
            probe_snapshot["next_retry_at"] = None

        if primary_reason in TRANSIENT_REASONS and int(probe_snapshot.get("transient_failure_count") or 0) > 0:
            probe_snapshot["connection_health"] = "degraded"
            probe_snapshot["is_reconnecting"] = True

    return probe_snapshot, True


def _append_health_history(
    snapshot: dict,
    *,
    health: str,
    reason: str,
    source: str,
    validation_success: bool,
    can_trade: bool,
    user_id: str | None = None,
    connection_id: str | None = None,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    raw_history = snapshot.get("health_history")
    history = raw_history if isinstance(raw_history, list) else []
    last_entry = history[-1] if history else None
    normalized_reason = (reason or "").strip().lower() or "none"

    changed = (
        not isinstance(last_entry, dict)
        or str(last_entry.get("health") or "").lower() != str(health or "").lower()
        or str(last_entry.get("reason") or "").lower() != normalized_reason
    )
    if changed:
        previous_health = str(last_entry.get("health") or "unknown").lower() if isinstance(last_entry, dict) else "unknown"
        history.append(
            {
                "at": now_iso,
                "health": str(health or "unknown").lower(),
                "reason": normalized_reason,
                "source": source,
                "validation_success": bool(validation_success),
                "can_trade": bool(can_trade),
            }
        )
        snapshot["health_last_transition_at"] = now_iso
        logger.warning(
            "exchange_health_transition",
            extra={
                "event_type": "exchange_health_transition",
                "user_id": user_id,
                "connection_id": connection_id,
                "old_health": previous_health,
                "new_health": str(health or "unknown").lower(),
                "reason_code": normalized_reason,
            },
        )

    snapshot["health_last_seen_at"] = now_iso
    snapshot["health_history"] = history[-30:]


def _run_signed_validation_if_due(db: Session, row: UserExchangeConnection, snapshot: dict, *, has_open_position: bool) -> dict:
    now = datetime.now(timezone.utc)
    signed_interval = _signed_check_interval_seconds(
        environment=row.environment,
        has_open_position=has_open_position,
        connection_id=row.id,
    )
    validated_at = snapshot.get("validated_at") or snapshot.get("validation_checked_at")
    signed_due = _seconds_since(validated_at, now=now) >= signed_interval

    retry_due = False
    next_retry_at = _parse_iso(snapshot.get("next_retry_at"))
    if bool(snapshot.get("is_reconnecting")) and next_retry_at is not None and next_retry_at <= now:
        retry_due = True

    if not signed_due and not retry_due:
        return snapshot

    validate_exchange_credentials_for_user(
        db,
        row.user_id,
        exchange=row.exchange,
        market_type=row.market_type,
        environment=row.environment,
        connection_id=row.id,
    )
    db.refresh(row)
    refreshed = dict(row.readiness_snapshot or {})
    refreshed["signed_checked_at"] = now.isoformat()
    refreshed["signed_interval_seconds"] = signed_interval
    return refreshed


def _sync_connection(db: Session, row: UserExchangeConnection, open_positions_index: dict[tuple[str, str], int]) -> None:
    now = datetime.now(timezone.utc)
    snapshot = dict(row.readiness_snapshot or {})
    policy = get_connection_reliability_policy()
    health_policy = policy.get("health") or {}

    has_api_key = bool(row.api_key_encrypted)
    has_api_secret = bool(row.api_secret_encrypted)
    if not has_api_key or not has_api_secret:
        if snapshot.get("last_error_reason") != "missing_credentials" or snapshot.get("connection_health") != "offline":
            snapshot.update(
                {
                    "validation_success": False,
                    "is_valid": False,
                    "can_trade": False,
                    "reason_codes": ["missing_credentials"],
                    "last_error_reason": "missing_credentials",
                    "connection_health": "offline",
                    "is_reconnecting": False,
                    "retry_attempt": 0,
                    "retry_backoff_seconds": 0,
                    "next_retry_at": None,
                    "liveness_checked_at": now.isoformat(),
                    "transient_failure_count": 0,
                    "transient_success_count": 0,
                }
            )
            _append_health_history(
                snapshot,
                health="offline",
                reason="missing_credentials",
                source="health_loop_credentials",
                validation_success=False,
                can_trade=False,
                user_id=row.user_id,
                connection_id=row.id,
            )
            row.readiness_snapshot = snapshot
            row.updated_at = now
        return

    env_key = "testnet" if str(row.environment or "").lower() == "testnet" else "live"
    liveness_policy = health_policy.get("liveness_interval_seconds") or {}
    liveness_interval = int(liveness_policy.get(env_key) or (4 if env_key == "testnet" else 8))
    liveness_due = _seconds_since(snapshot.get("liveness_checked_at"), now=now) >= liveness_interval

    if liveness_due:
        snapshot, _ = _run_fast_liveness_probe(row, snapshot)
        _append_health_history(
            snapshot,
            health=str(snapshot.get("connection_health") or "unknown"),
            reason=str(snapshot.get("last_error_reason") or "none"),
            source="health_loop_liveness",
            validation_success=bool(snapshot.get("validation_success")),
            can_trade=bool(snapshot.get("can_trade")),
            user_id=row.user_id,
            connection_id=row.id,
        )
        row.readiness_snapshot = snapshot
        row.updated_at = now

    open_count = open_positions_index.get((row.user_id, str(row.market_type or "spot").lower()), 0)
    has_open_position = open_count > 0

    updated_snapshot = _run_signed_validation_if_due(
        db,
        row,
        dict(row.readiness_snapshot or snapshot),
        has_open_position=has_open_position,
    )
    if updated_snapshot != (row.readiness_snapshot or {}):
        row.readiness_snapshot = updated_snapshot
        row.updated_at = datetime.now(timezone.utc)


def _run_exchange_connection_health_cycle(session_factory) -> None:
    db = session_factory()
    try:
        open_positions_index = _build_open_position_index(db)
        rows = db.query(UserExchangeConnection).all()
        for row in rows:
            _sync_connection(db, row, open_positions_index)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Exchange connection health loop cycle failed")
    finally:
        db.close()


async def run_exchange_connection_health_loop(session_factory) -> None:
    logger.info("Starting exchange connection health loop")
    while True:
        cycle_started = datetime.now(timezone.utc)
        await asyncio.to_thread(_run_exchange_connection_health_cycle, session_factory)
        elapsed = (datetime.now(timezone.utc) - cycle_started).total_seconds()
        await asyncio.sleep(max(1.0, 2.0 - elapsed))