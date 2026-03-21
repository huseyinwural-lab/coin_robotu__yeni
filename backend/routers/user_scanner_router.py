import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_user
from models import User
from schemas import UserScannerAnomalyAuditRequest, UserScannerAnomalyAuditResponse
from services.audit_service import create_audit_log
from services.pipeline.cache_store import get_counter, get_json, incr_counter, set_json
from services.scanner_anomaly_alert_service import (
    dispatch_generic_webhooks,
    evaluate_anomaly_severity,
    get_anomaly_alert_policy,
    get_pattern_mute_state,
    mute_pattern,
    record_pattern_hit,
    should_notify,
)
from services.scanner_runtime import get_runtime_snapshot, run_scanner_runtime
from services.user_scanner_operations_service import (
    build_user_scanner_daily_report,
    build_user_scanner_live_readiness,
    export_user_scanner_daily_report_csv,
)


router = APIRouter(prefix="/user/scanner/runtime", tags=["user_scanner_runtime"])

ANOMALY_COOLDOWN_SECONDS = 60
ANOMALY_DUPLICATE_WINDOW_SECONDS = 900
ANOMALY_MIN_TOTAL_REQUESTS = 5
ANOMALY_BURST_LIMIT_PER_MINUTE = 6


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _anomaly_state_key(user_id: str) -> str:
    return f"scanner:anomaly:audit:last:{user_id}"


def _anomaly_suppressed_counter_key(user_id: str) -> str:
    return f"scanner:anomaly:audit:suppressed:count:{user_id}"


def _anomaly_burst_key(user_id: str, now: datetime) -> str:
    return f"scanner:anomaly:audit:burst:{user_id}:{now.strftime('%Y%m%d%H%M')}"


def _build_anomaly_payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _increase_suppressed_count(user_id: str) -> int:
    key = _anomaly_suppressed_counter_key(user_id)
    return int(incr_counter(redis_client, key, 1))


def _read_suppressed_count(user_id: str) -> int:
    key = _anomaly_suppressed_counter_key(user_id)
    return int(get_counter(redis_client, key))


def _maybe_set_key_expiry(key: str, ttl_seconds: int) -> None:
    try:
        if hasattr(redis_client, "expire"):
            redis_client.expire(key, ttl_seconds)
    except Exception:
        return


@router.post("/run")
def run_runtime_scan(
    symbol_selection_mode: str = Query(default="all_market_symbols"),
    max_results: int = Query(default=120, ge=10, le=500),
    selected_symbols: str = Query(default=""),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    selected_list = [item.strip().upper() for item in selected_symbols.split(",") if item.strip()]
    return run_scanner_runtime(
        db,
        redis_client,
        user_id=current_user.id,
        symbol_selection_mode=symbol_selection_mode,
        selected_symbols=selected_list,
        symbol_source="crypto",
        max_results=max_results,
    )


@router.get("/snapshot")
def get_runtime_scan_snapshot(
    current_user: User = Depends(require_user),
):
    return get_runtime_snapshot(redis_client, user_id=current_user.id)


@router.get("/live-readiness")
def get_runtime_live_readiness(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_scanner_live_readiness(db, current_user.id, redis_client, window=window)


@router.get("/daily-report")
def get_runtime_daily_report(
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return build_user_scanner_daily_report(db, current_user.id, redis_client, window=window)


@router.get("/daily-report/export")
def get_runtime_daily_report_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    window: str = Query(default="24h", pattern="^(1h|6h|24h)$"),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    report = build_user_scanner_daily_report(db, current_user.id, redis_client, window=window)
    if format == "csv":
        content = export_user_scanner_daily_report_csv(report)
        filename = f"scanner_daily_report_{report.get('date', 'latest')}.csv"
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return report


@router.post("/anomaly-event", response_model=UserScannerAnomalyAuditResponse)
def create_runtime_anomaly_event(
    payload: UserScannerAnomalyAuditRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if payload.failed_requests + payload.success_requests > payload.total_requests:
        raise HTTPException(status_code=422, detail="failed_requests + success_requests toplam_requests değerini geçemez")

    normalized_points = [point.model_dump() for point in payload.trend_points[:5]]
    normalized_payload = {
        "source": payload.source,
        "fail_ratio": round(float(payload.fail_ratio), 6),
        "total_requests": int(payload.total_requests),
        "failed_requests": int(payload.failed_requests),
        "success_requests": int(payload.success_requests),
        "trend_window_minutes": int(payload.trend_window_minutes),
        "trend_points": normalized_points,
    }
    payload_hash = _build_anomaly_payload_hash(normalized_payload)
    policy = get_anomaly_alert_policy()
    alert_severity = evaluate_anomaly_severity(fail_ratio=float(payload.fail_ratio), policy=policy)

    if alert_severity == "info" or payload.total_requests < ANOMALY_MIN_TOTAL_REQUESTS:
        suppressed = _increase_suppressed_count(current_user.id)
        return UserScannerAnomalyAuditResponse(
            status="suppressed",
            suppressed_count=suppressed,
            suppress_reason="guardrail_threshold",
            payload_hash=payload_hash,
            alert_severity=alert_severity,
        )

    muted_state = get_pattern_mute_state(payload_hash)
    if muted_state:
        suppressed = _increase_suppressed_count(current_user.id)
        return UserScannerAnomalyAuditResponse(
            status="suppressed",
            suppressed_count=suppressed,
            suppress_reason="muted_pattern",
            payload_hash=payload_hash,
            alert_severity=alert_severity,
            mute_until=muted_state["mute_until"],
        )

    now = _utc_now()
    state_key = _anomaly_state_key(current_user.id)
    state = get_json(redis_client, state_key) or {}
    cooldown_until = _safe_parse_iso(str(state.get("cooldown_until") or ""))
    duplicate_until = _safe_parse_iso(str(state.get("duplicate_until") or ""))
    last_payload_hash = str(state.get("last_payload_hash") or "")

    if cooldown_until and now < cooldown_until:
        suppressed = _increase_suppressed_count(current_user.id)
        return UserScannerAnomalyAuditResponse(
            status="suppressed",
            suppressed_count=suppressed,
            suppress_reason="cooldown_active",
            payload_hash=payload_hash,
            alert_severity=alert_severity,
        )

    if duplicate_until and now < duplicate_until and last_payload_hash == payload_hash:
        suppressed = _increase_suppressed_count(current_user.id)
        return UserScannerAnomalyAuditResponse(
            status="suppressed",
            suppressed_count=suppressed,
            suppress_reason="duplicate_payload",
            payload_hash=payload_hash,
            alert_severity=alert_severity,
        )

    burst_key = _anomaly_burst_key(current_user.id, now)
    burst_count = int(incr_counter(redis_client, burst_key, 1))
    _maybe_set_key_expiry(burst_key, 120)
    if burst_count > ANOMALY_BURST_LIMIT_PER_MINUTE:
        suppressed = _increase_suppressed_count(current_user.id)
        return UserScannerAnomalyAuditResponse(
            status="suppressed",
            suppressed_count=suppressed,
            suppress_reason="burst_limit",
            payload_hash=payload_hash,
            alert_severity=alert_severity,
        )

    pattern_hits = record_pattern_hit(
        user_id=current_user.id,
        payload_hash=payload_hash,
        window_seconds=int(policy.get("smart_mute_window_seconds") or 300),
    )
    trigger_count = int(policy.get("smart_mute_trigger_count") or 3)
    if pattern_hits >= trigger_count:
        mute_state = mute_pattern(
            payload_hash=payload_hash,
            duration_seconds=int(policy.get("smart_mute_duration_seconds") or 900),
            reason="smart_mute_auto",
            actor_user_id=current_user.id,
        )
        suppressed = _increase_suppressed_count(current_user.id)
        return UserScannerAnomalyAuditResponse(
            status="suppressed",
            suppressed_count=suppressed,
            suppress_reason="smart_mute_auto",
            payload_hash=payload_hash,
            alert_severity=alert_severity,
            mute_until=mute_state["mute_until"],
        )

    suppressed_count = _read_suppressed_count(current_user.id)
    webhook_payload = {
        "event": "SCANNER_ANOMALY_DETECTED",
        "severity": alert_severity,
        "actor_user_id": current_user.id,
        "timestamp": now.isoformat(),
        "details": normalized_payload,
        "payload_hash": payload_hash,
    }
    webhook_delivery = {
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "failures": [],
    }
    if should_notify(severity=alert_severity, policy=policy):
        webhook_delivery = dispatch_generic_webhooks(payload=webhook_payload, policy=policy)

    details = {
        **normalized_payload,
        "payload_hash": payload_hash,
        "alert_severity": alert_severity,
        "suppressed_count": suppressed_count,
        "pattern_hits": pattern_hits,
        "notification": webhook_delivery,
        "policy_snapshot": {
            "warning_threshold": policy.get("warning_threshold"),
            "critical_threshold": policy.get("critical_threshold"),
            "smart_mute_window_seconds": policy.get("smart_mute_window_seconds"),
            "smart_mute_trigger_count": policy.get("smart_mute_trigger_count"),
            "smart_mute_duration_seconds": policy.get("smart_mute_duration_seconds"),
            "notify_min_severity": policy.get("notify_min_severity"),
            "notifications_enabled": policy.get("notifications_enabled"),
            "webhook_count": len(policy.get("webhook_urls") or []),
        },
        "guardrails": {
            "cooldown_seconds": ANOMALY_COOLDOWN_SECONDS,
            "duplicate_window_seconds": ANOMALY_DUPLICATE_WINDOW_SECONDS,
            "burst_limit_per_minute": ANOMALY_BURST_LIMIT_PER_MINUTE,
            "min_fail_ratio": float(policy.get("warning_threshold") or 0.1),
            "min_total_requests": ANOMALY_MIN_TOTAL_REQUESTS,
        },
    }
    audit_entry = create_audit_log(
        db,
        action="SCANNER_ANOMALY_DETECTED",
        entity_type="user_scanner_runtime",
        entity_id=current_user.id,
        severity=alert_severity,
        actor_user_id=current_user.id,
        actor_role=str(getattr(current_user, "role", "user") or "user").lower(),
        details=details,
    )

    set_json(
        redis_client,
        state_key,
        {
            "last_logged_at": now.isoformat(),
            "last_payload_hash": payload_hash,
            "cooldown_until": (now + timedelta(seconds=ANOMALY_COOLDOWN_SECONDS)).isoformat(),
            "duplicate_until": (now + timedelta(seconds=ANOMALY_DUPLICATE_WINDOW_SECONDS)).isoformat(),
            "suppressed_count": suppressed_count,
            "last_audit_log_id": audit_entry.id,
        },
    )

    return UserScannerAnomalyAuditResponse(
        status="logged",
        audit_log_id=audit_entry.id,
        logged_at=audit_entry.created_at,
        suppressed_count=suppressed_count,
        payload_hash=payload_hash,
        alert_severity=alert_severity,
    )
