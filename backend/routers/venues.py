import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin, require_super_admin
from models import (
    AuditLog,
    AdminExchangeCredential,
    AllowedMarket,
    ExchangeCapability,
    ExchangeRegistry,
    User,
    UserExchangeConnection,
    UserVenueAssignment,
)
from schemas import (
    AdminExchangeCredentialCreateRequest,
    AdminExchangeCredentialPatchRequest,
    AdminExchangeCredentialRotateRequest,
    AdminExchangeCredentialResponse,
    AllowedMarketCreate,
    AllowedMarketResponse,
    AllowedMarketToggle,
    CredentialAssignmentRuleResponse,
    CredentialAssignmentRuleUpsertRequest,
    CredentialResolutionPreviewResponse,
    ExchangeCapabilityCreate,
    ExchangeCapabilityResponse,
    ExchangeCapabilityUpdate,
    ExchangeRegistryCreate,
    ExchangeRegistryResponse,
    ExchangeRegistryUpdate,
    UserVenueAssignmentResponse,
    UserVenueAssignmentUpdate,
    UserVenueOptionResponse,
    VenueHealthSummaryResponse,
    CapabilityDiscoveryRequest,
    CapabilityMatrixOverrideRequest,
    MarketPolicyLayerUpdateRequest,
    FailoverPolicyUpsertRequest,
    FailoverManualOverrideRequest,
    ValidationCenterRerunRequest,
    ConflictAutoRemediationApplyRequest,
    RoutingPolicyUpsertRequest,
    RoutingPreviewRequest,
)
from services.audit_service import create_audit_log
from services.admin_exchange_credentials_service import (
    execution_credentials_for_adapter,
    get_execution_credentials,
    upsert_execution_credentials,
)
from services.exchange_adapter_smoke_service import run_exchange_adapter_smoke
from services.credential_resolution_service import (
    approve_admin_credential,
    create_admin_credential,
    disable_admin_credential,
    list_admin_credentials,
    list_assignment_rules,
    probe_admin_credential,
    revoke_admin_credential,
    resolve_exchange_credentials,
    rotate_admin_credential,
    update_admin_credential,
    upsert_assignment_rule,
    verify_admin_credential,
)
from services.venue_control_plane_service import (
    get_cached_venue_control_plane_sanity,
    run_and_cache_venue_control_plane_sanity,
)
from services.venue_service import check_user_venue_access, seed_binance_venue_registry, user_allowed_venue_options, venue_health_summary
from services.control_plane_config_service import get_control_plane_config, upsert_control_plane_config
from services.venue_discovery_service import discover_exchange_capabilities

router = APIRouter(prefix="/venues", tags=["venues"])


def _credential_error(exc: Exception) -> HTTPException:
    message = str(exc)
    mapping = {
        "invalid_scope_type": (status.HTTP_400_BAD_REQUEST, "invalid_scope_type"),
        "invalid_market_type": (status.HTTP_400_BAD_REQUEST, "invalid_market_type"),
        "invalid_environment": (status.HTTP_400_BAD_REQUEST, "invalid_environment"),
        "invalid_purpose": (status.HTTP_400_BAD_REQUEST, "invalid_purpose"),
        "invalid_preferred_source": (status.HTTP_400_BAD_REQUEST, "invalid_preferred_source"),
        "unsupported_exchange": (status.HTTP_400_BAD_REQUEST, "unsupported_exchange"),
        "credential_not_found": (status.HTTP_404_NOT_FOUND, "credential_not_found"),
        "credential_readback_verification_failed": (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "credential_readback_verification_failed",
        ),
        "credential_verify_failed": (status.HTTP_409_CONFLICT, "credential_verify_failed"),
        "invalid_rotation_payload": (status.HTTP_400_BAD_REQUEST, "invalid_rotation_payload"),
        "environment_lock_blocked": (status.HTTP_409_CONFLICT, "environment_lock_blocked"),
        "prod_freeze_active": (status.HTTP_409_CONFLICT, "prod_freeze_active"),
        "live_route_not_approved": (status.HTTP_409_CONFLICT, "live_route_not_approved"),
        "mode_mismatch_live_blocked": (status.HTTP_409_CONFLICT, "mode_mismatch_live_blocked"),
        "venue_not_allowed": (status.HTTP_409_CONFLICT, "venue_not_allowed"),
        "approved_credential_required": (status.HTTP_409_CONFLICT, "approved_credential_required"),
        "symbol_policy_blocked": (status.HTTP_409_CONFLICT, "symbol_policy_blocked"),
        "restricted_symbol_class_blocked": (status.HTTP_409_CONFLICT, "restricted_symbol_class_blocked"),
        "sanity_gate_blocked": (status.HTTP_409_CONFLICT, "sanity_gate_blocked"),
        "canary_allowlist_blocked": (status.HTTP_409_CONFLICT, "canary_allowlist_blocked"),
        "two_step_approval_missing": (status.HTTP_409_CONFLICT, "two_step_approval_missing"),
        "local_secret_provider_not_allowed_in_prod": (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "local_secret_provider_not_allowed_in_prod",
        ),
        "execution_credential_readback_verification_failed": (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "execution_credential_readback_verification_failed",
        ),
    }
    code, detail = mapping.get(message, (status.HTTP_400_BAD_REQUEST, message))
    return HTTPException(status_code=code, detail=detail)


_STATUS_RANK = {"PASS": 0, "WARN": 1, "BLOCK": 2}
_HARD_DOWN_REASON_CODES = {
    "missing_credentials",
    "invalid_key",
    "ip_restriction",
    "exchange_error_451",
}


def _safe_float_value(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    index = (len(ordered) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    ratio = index - lower
    score = ordered[lower] + (ordered[upper] - ordered[lower]) * ratio
    return round(score, 2)


def _add_reason(reason_codes: list[str], reason_code: str) -> None:
    normalized = str(reason_code or "").strip().lower()
    if normalized and normalized not in reason_codes:
        reason_codes.append(normalized)


def _parse_datetime_query(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_datetime_filter")


def _extract_diff_keys(old_value: Any, new_value: Any) -> list[str]:
    if isinstance(old_value, dict) and isinstance(new_value, dict):
        keys = sorted(set(old_value.keys()) | set(new_value.keys()))
        return [key for key in keys if old_value.get(key) != new_value.get(key)]
    if old_value != new_value:
        return ["value"]
    return []


def _derive_symbol_class(symbol: str) -> str:
    normalized = str(symbol or "").upper()
    if normalized.endswith(("UPUSDT", "DOWNUSDT", "3LUSDT", "3SUSDT")):
        return "leverage_token"
    if any(token in normalized for token in ["PEPE", "DOGE", "SHIB", "FLOKI", "BONK"]):
        return "meme"
    return "core"


def _policy_effect_for_symbol(
    market_policy_rules: dict,
    *,
    exchange: str,
    market_type: str,
    environment: str,
    symbol: str,
) -> dict:
    key = f"{exchange}:{market_type}:{environment}"
    policy = (market_policy_rules or {}).get(key) or {}
    symbol_rules = policy.get("symbol_rules") or []

    symbol_action = "allow"
    for rule in symbol_rules:
        if str(rule.get("symbol") or "").upper() == str(symbol or "").upper():
            symbol_action = str(rule.get("action") or "allow").strip().lower()
            break

    restricted_classes = [str(item).strip().lower() for item in (policy.get("restricted_symbol_classes") or []) if str(item).strip()]
    symbol_class = _derive_symbol_class(symbol)
    blocked_by_class = symbol_class in restricted_classes

    reason_codes: list[str] = []
    if symbol_action == "deny":
        _add_reason(reason_codes, "symbol_policy_blocked")
    if blocked_by_class:
        _add_reason(reason_codes, "restricted_symbol_class_blocked")

    return {
        "key": key,
        "symbol_action": symbol_action,
        "symbol_class": symbol_class,
        "restricted_symbol_classes": restricted_classes,
        "risk_tier_defaults": policy.get("risk_tier_defaults") or {},
        "is_blocked": symbol_action == "deny" or blocked_by_class,
        "reason_codes": reason_codes,
    }


def _capability_effect_for_symbol(
    db: Session,
    capability_matrix: dict,
    *,
    exchange: str,
    market_type: str,
    environment: str,
    symbol: str,
) -> dict:
    key = f"{exchange}:{market_type}:{environment}"
    matrix_entry = (capability_matrix or {}).get(key) or {}
    symbol_caps = matrix_entry.get("symbol_capabilities") or []
    match = None
    for item in symbol_caps:
        if str(item.get("symbol") or "").upper() == str(symbol or "").upper():
            match = item
            break

    if match is not None:
        support_level = str(match.get("support_level") or "partial").strip().lower()
        if support_level not in {"supported", "partial", "unsupported"}:
            support_level = "partial"
        return {
            "source": "capability_matrix",
            "support_level": support_level,
            "supports_leverage": bool(match.get("supports_leverage")),
            "supports_reduce_only": bool(match.get("supports_reduce_only")),
            "supports_margin_mode": bool(match.get("supports_margin_mode")),
            "supports_hedge_mode": bool(match.get("supports_hedge_mode")),
            "reason_codes": [] if support_level != "unsupported" else ["capability_unsupported"],
        }

    fallback = (
        db.query(ExchangeCapability)
        .filter(ExchangeCapability.exchange_code == exchange, ExchangeCapability.market_type == market_type)
        .first()
    )
    if fallback is None:
        return {
            "source": "unknown",
            "support_level": "unsupported",
            "supports_leverage": False,
            "supports_reduce_only": False,
            "supports_margin_mode": False,
            "supports_hedge_mode": False,
            "reason_codes": ["capability_missing"],
        }

    market_supported = bool(fallback.supports_spot) if market_type == "spot" else bool(fallback.supports_futures)
    return {
        "source": "exchange_capability_table",
        "support_level": "supported" if market_supported else "unsupported",
        "supports_leverage": bool(fallback.supports_leverage),
        "supports_reduce_only": bool(fallback.supports_reduce_only),
        "supports_margin_mode": bool(fallback.supports_margin_mode),
        "supports_hedge_mode": bool(fallback.supports_hedge_mode),
        "reason_codes": [] if market_supported else ["capability_unsupported"],
    }


def _build_exchange_operational_score(exchange_row: ExchangeRegistry, rows: list[UserExchangeConnection]) -> dict:
    latencies: list[float] = []
    validation_success = 0
    validation_fail = 0
    reconnecting_count = 0
    unreachable_count = 0
    trade_ready_count = 0
    hard_down_count = 0
    telemetry_reason_codes: list[str] = []

    for row in rows:
        snapshot = dict(row.readiness_snapshot or {})
        if bool(snapshot.get("is_reconnecting")):
            reconnecting_count += 1
        if str(snapshot.get("liveness_status") or "").strip().lower() == "unreachable":
            unreachable_count += 1
        if bool(snapshot.get("can_trade")):
            trade_ready_count += 1

        direct_latency = _safe_float_value(snapshot.get("liveness_latency_ms"))
        if direct_latency is not None:
            latencies.append(direct_latency)
        for item in (snapshot.get("liveness_latency_history") or []):
            latency = _safe_float_value((item or {}).get("latency_ms"))
            if latency is not None:
                latencies.append(latency)

        history = snapshot.get("health_history") or []
        history_with_flags = [entry for entry in history if isinstance(entry, dict) and "validation_success" in entry]
        if history_with_flags:
            for entry in history_with_flags:
                if bool(entry.get("validation_success")):
                    validation_success += 1
                else:
                    validation_fail += 1
        elif "validation_success" in snapshot:
            if bool(snapshot.get("validation_success")):
                validation_success += 1
            else:
                validation_fail += 1

        last_reason = str(snapshot.get("last_error_reason") or "").strip().lower()
        for reason in (snapshot.get("reason_codes") or []):
            _add_reason(telemetry_reason_codes, str(reason))
        if last_reason:
            _add_reason(telemetry_reason_codes, last_reason)
            if last_reason in _HARD_DOWN_REASON_CODES:
                hard_down_count += 1

    connection_count = len(rows)
    latency_ms_p95 = _percentile(latencies, 0.95)
    total_validations = validation_success + validation_fail
    validation_success_rate = round((validation_success / total_validations) * 100, 1) if total_validations > 0 else None

    reconnect_ratio = (reconnecting_count / connection_count) if connection_count > 0 else 0.0
    trade_ready_ratio = (trade_ready_count / connection_count) if connection_count > 0 else 0.0

    if connection_count == 0:
        websocket_sync_health = "unknown"
    elif hard_down_count > 0:
        websocket_sync_health = "down"
    elif reconnect_ratio >= 0.35 or unreachable_count > 0:
        websocket_sync_health = "degraded"
    else:
        websocket_sync_health = "healthy"

    if connection_count == 0:
        orderbook_sync_health = "unknown"
    elif validation_success_rate is not None and validation_success_rate < 60:
        orderbook_sync_health = "down"
    elif validation_success_rate is not None and validation_success_rate < 88:
        orderbook_sync_health = "degraded"
    elif trade_ready_ratio < 0.40:
        orderbook_sync_health = "degraded"
    else:
        orderbook_sync_health = "healthy"

    base_rate_limit = {"ok": 10, "healthy": 10, "warning": 65, "throttled": 90}.get(
        str(exchange_row.rate_limit_status or "ok").strip().lower(),
        25,
    )
    if "rate_limit" in telemetry_reason_codes:
        base_rate_limit += 10
    if reconnect_ratio >= 0.35:
        base_rate_limit += 8
    rate_limit_pressure = max(0, min(100, int(base_rate_limit)))

    reason_codes: list[str] = []
    health_score = 100

    exchange_health_status = str(exchange_row.health_status or "healthy").strip().lower()
    if exchange_health_status == "degraded":
        health_score -= 18
        _add_reason(reason_codes, "exchange_registry_health_degraded")
    if exchange_health_status == "down":
        health_score -= 40
        _add_reason(reason_codes, "exchange_registry_health_down")

    if latency_ms_p95 is not None and latency_ms_p95 >= 1400:
        health_score -= 25
        _add_reason(reason_codes, "telemetry_latency_p95_critical")
    elif latency_ms_p95 is not None and latency_ms_p95 >= 900:
        health_score -= 12
        _add_reason(reason_codes, "telemetry_latency_p95_elevated")

    if validation_success_rate is not None and validation_success_rate < 70:
        health_score -= 28
        _add_reason(reason_codes, "telemetry_validation_success_low")
    elif validation_success_rate is not None and validation_success_rate < 90:
        health_score -= 12
        _add_reason(reason_codes, "telemetry_validation_success_warning")

    if rate_limit_pressure >= 85:
        health_score -= 24
        _add_reason(reason_codes, "telemetry_rate_limit_pressure_critical")
    elif rate_limit_pressure >= 60:
        health_score -= 12
        _add_reason(reason_codes, "telemetry_rate_limit_pressure_elevated")

    if websocket_sync_health == "degraded":
        health_score -= 14
        _add_reason(reason_codes, "telemetry_websocket_sync_degraded")
    elif websocket_sync_health == "down":
        health_score -= 30
        _add_reason(reason_codes, "telemetry_websocket_sync_down")

    if orderbook_sync_health == "degraded":
        health_score -= 12
        _add_reason(reason_codes, "telemetry_orderbook_sync_degraded")
    elif orderbook_sync_health == "down":
        health_score -= 26
        _add_reason(reason_codes, "telemetry_orderbook_sync_down")

    if connection_count == 0:
        _add_reason(reason_codes, "telemetry_connections_missing")

    health_score = max(0, min(100, int(round(health_score))))
    if health_score < 45 or websocket_sync_health == "down" or orderbook_sync_health == "down" or exchange_health_status == "down":
        computed_health_status = "down"
    elif health_score < 78 or reason_codes:
        computed_health_status = "degraded"
    else:
        computed_health_status = "healthy"

    return {
        "exchange": exchange_row.exchange_code,
        "health_score": health_score,
        "health_status": computed_health_status,
        "rate_limit_status": exchange_row.rate_limit_status,
        "latency_ms_p95": latency_ms_p95,
        "validation_success_rate": validation_success_rate,
        "rate_limit_pressure": rate_limit_pressure,
        "websocket_sync_health": websocket_sync_health,
        "orderbook_sync_health": orderbook_sync_health,
        "connection_count": connection_count,
        "validation_success_count": validation_success,
        "validation_fail_count": validation_fail,
        "reason_codes": reason_codes,
    }


def _build_operational_health_payload(db: Session) -> dict:
    summary = venue_health_summary(db)
    sanity = get_cached_venue_control_plane_sanity() or {
        "net_status": "WARN",
        "reason_codes": ["sanity_not_run"],
        "remediation_suggestions": ["Control plane sanity check çalıştırın."],
        "checks": [],
    }

    exchange_rows = db.query(ExchangeRegistry).order_by(ExchangeRegistry.exchange_code.asc()).all()
    connection_rows = db.query(UserExchangeConnection).all()
    grouped: dict[str, list[UserExchangeConnection]] = defaultdict(list)
    for row in connection_rows:
        grouped[str(row.exchange or "").strip().lower()].append(row)

    operational_scores = [
        _build_exchange_operational_score(exchange_row, grouped.get(exchange_row.exchange_code, []))
        for exchange_row in exchange_rows
    ]

    reason_codes = [str(code).strip().lower() for code in (sanity.get("reason_codes") or []) if str(code).strip()]
    remediation_suggestions = [str(item) for item in (sanity.get("remediation_suggestions") or []) if str(item).strip()]
    checks = list(sanity.get("checks") or [])

    has_down = any(item.get("health_status") == "down" for item in operational_scores)
    has_degraded = any(item.get("health_status") == "degraded" for item in operational_scores)

    if has_down:
        _add_reason(reason_codes, "exchange_operational_down")
        remediation_suggestions.append("Down durumundaki exchange için credential/latency/rate-limit nedeni çözülmeden live route açmayın.")
    elif has_degraded:
        _add_reason(reason_codes, "exchange_operational_degraded")
        remediation_suggestions.append("Degraded exchange telemetry değerlerini (latency/validation/rate-limit) stabilize edin.")

    for item in operational_scores:
        status_value = "PASS"
        if item.get("health_status") == "down":
            status_value = "BLOCK"
        elif item.get("health_status") == "degraded":
            status_value = "WARN"

        checks.append(
            {
                "name": f"exchange_operational_{item.get('exchange')}",
                "status": status_value,
                "reason_code": (item.get("reason_codes") or ["operational_healthy"])[0],
                "severity": "high" if status_value == "BLOCK" else ("medium" if status_value == "WARN" else "low"),
                "remediation_suggestions": [
                    "Operational health panelindeki reason code'ları temel alarak venue config düzeltmesi yapın."
                ]
                if status_value != "PASS"
                else [],
            }
        )

    sanity_status = str(sanity.get("net_status") or "WARN").upper()
    net_status = "PASS"
    if has_down:
        net_status = "BLOCK"
    elif has_degraded or sanity_status in {"WARN", "BLOCK"}:
        net_status = "WARN"

    return {
        "net_status": net_status,
        "reason_codes": reason_codes,
        "remediation_suggestions": remediation_suggestions,
        "checks": checks,
        "exchange_health": summary.get("exchange_health") or {},
        "market_availability": summary.get("market_availability") or {},
        "operational_scores": operational_scores,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_venue_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for item in values or []:
        venue = str(item or "").strip().lower()
        if venue and venue not in normalized:
            normalized.append(venue)
    return normalized


def _failover_rule_key(*, user_id: str, strategy_id: str, market_type: str, environment: str) -> str:
    return f"{user_id}:{strategy_id}:{market_type.lower()}:{environment.lower()}"


def _get_failover_policy_config(db: Session) -> dict:
    return get_control_plane_config(db, config_key="failover_policy", default={"rules": {}})


def _get_failover_runtime_config(db: Session) -> dict:
    return get_control_plane_config(
        db,
        config_key="failover_runtime",
        default={"runtime_state": {}, "transition_logs": [], "routing_decision_logs": []},
    )


def _evaluate_venue_runtime_state(health_effect: dict, thresholds: dict) -> dict:
    latency_threshold = float(thresholds.get("latency_ms") or 1200)
    error_threshold = float(thresholds.get("error_rate_pct") or 20)
    validation_failure_threshold = float(thresholds.get("validation_failure_pct") or 25)

    latency_ms = _safe_float_value(health_effect.get("latency_ms_p95"))
    validation_success_rate = _safe_float_value(health_effect.get("validation_success_rate"))
    error_rate_pct = max(0.0, 100.0 - float(validation_success_rate)) if validation_success_rate is not None else 100.0
    validation_failure_pct = error_rate_pct

    trigger_metrics = []
    if latency_ms is not None and latency_ms >= latency_threshold:
        trigger_metrics.append({"metric": "latency", "value": latency_ms, "threshold": latency_threshold})
    if error_rate_pct >= error_threshold:
        trigger_metrics.append({"metric": "error_rate", "value": round(error_rate_pct, 2), "threshold": error_threshold})
    if validation_failure_pct >= validation_failure_threshold:
        trigger_metrics.append(
            {
                "metric": "validation_failure",
                "value": round(validation_failure_pct, 2),
                "threshold": validation_failure_threshold,
            }
        )

    health_status = str(health_effect.get("health_status") or "unknown").lower()
    if health_status == "down" or error_rate_pct >= max(70.0, error_threshold * 1.8):
        runtime_state = "down"
    elif health_status == "degraded" or trigger_metrics:
        runtime_state = "degraded"
    else:
        runtime_state = "healthy"

    return {
        "runtime_state": runtime_state,
        "trigger_metrics": trigger_metrics,
        "latency_ms_p95": latency_ms,
        "error_rate_pct": round(error_rate_pct, 2),
        "validation_failure_pct": round(validation_failure_pct, 2),
        "health_score": health_effect.get("health_score"),
        "rate_limit_pressure": health_effect.get("rate_limit_pressure"),
    }


def _resolve_failover_plan(rule: dict, *, health_map: dict) -> dict:
    primary = str(rule.get("primary_venue") or "").strip().lower()
    secondary = str(rule.get("secondary_venue") or "").strip().lower()
    fallback_chain = _normalize_venue_list(rule.get("fallback_chain") or [])
    chain = _normalize_venue_list([primary, secondary, *fallback_chain])

    thresholds = dict(rule.get("auto_trigger_thresholds") or {})
    auto_reroute_enabled = bool(rule.get("auto_reroute_enabled", True))
    manual_override = dict(rule.get("manual_override") or {})
    forced_route = str(manual_override.get("force_route") or "").strip().lower() or None
    forced_disable = set(_normalize_venue_list(manual_override.get("force_disable") or []))

    evaluations = {}
    for venue in chain:
        health_effect = health_map.get(venue) or {
            "exchange": venue,
            "health_status": "unknown",
            "health_score": 40,
            "latency_ms_p95": None,
            "validation_success_rate": None,
            "rate_limit_pressure": 0,
        }
        state = _evaluate_venue_runtime_state(health_effect, thresholds)
        evaluations[venue] = {**state, "disabled": venue in forced_disable}

    selection_reason = "auto_primary_preferred"
    active_venue = None
    reject_reason = None

    if forced_route and forced_route not in forced_disable:
        active_venue = forced_route
        selection_reason = "manual_force_route"
    elif not auto_reroute_enabled:
        selection_reason = "auto_reroute_disabled"
        for venue in chain:
            if venue not in forced_disable:
                active_venue = venue
                break
    else:
        for target_state in ["healthy", "degraded"]:
            for venue in chain:
                venue_state = evaluations.get(venue) or {}
                if venue in forced_disable:
                    continue
                if venue_state.get("runtime_state") == target_state:
                    active_venue = venue
                    selection_reason = f"auto_reroute_{target_state}"
                    break
            if active_venue:
                break

    if active_venue is None:
        reject_reason = "failover_no_available_venue"

    return {
        "active_venue": active_venue,
        "fallback_chain": [venue for venue in chain if venue != active_venue],
        "selection_reason": selection_reason,
        "forced_route": forced_route,
        "forced_disable": sorted(list(forced_disable)),
        "auto_reroute_enabled": auto_reroute_enabled,
        "runtime_evaluations": evaluations,
        "reject_reason": reject_reason,
    }


def _record_failover_transition(runtime_config: dict, *, key: str, plan: dict, actor_user_id: str | None = None) -> dict | None:
    runtime_state = dict(runtime_config.get("runtime_state") or {})
    transition_logs = list(runtime_config.get("transition_logs") or [])

    previous = dict(runtime_state.get(key) or {})
    previous_active = previous.get("active_venue")
    next_active = plan.get("active_venue")
    selection_reason = str(plan.get("selection_reason") or "auto")

    transition_event = None
    if previous_active != next_active:
        transition_event = {
            "id": str(uuid.uuid4()),
            "key": key,
            "from_venue": previous_active,
            "to_venue": next_active,
            "selection_reason": selection_reason,
            "trigger_metrics": (
                ((plan.get("runtime_evaluations") or {}).get(next_active) or {}).get("trigger_metrics") if next_active else []
            ),
            "reason_code": str(plan.get("reject_reason") or selection_reason),
            "actor_user_id": actor_user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        transition_logs.insert(0, transition_event)
        transition_logs = transition_logs[:300]

    runtime_state[key] = {
        "active_venue": next_active,
        "selection_reason": selection_reason,
        "reject_reason": plan.get("reject_reason"),
        "runtime_evaluations": plan.get("runtime_evaluations") or {},
        "fallback_chain": plan.get("fallback_chain") or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": int(previous.get("version") or 0) + 1,
    }

    runtime_config["runtime_state"] = runtime_state
    runtime_config["transition_logs"] = transition_logs
    return transition_event


def _append_routing_decision_log(runtime_config: dict, payload: dict) -> dict:
    logs = list(runtime_config.get("routing_decision_logs") or [])
    event = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    logs.insert(0, event)
    runtime_config["routing_decision_logs"] = logs[:500]
    return event


def _build_execution_validation_report(db: Session) -> dict:
    credentials = execution_credentials_for_adapter(db)
    smoke = run_exchange_adapter_smoke(credentials_override=credentials)
    execution_rows = smoke.get("execution_adapter") or []

    real_balance_ok = any(
        (not bool(row.get("mocked")))
        and int(((row.get("payload") or {}).get("provider") or {}).get("http_status") or 0) == 200
        for row in execution_rows
    )
    has_mocked_balance = any(bool(row.get("mocked")) for row in execution_rows)

    permission_real_ok = any(
        (not bool(row.get("mocked"))) and str(row.get("status") or "") in {"SUBMITTED", "CANCELLED"}
        for row in execution_rows
    )
    capability_runtime_ok = all((row.get("precision_validation") or {}).get("status") == "PASS" for row in execution_rows) if execution_rows else False
    dry_run_ok = all(bool((row.get("payload") or {}).get("normalized")) for row in execution_rows) if execution_rows else False
    test_order_ok = any(str((row.get("payload") or {}).get("status") or "") in {"SUBMITTED", "MOCKED"} for row in execution_rows)
    cancel_ok = any(str((row.get("cancel") or {}).get("status") or "") in {"CANCELLED", "MOCKED"} for row in execution_rows)
    retry_ok = all(str((row.get("retry_behavior") or {}).get("status") or "") == "configured" for row in execution_rows) if execution_rows else False

    rejection_classes = sorted(
        {
            str((row.get("payload") or {}).get("reason") or "").strip().lower()
            for row in execution_rows
            if str((row.get("payload") or {}).get("reason") or "").strip()
        }
    )

    checks = [
        {
            "name": "real_balance_fetch",
            "status": "PASS" if real_balance_ok else ("WARN" if has_mocked_balance else "BLOCK"),
            "reason_code": "balance_real_ok" if real_balance_ok else ("balance_fetch_mocked" if has_mocked_balance else "balance_fetch_failed"),
            "severity": "high" if not real_balance_ok and not has_mocked_balance else ("medium" if has_mocked_balance else "low"),
            "remediation_suggestions": [] if real_balance_ok else ["Venue API credential doğrulaması ve wallet-balance erişimini kontrol edin."],
        },
        {
            "name": "permission_matrix_test",
            "status": "PASS" if permission_real_ok else ("WARN" if has_mocked_balance else "BLOCK"),
            "reason_code": "permission_matrix_ok" if permission_real_ok else ("permission_matrix_mocked" if has_mocked_balance else "permission_matrix_failed"),
            "severity": "high" if not permission_real_ok and not has_mocked_balance else "medium",
            "remediation_suggestions": [] if permission_real_ok else ["Trade/read permission scope ve credential approval durumunu doğrulayın."],
        },
        {
            "name": "venue_capability_runtime_test",
            "status": "PASS" if capability_runtime_ok else "WARN",
            "reason_code": "capability_runtime_ok" if capability_runtime_ok else "capability_runtime_partial",
            "severity": "medium" if not capability_runtime_ok else "low",
            "remediation_suggestions": [] if capability_runtime_ok else ["Precision/lot-size metadata senkronunu güncelleyin."],
        },
        {
            "name": "dry_run_execution_simulation",
            "status": "PASS" if dry_run_ok else "BLOCK",
            "reason_code": "dry_run_simulation_ok" if dry_run_ok else "dry_run_simulation_failed",
            "severity": "high" if not dry_run_ok else "low",
            "remediation_suggestions": [] if dry_run_ok else ["Execution adapter normalizasyon ve payload üretim akışını doğrulayın."],
        },
        {
            "name": "test_order_cancel_retry",
            "status": "PASS" if test_order_ok and cancel_ok and retry_ok else "WARN",
            "reason_code": "test_order_cancel_retry_ok" if test_order_ok and cancel_ok and retry_ok else "test_order_cancel_retry_partial",
            "severity": "medium" if not (test_order_ok and cancel_ok and retry_ok) else "low",
            "remediation_suggestions": [] if test_order_ok and cancel_ok and retry_ok else ["Submit/cancel/retry senaryolarını venue bazında stabilize edin."],
        },
        {
            "name": "rejection_classification",
            "status": "PASS" if rejection_classes else "WARN",
            "reason_code": "rejection_classification_available" if rejection_classes else "rejection_classification_missing",
            "severity": "medium" if not rejection_classes else "low",
            "remediation_suggestions": [] if rejection_classes else ["Rejection reason kodlarını sınıflandırmak için adapter mapping genişletin."],
        },
    ]

    max_rank = 0
    for item in checks:
        status_value = str(item.get("status") or "PASS").upper()
        max_rank = max(max_rank, 2 if status_value == "BLOCK" else (1 if status_value == "WARN" else 0))
    net_status = "PASS" if max_rank == 0 else ("WARN" if max_rank == 1 else "BLOCK")

    reason_codes = sorted({item.get("reason_code") for item in checks if item.get("reason_code") and item.get("reason_code") not in {"ok", "balance_real_ok", "permission_matrix_ok", "capability_runtime_ok", "dry_run_simulation_ok", "test_order_cancel_retry_ok", "rejection_classification_available"}})
    remediation_suggestions = sorted({tip for item in checks for tip in (item.get("remediation_suggestions") or [])})

    return {
        "net_status": net_status,
        "reason_codes": reason_codes,
        "remediation_suggestions": remediation_suggestions,
        "checks": checks,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "classification": {
            "pass": sum(1 for row in checks if row.get("status") == "PASS"),
            "warn": sum(1 for row in checks if row.get("status") == "WARN"),
            "block": sum(1 for row in checks if row.get("status") == "BLOCK"),
        },
        "smoke_summary": smoke.get("summary") or {},
        "adapter_output": smoke,
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _build_route_churn_alert(transition_logs: list[dict], *, window_minutes: int = 30, threshold: int = 5) -> dict:
    now_utc = datetime.now(timezone.utc)
    lower_bound = now_utc - timedelta(minutes=window_minutes)

    by_key: dict[str, int] = defaultdict(int)
    recent_logs = []
    for item in transition_logs or []:
        created_at = _parse_iso_datetime(item.get("created_at"))
        if created_at and created_at >= lower_bound:
            key = str(item.get("key") or "unknown")
            by_key[key] += 1
            recent_logs.append(item)

    hot_routes = [
        {"key": key, "transition_count": count}
        for key, count in sorted(by_key.items(), key=lambda pair: pair[1], reverse=True)
        if count >= threshold
    ]

    status_value = "BLOCK" if hot_routes else "PASS"
    reason_codes = ["route_churn_anomaly_detected"] if hot_routes else []
    remediation = ["Anomali görülen route için failover threshold ve manual override politikasını gözden geçirin."] if hot_routes else []

    return {
        "status": status_value,
        "window_minutes": window_minutes,
        "threshold": threshold,
        "total_recent_transitions": len(recent_logs),
        "hot_routes": hot_routes,
        "reason_codes": reason_codes,
        "remediation_suggestions": remediation,
        "evaluated_at": now_utc.isoformat(),
    }


def _build_conflict_detection_report(db: Session) -> dict:
    routing = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})
    failover = _get_failover_policy_config(db)

    routing_rules = routing.get("rules") or {}
    failover_rules = failover.get("rules") or {}

    alerts: list[dict] = []

    for key, rule in routing_rules.items():
        default_venue = str(rule.get("default_venue") or "").strip().lower()
        blocked_venues = set(_normalize_venue_list(rule.get("blocked_venues") or []))
        preferred_venues = _normalize_venue_list(rule.get("preferred_venues") or [])
        capital_allocation = list(rule.get("capital_allocation") or [])

        if default_venue and default_venue in blocked_venues:
            alerts.append(
                {
                    "type": "routing_conflict",
                    "severity": "BLOCK",
                    "reason_code": "default_venue_blocked",
                    "entity_id": key,
                    "message": "Default venue blocked_venues içinde tanımlı.",
                    "blocking": True,
                }
            )

        overlap = sorted(list(blocked_venues.intersection(preferred_venues)))
        if overlap:
            alerts.append(
                {
                    "type": "routing_conflict",
                    "severity": "WARN",
                    "reason_code": "preferred_and_blocked_overlap",
                    "entity_id": key,
                    "message": f"Aynı venue preferred ve blocked listede: {', '.join(overlap)}",
                    "blocking": False,
                }
            )

        if not capital_allocation:
            alerts.append(
                {
                    "type": "allocation_conflict",
                    "severity": "WARN",
                    "reason_code": "capital_allocation_missing",
                    "entity_id": key,
                    "message": "Routing policy için capital_allocation tanımı eksik.",
                    "blocking": False,
                }
            )

    for key, rule in failover_rules.items():
        primary_venue = str(rule.get("primary_venue") or "").strip().lower()
        secondary_venue = str(rule.get("secondary_venue") or "").strip().lower()
        manual_override = dict(rule.get("manual_override") or {})
        force_disable = set(_normalize_venue_list(manual_override.get("force_disable") or []))

        if primary_venue and primary_venue in force_disable:
            alerts.append(
                {
                    "type": "failover_conflict",
                    "severity": "BLOCK",
                    "reason_code": "primary_force_disabled",
                    "entity_id": key,
                    "message": "Primary venue manual force_disable listesinde.",
                    "blocking": True,
                }
            )

        if primary_venue and secondary_venue and primary_venue == secondary_venue:
            alerts.append(
                {
                    "type": "failover_conflict",
                    "severity": "WARN",
                    "reason_code": "primary_secondary_same",
                    "entity_id": key,
                    "message": "Primary ve secondary venue aynı değer.",
                    "blocking": False,
                }
            )

    has_block = any(item.get("severity") == "BLOCK" for item in alerts)
    has_warn = any(item.get("severity") == "WARN" for item in alerts)

    return {
        "net_status": "BLOCK" if has_block else ("WARN" if has_warn else "PASS"),
        "alerts": alerts,
        "blocking_alerts": [item for item in alerts if item.get("blocking")],
        "warning_alerts": [item for item in alerts if not item.get("blocking")],
        "summary": {
            "total_alerts": len(alerts),
            "block_count": sum(1 for item in alerts if item.get("severity") == "BLOCK"),
            "warn_count": sum(1 for item in alerts if item.get("severity") == "WARN"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _status_rank(status_value: str) -> int:
    normalized = str(status_value or "PASS").upper()
    return 2 if normalized == "BLOCK" else (1 if normalized == "WARN" else 0)


def _append_validation_timeline_event(config: dict, payload: dict) -> dict:
    timeline = list(config.get("items") or [])
    event = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    timeline.insert(0, event)
    config["items"] = timeline[:1000]
    return event


def _build_validation_center_payload(db: Session, *, window_hours: int = 24, limit: int = 200) -> dict:
    config = get_control_plane_config(db, config_key="validation_center_timeline", default={"items": []})
    items = list(config.get("items") or [])

    now_utc = datetime.now(timezone.utc)
    lower_bound = now_utc - timedelta(hours=window_hours)
    recent_items = [
        row for row in items if (_parse_iso_datetime(row.get("created_at")) or now_utc) >= lower_bound
    ]
    recent_items = recent_items[:limit]

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in recent_items:
        key = str(row.get("strategy_key") or "global")
        grouped[key].append(row)

    drift_alerts = []
    for strategy_key, logs in grouped.items():
        ordered_logs = sorted(logs, key=lambda item: item.get("created_at") or "")
        first_status = str((ordered_logs[0] or {}).get("net_status") or "PASS").upper()
        last_status = str((ordered_logs[-1] or {}).get("net_status") or "PASS").upper()
        if first_status == "PASS" and last_status in {"WARN", "BLOCK"}:
            drift_alerts.append(
                {
                    "strategy_key": strategy_key,
                    "from_status": first_status,
                    "to_status": last_status,
                    "reason_code": "validation_drift_pass_to_warn_or_block",
                    "event_count": len(ordered_logs),
                    "latest_at": (ordered_logs[-1] or {}).get("created_at"),
                    "severity": "high" if last_status == "BLOCK" else "medium",
                }
            )

    diff_items = []
    for strategy_key, logs in grouped.items():
        ordered_logs = sorted(logs, key=lambda item: item.get("created_at") or "")
        for previous, current in zip(ordered_logs, ordered_logs[1:]):
            if previous.get("net_status") != current.get("net_status"):
                diff_items.append(
                    {
                        "strategy_key": strategy_key,
                        "from_status": previous.get("net_status"),
                        "to_status": current.get("net_status"),
                        "from_at": previous.get("created_at"),
                        "to_at": current.get("created_at"),
                    }
                )

    summary = {
        "total_events": len(recent_items),
        "pass_count": sum(1 for row in recent_items if str(row.get("net_status") or "PASS").upper() == "PASS"),
        "warn_count": sum(1 for row in recent_items if str(row.get("net_status") or "PASS").upper() == "WARN"),
        "block_count": sum(1 for row in recent_items if str(row.get("net_status") or "PASS").upper() == "BLOCK"),
        "drift_alert_count": len(drift_alerts),
    }

    return {
        "window_hours": window_hours,
        "summary": summary,
        "timeline": recent_items,
        "diff_items": diff_items[:300],
        "drift_alerts": sorted(drift_alerts, key=lambda item: (_status_rank(item.get("to_status")), item.get("latest_at") or ""), reverse=True),
        "generated_at": now_utc.isoformat(),
    }


def _build_strategy_venue_heatmap_payload(db: Session, *, window_hours: int = 24) -> dict:
    runtime_config = _get_failover_runtime_config(db)
    routing_policy = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})

    now_utc = datetime.now(timezone.utc)
    lower_bound = now_utc - timedelta(hours=window_hours)

    decision_logs = [
        row
        for row in (runtime_config.get("routing_decision_logs") or [])
        if (_parse_iso_datetime(row.get("created_at")) or now_utc) >= lower_bound
    ]
    transition_logs = [
        row
        for row in (runtime_config.get("transition_logs") or [])
        if (_parse_iso_datetime(row.get("created_at")) or now_utc) >= lower_bound
    ]

    by_strategy: dict[str, dict] = {}
    for row in decision_logs:
        key = str(row.get("key") or "")
        strategy_bucket = by_strategy.setdefault(
            key,
            {
                "key": key,
                "user_id": row.get("user_id"),
                "strategy_id": row.get("strategy_id"),
                "market_type": row.get("market_type"),
                "environment": row.get("environment"),
                "selections": defaultdict(int),
                "total_routes": 0,
            },
        )
        selected = str(row.get("selected_venue") or "").strip().lower()
        if selected:
            strategy_bucket["selections"][selected] += 1
            strategy_bucket["total_routes"] += 1

    transition_count_map: dict[str, int] = defaultdict(int)
    for item in transition_logs:
        transition_count_map[str(item.get("key") or "")] += 1

    strategy_rows = []
    drift_rows = []
    routing_rules = routing_policy.get("rules") or {}
    for key, bucket in by_strategy.items():
        user_id = str(bucket.get("user_id") or "")
        strategy_id = str(bucket.get("strategy_id") or "")
        rule_key = f"{user_id}:{strategy_id}"
        routing_rule = dict(routing_rules.get(rule_key) or {})
        allocation_rows = list(routing_rule.get("capital_allocation") or [])
        allocation_map = {
            str((row or {}).get("venue") or "").strip().lower(): float((row or {}).get("weight") or (row or {}).get("allocation_pct") or 0)
            for row in allocation_rows
            if str((row or {}).get("venue") or "").strip()
        }

        total_routes = max(1, int(bucket.get("total_routes") or 0))
        distribution = []
        for venue, count in sorted((bucket.get("selections") or {}).items(), key=lambda pair: pair[1], reverse=True):
            actual_ratio = round(count / total_routes, 4)
            target_ratio = allocation_map.get(venue)
            drift = round(abs(actual_ratio - float(target_ratio)), 4) if target_ratio is not None else None
            distribution.append(
                {
                    "venue": venue,
                    "selected_count": count,
                    "actual_ratio": actual_ratio,
                    "target_ratio": target_ratio,
                    "allocation_drift": drift,
                }
            )
            if drift is not None:
                drift_rows.append({"strategy_key": key, "venue": venue, "allocation_drift": drift})

        strategy_rows.append(
            {
                "key": key,
                "user_id": bucket.get("user_id"),
                "strategy_id": bucket.get("strategy_id"),
                "market_type": bucket.get("market_type"),
                "environment": bucket.get("environment"),
                "route_churn_count": transition_count_map.get(key, 0),
                "total_routes": bucket.get("total_routes") or 0,
                "venue_distribution": distribution,
            }
        )

    top_drifts = sorted(drift_rows, key=lambda item: item.get("allocation_drift") or 0, reverse=True)[:30]
    return {
        "window_hours": window_hours,
        "strategies": strategy_rows,
        "top_allocation_drifts": top_drifts,
        "generated_at": now_utc.isoformat(),
    }


def _build_conflict_auto_remediation_drafts(db: Session) -> list[dict]:
    conflict_report = _build_conflict_detection_report(db)
    routing_policy = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})
    failover_policy = _get_failover_policy_config(db)

    drafts = []
    for alert in conflict_report.get("alerts") or []:
        reason_code = str(alert.get("reason_code") or "")
        entity_id = str(alert.get("entity_id") or "")
        draft = {
            "draft_id": f"{reason_code}:{entity_id}",
            "reason_code": reason_code,
            "entity_id": entity_id,
            "severity": alert.get("severity"),
            "message": alert.get("message"),
            "endpoint": None,
            "payload": None,
            "action_summary": None,
        }

        if reason_code == "default_venue_blocked":
            rule = dict((routing_policy.get("rules") or {}).get(entity_id) or {})
            default_venue = str(rule.get("default_venue") or "").strip().lower()
            blocked = [item for item in _normalize_venue_list(rule.get("blocked_venues") or []) if item != default_venue]
            draft["endpoint"] = "PUT /api/venues/admin/routing-policies"
            user_id, strategy_id = entity_id.split(":")[:2]
            draft["payload"] = {
                "user_id": user_id,
                "strategy_id": strategy_id,
                "default_venue": default_venue,
                "preferred_venues": _normalize_venue_list(rule.get("preferred_venues") or []),
                "blocked_venues": blocked,
                "capital_allocation": rule.get("capital_allocation") or [],
                "execution_policy_override": rule.get("execution_policy_override") or {},
            }
            draft["action_summary"] = "Default venue'yu blocked listeden kaldır"

        elif reason_code == "capital_allocation_missing":
            rule = dict((routing_policy.get("rules") or {}).get(entity_id) or {})
            venues = _normalize_venue_list([rule.get("default_venue"), *(rule.get("preferred_venues") or [])]) or ["binance"]
            weight = round(1 / len(venues), 4)
            user_id, strategy_id = entity_id.split(":")[:2]
            draft["endpoint"] = "PUT /api/venues/admin/routing-policies"
            draft["payload"] = {
                "user_id": user_id,
                "strategy_id": strategy_id,
                "default_venue": str(rule.get("default_venue") or venues[0]).strip().lower(),
                "preferred_venues": _normalize_venue_list(rule.get("preferred_venues") or []),
                "blocked_venues": _normalize_venue_list(rule.get("blocked_venues") or []),
                "capital_allocation": [{"venue": venue, "weight": weight} for venue in venues],
                "execution_policy_override": rule.get("execution_policy_override") or {},
            }
            draft["action_summary"] = "Eksik capital_allocation için eşit dağılım öner"

        elif reason_code == "primary_force_disabled":
            rule = dict((failover_policy.get("rules") or {}).get(entity_id) or {})
            manual_override = dict(rule.get("manual_override") or {})
            primary_venue = str(rule.get("primary_venue") or "").strip().lower()
            force_disable = [item for item in _normalize_venue_list(manual_override.get("force_disable") or []) if item != primary_venue]
            draft["endpoint"] = "POST /api/venues/admin/failover/manual-override"
            user_id, strategy_id, market_type, environment = entity_id.split(":")[:4]
            draft["payload"] = {
                "user_id": user_id,
                "strategy_id": strategy_id,
                "market_type": market_type,
                "environment": environment,
                "force_route": manual_override.get("force_route"),
                "force_disable": force_disable,
                "reason": "auto_remediation_primary_force_disabled",
                "clear_override": False,
            }
            draft["action_summary"] = "Primary venue'yu force_disable listesinden çıkar"

        elif reason_code == "primary_secondary_same":
            rule = dict((failover_policy.get("rules") or {}).get(entity_id) or {})
            fallback_chain = _normalize_venue_list(rule.get("fallback_chain") or [])
            new_secondary = fallback_chain[0] if fallback_chain else None
            user_id, strategy_id, market_type, environment = entity_id.split(":")[:4]
            draft["endpoint"] = "PUT /api/venues/admin/failover-policies"
            draft["payload"] = {
                "user_id": user_id,
                "strategy_id": strategy_id,
                "market_type": market_type,
                "environment": environment,
                "primary_venue": rule.get("primary_venue"),
                "secondary_venue": new_secondary,
                "fallback_chain": fallback_chain,
                "auto_reroute_enabled": bool(rule.get("auto_reroute_enabled", True)),
                "auto_trigger_thresholds": rule.get("auto_trigger_thresholds") or {"latency_ms": 1200, "error_rate_pct": 20, "validation_failure_pct": 25},
                "manual_override": rule.get("manual_override") or {"force_route": None, "force_disable": [], "reason": None},
            }
            draft["action_summary"] = "Secondary venue değerini primary'den farklı olacak şekilde güncelle"

        if draft.get("endpoint"):
            drafts.append(draft)

    return drafts


@router.get("/admin/exchanges", response_model=list[ExchangeRegistryResponse])
def admin_list_exchanges(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return db.query(ExchangeRegistry).order_by(ExchangeRegistry.exchange_code.asc()).all()


@router.post("/admin/exchanges", response_model=ExchangeRegistryResponse, status_code=status.HTTP_201_CREATED)
def admin_create_exchange(
    payload: ExchangeRegistryCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    exchange_code = payload.exchange_code.strip().lower()
    if not exchange_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exchange_code zorunlu")

    existing = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exchange zaten kayıtlı")

    market_types = sorted({item.strip().lower() for item in payload.supported_market_types if item.strip()})
    row = ExchangeRegistry(
        id=str(uuid.uuid4()),
        exchange_code=exchange_code,
        exchange_name=payload.exchange_name.strip(),
        status=payload.status.strip().lower(),
        supported_market_types=market_types,
        supports_testnet=payload.supports_testnet,
        supports_live=payload.supports_live,
        health_status=payload.health_status.strip().lower(),
        rate_limit_status=payload.rate_limit_status.strip().lower(),
        adapter_version=payload.adapter_version.strip(),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_exchange_created",
        entity_type="exchange_registry",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"exchange_code": row.exchange_code, "exchange_name": row.exchange_name},
    )
    return row


@router.patch("/admin/exchanges/{exchange_code}", response_model=ExchangeRegistryResponse)
def admin_update_exchange(
    exchange_code: str,
    payload: ExchangeRegistryUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code.lower()).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    row.status = payload.status
    row.health_status = payload.health_status
    row.rate_limit_status = payload.rate_limit_status
    row.adapter_version = payload.adapter_version
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_exchange_updated",
        entity_type="exchange_registry",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange_code": row.exchange_code,
            "status": row.status,
            "health_status": row.health_status,
            "rate_limit_status": row.rate_limit_status,
            "adapter_version": row.adapter_version,
        },
    )
    return row


@router.delete("/admin/exchanges/{exchange_code}")
def admin_delete_exchange(
    exchange_code: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_code = exchange_code.lower()
    row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == normalized_code).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    capabilities_deleted = (
        db.query(ExchangeCapability).filter(ExchangeCapability.exchange_code == normalized_code).delete()
    )
    markets_deleted = db.query(AllowedMarket).filter(AllowedMarket.exchange_code == normalized_code).delete()
    assignments_deleted = (
        db.query(UserVenueAssignment).filter(UserVenueAssignment.exchange_code == normalized_code).delete()
    )
    db.delete(row)
    db.commit()

    create_audit_log(
        db,
        action="venue_exchange_deleted",
        entity_type="exchange_registry",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "exchange_code": normalized_code,
            "capabilities_deleted": capabilities_deleted,
            "allowed_markets_deleted": markets_deleted,
            "assignments_deleted": assignments_deleted,
        },
    )
    return {"deleted": True, "exchange_code": normalized_code}


@router.get("/admin/capabilities", response_model=list[ExchangeCapabilityResponse])
def admin_list_capabilities(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return (
        db.query(ExchangeCapability)
        .order_by(ExchangeCapability.exchange_code.asc(), ExchangeCapability.market_type.asc())
        .all()
    )


@router.post("/admin/capabilities", response_model=ExchangeCapabilityResponse, status_code=status.HTTP_201_CREATED)
def admin_create_capability(
    payload: ExchangeCapabilityCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    exchange_code = payload.exchange_code.strip().lower()
    market_type = payload.market_type.strip().lower()

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code).first()
    if exchange_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    existing = (
        db.query(ExchangeCapability)
        .filter(ExchangeCapability.exchange_code == exchange_code, ExchangeCapability.market_type == market_type)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Capability zaten kayıtlı")

    row = ExchangeCapability(
        id=str(uuid.uuid4()),
        exchange_code=exchange_code,
        market_type=market_type,
        supports_spot=payload.supports_spot,
        supports_futures=payload.supports_futures,
        supports_test_order=payload.supports_test_order,
        supports_quote_qty=payload.supports_quote_qty,
        supports_reduce_only=payload.supports_reduce_only,
        supports_leverage=payload.supports_leverage,
        supports_margin_mode=payload.supports_margin_mode,
        supports_hedge_mode=payload.supports_hedge_mode,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_capability_created",
        entity_type="exchange_capability",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"exchange_code": row.exchange_code, "market_type": row.market_type},
    )
    return row


@router.put("/admin/capabilities/{capability_id}", response_model=ExchangeCapabilityResponse)
def admin_update_capability(
    capability_id: str,
    payload: ExchangeCapabilityUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(ExchangeCapability).filter(ExchangeCapability.id == capability_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability bulunamadı")

    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_capability_updated",
        entity_type="exchange_capability",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"exchange_code": row.exchange_code, "market_type": row.market_type, **payload.model_dump()},
    )
    return row


@router.delete("/admin/capabilities/{capability_id}")
def admin_delete_capability(
    capability_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(ExchangeCapability).filter(ExchangeCapability.id == capability_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability bulunamadı")

    db.delete(row)
    db.commit()
    create_audit_log(
        db,
        action="venue_capability_deleted",
        entity_type="exchange_capability",
        entity_id=capability_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"exchange_code": row.exchange_code, "market_type": row.market_type},
    )
    return {"deleted": True, "capability_id": capability_id}


@router.get("/admin/allowed-markets", response_model=list[AllowedMarketResponse])
def admin_list_allowed_markets(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return db.query(AllowedMarket).order_by(AllowedMarket.exchange_code.asc(), AllowedMarket.market_type.asc(), AllowedMarket.environment.asc()).all()


@router.post("/admin/allowed-markets", response_model=AllowedMarketResponse, status_code=status.HTTP_201_CREATED)
def admin_create_allowed_market(
    payload: AllowedMarketCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    exchange_code = payload.exchange_code.strip().lower()
    market_type = payload.market_type.strip().lower()
    environment = payload.environment.strip().lower()

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code).first()
    if exchange_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    existing = (
        db.query(AllowedMarket)
        .filter(
            AllowedMarket.exchange_code == exchange_code,
            AllowedMarket.market_type == market_type,
            AllowedMarket.environment == environment,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Allowed market zaten kayıtlı")

    row = AllowedMarket(
        id=str(uuid.uuid4()),
        exchange_code=exchange_code,
        market_type=market_type,
        environment=environment,
        enabled=payload.enabled,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_allowed_market_created",
        entity_type="allowed_market",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange_code": row.exchange_code,
            "market_type": row.market_type,
            "environment": row.environment,
            "enabled": row.enabled,
        },
    )
    return row


@router.put("/admin/allowed-markets/{allowed_market_id}", response_model=AllowedMarketResponse)
def admin_toggle_allowed_market(
    allowed_market_id: str,
    payload: AllowedMarketToggle,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(AllowedMarket).filter(AllowedMarket.id == allowed_market_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed market kaydı bulunamadı")

    row.enabled = payload.enabled
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_allowed_market_toggled",
        entity_type="allowed_market",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange_code": row.exchange_code,
            "market_type": row.market_type,
            "environment": row.environment,
            "enabled": row.enabled,
        },
    )
    return row


@router.delete("/admin/allowed-markets/{allowed_market_id}")
def admin_delete_allowed_market(
    allowed_market_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(AllowedMarket).filter(AllowedMarket.id == allowed_market_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed market kaydı bulunamadı")

    db.delete(row)
    db.commit()
    create_audit_log(
        db,
        action="venue_allowed_market_deleted",
        entity_type="allowed_market",
        entity_id=allowed_market_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "exchange_code": row.exchange_code,
            "market_type": row.market_type,
            "environment": row.environment,
        },
    )
    return {"deleted": True, "allowed_market_id": allowed_market_id}


@router.get("/admin/user-assignments", response_model=list[UserVenueAssignmentResponse])
def admin_list_user_assignments(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    user_id: str | None = Query(default=None),
):
    query = db.query(UserVenueAssignment)
    if user_id:
        query = query.filter(UserVenueAssignment.user_id == user_id)
    return query.order_by(UserVenueAssignment.updated_at.desc()).all()


@router.put("/admin/user-assignments", response_model=UserVenueAssignmentResponse)
def admin_upsert_user_assignment(
    payload: UserVenueAssignmentUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    seed_binance_venue_registry(db)
    target_user = db.query(User).filter(User.id == payload.user_id).first()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == payload.exchange_code.lower()).first()
    if exchange_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    row = (
        db.query(UserVenueAssignment)
        .filter(UserVenueAssignment.user_id == payload.user_id, UserVenueAssignment.exchange_code == payload.exchange_code.lower())
        .first()
    )
    if row is None:
        row = UserVenueAssignment(
            user_id=payload.user_id,
            exchange_code=payload.exchange_code.lower(),
        )
        db.add(row)

    row.spot_allowed = payload.spot_allowed
    row.futures_allowed = payload.futures_allowed
    row.testnet_allowed = payload.testnet_allowed
    row.live_allowed = payload.live_allowed
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_user_assignment_updated",
        entity_type="user_venue_assignment",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=payload.model_dump(),
    )
    return row


@router.delete("/admin/user-assignments/{assignment_id}")
def admin_delete_user_assignment(
    assignment_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(UserVenueAssignment).filter(UserVenueAssignment.id == assignment_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User assignment bulunamadı")

    db.delete(row)
    db.commit()
    create_audit_log(
        db,
        action="venue_user_assignment_deleted",
        entity_type="user_venue_assignment",
        entity_id=assignment_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"user_id": row.user_id, "exchange_code": row.exchange_code},
    )
    return {"deleted": True, "assignment_id": assignment_id}


@router.get("/admin/health-summary", response_model=VenueHealthSummaryResponse)
def admin_health_summary(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return VenueHealthSummaryResponse(**venue_health_summary(db))


@router.post("/admin/capability-discovery")
def admin_capability_discovery(
    payload: CapabilityDiscoveryRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    discovery = discover_exchange_capabilities(
        exchange_code=payload.exchange_code,
        market_type=payload.market_type,
        environment=payload.environment,
        symbols=payload.symbols,
    )
    matrix = get_control_plane_config(db, config_key="capability_matrix", default={})
    key = f"{payload.exchange_code.lower()}:{payload.market_type.lower()}:{payload.environment.lower()}"
    old_value = matrix.get(key)
    matrix[key] = discovery
    upsert_control_plane_config(db, config_key="capability_matrix", payload=matrix, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="venue_capability_discovery_synced",
        entity_type="venue_capability_matrix",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_value, "new_value": discovery},
    )
    return {
        "net_status": "PASS",
        "reason_codes": discovery.get("reason_codes") or [],
        "remediation_suggestions": [],
        "checks": [
            {
                "name": "adapter_capability_discovery",
                "status": "PASS",
                "reason_code": "discovery_synced",
                "severity": "low",
                "remediation_suggestions": [],
            }
        ],
        "capability": discovery,
    }


@router.get("/admin/capability-matrix")
def admin_get_capability_matrix(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_control_plane_config(db, config_key="capability_matrix", default={})


@router.put("/admin/capability-matrix/override")
def admin_upsert_capability_matrix_override(
    payload: CapabilityMatrixOverrideRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    matrix = get_control_plane_config(db, config_key="capability_matrix", default={})
    key = f"{payload.exchange_code.lower()}:{payload.market_type.lower()}:{payload.environment.lower()}"
    capability_entry = dict((matrix or {}).get(key) or {})
    symbol_capabilities = list(capability_entry.get("symbol_capabilities") or [])

    target_symbol = str(payload.symbol or "").upper()
    old_symbol_value = None
    target_index = None
    for index, item in enumerate(symbol_capabilities):
        if str((item or {}).get("symbol") or "").upper() == target_symbol:
            target_index = index
            old_symbol_value = dict(item or {})
            break

    if target_index is None:
        symbol_capabilities.append({"symbol": target_symbol})
        target_index = len(symbol_capabilities) - 1

    existing = dict(symbol_capabilities[target_index] or {})
    updated = {
        **existing,
        "symbol": target_symbol,
        "support_level": str(payload.support_level or existing.get("support_level") or "partial").strip().lower(),
        "manual_override": True,
        "override_note": str(payload.note or "").strip() or existing.get("override_note") or "",
        "override_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    optional_flags = {
        "supports_leverage": payload.supports_leverage,
        "supports_reduce_only": payload.supports_reduce_only,
        "supports_margin_mode": payload.supports_margin_mode,
        "supports_hedge_mode": payload.supports_hedge_mode,
    }
    for field, value in optional_flags.items():
        if value is not None:
            updated[field] = bool(value)
        elif field not in updated:
            updated[field] = False

    if updated["support_level"] not in {"supported", "partial", "unsupported"}:
        updated["support_level"] = "partial"

    symbol_capabilities[target_index] = updated
    capability_entry["symbol_capabilities"] = symbol_capabilities
    capability_entry["updated_at"] = datetime.now(timezone.utc).isoformat()

    matrix[key] = capability_entry
    upsert_control_plane_config(db, config_key="capability_matrix", payload=matrix, actor_user_id=current_admin.id)

    create_audit_log(
        db,
        action="venue_capability_matrix_override_updated",
        entity_type="venue_capability_matrix",
        entity_id=f"{key}:{target_symbol}",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "old_value": old_symbol_value,
            "new_value": updated,
            "diff_keys": _extract_diff_keys(old_symbol_value or {}, updated),
        },
    )

    return {
        "updated": True,
        "key": key,
        "symbol": target_symbol,
        "override": updated,
        "capability": capability_entry,
    }


@router.put("/admin/market-policy-layer")
def admin_upsert_market_policy_layer(
    payload: MarketPolicyLayerUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = get_control_plane_config(db, config_key="market_policy", default={"rules": {}})
    rules = dict(policy.get("rules") or {})
    key = f"{payload.exchange_code.lower()}:{payload.market_type.lower()}:{payload.environment.lower()}"
    old_value = rules.get(key)
    rules[key] = {
        "symbol_rules": payload.symbol_rules,
        "restricted_symbol_classes": payload.restricted_symbol_classes,
        "risk_tier_defaults": payload.risk_tier_defaults,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    policy["rules"] = rules
    upsert_control_plane_config(db, config_key="market_policy", payload=policy, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="venue_market_policy_updated",
        entity_type="venue_market_policy",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_value, "new_value": rules[key]},
    )
    return {"updated": True, "key": key, "policy": rules[key]}


@router.get("/admin/market-policy-layer")
def admin_get_market_policy_layer(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_control_plane_config(db, config_key="market_policy", default={"rules": {}})


@router.put("/admin/routing-policies")
def admin_upsert_routing_policies(
    payload: RoutingPolicyUpsertRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    routing = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})
    rules = dict(routing.get("rules") or {})
    key = f"{payload.user_id}:{payload.strategy_id}"
    old_value = rules.get(key)
    rules[key] = {
        "default_venue": payload.default_venue,
        "preferred_venues": payload.preferred_venues,
        "blocked_venues": payload.blocked_venues,
        "capital_allocation": payload.capital_allocation,
        "execution_policy_override": payload.execution_policy_override,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    routing["rules"] = rules
    upsert_control_plane_config(db, config_key="routing_policy", payload=routing, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="venue_routing_policy_updated",
        entity_type="venue_routing_policy",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_value, "new_value": rules[key]},
    )
    return {"updated": True, "key": key, "routing_rule": rules[key]}


@router.get("/admin/routing-policies")
def admin_get_routing_policies(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})


@router.put("/admin/failover-policies")
def admin_upsert_failover_policy(
    payload: FailoverPolicyUpsertRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy_config = _get_failover_policy_config(db)
    rules = dict(policy_config.get("rules") or {})
    key = _failover_rule_key(
        user_id=payload.user_id,
        strategy_id=payload.strategy_id,
        market_type=payload.market_type,
        environment=payload.environment,
    )
    old_value = rules.get(key)

    manual_override = payload.manual_override.model_dump() if payload.manual_override else {"force_route": None, "force_disable": [], "reason": None}
    rules[key] = {
        "user_id": payload.user_id,
        "strategy_id": payload.strategy_id,
        "market_type": payload.market_type.lower(),
        "environment": payload.environment.lower(),
        "primary_venue": payload.primary_venue.lower(),
        "secondary_venue": (payload.secondary_venue or "").lower() or None,
        "fallback_chain": _normalize_venue_list(payload.fallback_chain),
        "auto_reroute_enabled": bool(payload.auto_reroute_enabled),
        "auto_trigger_thresholds": payload.auto_trigger_thresholds.model_dump(),
        "manual_override": {
            "force_route": str(manual_override.get("force_route") or "").strip().lower() or None,
            "force_disable": _normalize_venue_list(manual_override.get("force_disable") or []),
            "reason": str(manual_override.get("reason") or "").strip() or None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    policy_config["rules"] = rules
    upsert_control_plane_config(db, config_key="failover_policy", payload=policy_config, actor_user_id=current_admin.id)

    runtime_config = _get_failover_runtime_config(db)
    health_payload = _build_operational_health_payload(db)
    health_map = {item.get("exchange"): item for item in (health_payload.get("operational_scores") or [])}
    plan = _resolve_failover_plan(rules[key], health_map=health_map)
    transition = _record_failover_transition(runtime_config, key=key, plan=plan, actor_user_id=current_admin.id)
    upsert_control_plane_config(db, config_key="failover_runtime", payload=runtime_config, actor_user_id=current_admin.id)

    create_audit_log(
        db,
        action="venue_failover_policy_updated",
        entity_type="venue_failover_policy",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_value, "new_value": rules[key]},
    )
    if transition:
        create_audit_log(
            db,
            action="venue_failover_transition",
            entity_type="venue_failover_state",
            entity_id=key,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            details=transition,
        )

    return {
        "updated": True,
        "key": key,
        "failover_rule": rules[key],
        "failover_state": (runtime_config.get("runtime_state") or {}).get(key),
        "transition_event": transition,
    }


@router.post("/admin/failover/manual-override")
def admin_apply_failover_manual_override(
    payload: FailoverManualOverrideRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy_config = _get_failover_policy_config(db)
    rules = dict(policy_config.get("rules") or {})
    key = _failover_rule_key(
        user_id=payload.user_id,
        strategy_id=payload.strategy_id,
        market_type=payload.market_type,
        environment=payload.environment,
    )
    rule = dict(rules.get(key) or {})
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="failover_policy_not_found")

    old_manual = dict(rule.get("manual_override") or {})
    if payload.clear_override:
        rule["manual_override"] = {"force_route": None, "force_disable": [], "reason": None, "updated_at": datetime.now(timezone.utc).isoformat()}
    else:
        rule["manual_override"] = {
            "force_route": str(payload.force_route or "").strip().lower() or None,
            "force_disable": _normalize_venue_list(payload.force_disable),
            "reason": str(payload.reason or "").strip() or None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    rule["updated_at"] = datetime.now(timezone.utc).isoformat()
    rules[key] = rule
    policy_config["rules"] = rules
    upsert_control_plane_config(db, config_key="failover_policy", payload=policy_config, actor_user_id=current_admin.id)

    runtime_config = _get_failover_runtime_config(db)
    health_payload = _build_operational_health_payload(db)
    health_map = {item.get("exchange"): item for item in (health_payload.get("operational_scores") or [])}
    plan = _resolve_failover_plan(rule, health_map=health_map)
    transition = _record_failover_transition(runtime_config, key=key, plan=plan, actor_user_id=current_admin.id)
    upsert_control_plane_config(db, config_key="failover_runtime", payload=runtime_config, actor_user_id=current_admin.id)

    create_audit_log(
        db,
        action="venue_failover_manual_override_applied",
        entity_type="venue_failover_policy",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_manual, "new_value": rule.get("manual_override")},
    )
    if transition:
        create_audit_log(
            db,
            action="venue_failover_transition",
            entity_type="venue_failover_state",
            entity_id=key,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            details=transition,
        )

    return {
        "updated": True,
        "key": key,
        "manual_override": rule.get("manual_override"),
        "failover_state": (runtime_config.get("runtime_state") or {}).get(key),
        "transition_event": transition,
    }


@router.get("/admin/failover-policies")
def admin_get_failover_policies(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    user_id: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    market_type: str | None = Query(default=None),
    environment: str | None = Query(default=None),
):
    policy_config = _get_failover_policy_config(db)
    runtime_config = _get_failover_runtime_config(db)
    rules = dict(policy_config.get("rules") or {})

    def _match(key: str) -> bool:
        parts = key.split(":")
        if len(parts) < 4:
            return False
        k_user, k_strategy, k_market, k_env = parts[0], parts[1], parts[2], parts[3]
        if user_id and k_user != user_id:
            return False
        if strategy_id and k_strategy != strategy_id:
            return False
        if market_type and k_market != market_type.lower():
            return False
        if environment and k_env != environment.lower():
            return False
        return True

    filtered_rules = {key: value for key, value in rules.items() if _match(key)}
    runtime_state = {key: value for key, value in (runtime_config.get("runtime_state") or {}).items() if key in filtered_rules}
    transition_logs = [row for row in (runtime_config.get("transition_logs") or []) if row.get("key") in filtered_rules][:120]
    routing_logs = [row for row in (runtime_config.get("routing_decision_logs") or []) if row.get("key") in filtered_rules][:120]

    return {
        "rules": filtered_rules,
        "runtime_state": runtime_state,
        "transition_logs": transition_logs,
        "routing_decision_logs": routing_logs,
    }


@router.get("/admin/failover-state")
def admin_get_failover_state(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    user_id: str = Query(...),
    strategy_id: str = Query(...),
    market_type: str = Query(...),
    environment: str = Query(default="testnet"),
    log_limit: int = Query(default=20, ge=1, le=200),
):
    key = _failover_rule_key(user_id=user_id, strategy_id=strategy_id, market_type=market_type, environment=environment)
    policy_config = _get_failover_policy_config(db)
    runtime_config = _get_failover_runtime_config(db)
    rule = (policy_config.get("rules") or {}).get(key)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="failover_policy_not_found")

    health_payload = _build_operational_health_payload(db)
    health_map = {item.get("exchange"): item for item in (health_payload.get("operational_scores") or [])}
    plan = _resolve_failover_plan(rule, health_map=health_map)
    transition_logs = [row for row in (runtime_config.get("transition_logs") or []) if row.get("key") == key][:log_limit]
    routing_logs = [row for row in (runtime_config.get("routing_decision_logs") or []) if row.get("key") == key][:log_limit]

    return {
        "key": key,
        "failover_rule": rule,
        "computed_state": plan,
        "runtime_state": (runtime_config.get("runtime_state") or {}).get(key),
        "transition_logs": transition_logs,
        "routing_decision_logs": routing_logs,
    }


@router.post("/admin/routing-preview-v2")
def admin_routing_preview_v2(
    payload: RoutingPreviewRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    routing = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})
    key = f"{payload.user_id}:{payload.strategy_id}"
    rule = (routing.get("rules") or {}).get(key) or {}

    default_venue = str(rule.get("default_venue") or "binance").strip().lower()
    preferred_venues = [str(item).strip().lower() for item in (rule.get("preferred_venues") or []) if str(item).strip()]
    blocked_venues = {str(item).strip().lower() for item in (rule.get("blocked_venues") or []) if str(item).strip()}
    allocation_rows = list(rule.get("capital_allocation") or [])
    allocation_weights = {
        str((row or {}).get("venue") or "").strip().lower(): _safe_float_value((row or {}).get("weight") or (row or {}).get("allocation_pct") or 0)
        for row in allocation_rows
        if str((row or {}).get("venue") or "").strip()
    }

    market_policy = get_control_plane_config(db, config_key="market_policy", default={"rules": {}})
    market_policy_rules = market_policy.get("rules") or {}
    capability_matrix = get_control_plane_config(db, config_key="capability_matrix", default={})
    health_payload = _build_operational_health_payload(db)
    health_map = {item.get("exchange"): item for item in (health_payload.get("operational_scores") or [])}

    failover_policy_config = _get_failover_policy_config(db)
    failover_runtime_config = _get_failover_runtime_config(db)
    failover_key = _failover_rule_key(
        user_id=payload.user_id,
        strategy_id=payload.strategy_id,
        market_type=payload.market_type,
        environment=payload.environment,
    )
    failover_rule = dict((failover_policy_config.get("rules") or {}).get(failover_key) or {})
    has_explicit_failover_policy = bool(failover_rule)
    if not failover_rule:
        failover_rule = {
            "user_id": payload.user_id,
            "strategy_id": payload.strategy_id,
            "market_type": payload.market_type,
            "environment": payload.environment,
            "primary_venue": default_venue,
            "secondary_venue": preferred_venues[0] if preferred_venues else None,
            "fallback_chain": preferred_venues[1:] if len(preferred_venues) > 1 else [],
            "auto_reroute_enabled": True,
            "auto_trigger_thresholds": {"latency_ms": 1200, "error_rate_pct": 20, "validation_failure_pct": 25},
            "manual_override": {"force_route": None, "force_disable": [], "reason": None},
        }
    failover_plan = _resolve_failover_plan(failover_rule, health_map=health_map)
    failover_transition = _record_failover_transition(
        failover_runtime_config,
        key=failover_key,
        plan=failover_plan,
        actor_user_id=current_admin.id,
    )

    exchange_rows = db.query(ExchangeRegistry).order_by(ExchangeRegistry.exchange_code.asc()).all()
    active_exchange_codes = [row.exchange_code for row in exchange_rows if str(row.status or "").lower() == "active"]
    candidate_venues: list[str] = []
    for venue in [failover_plan.get("active_venue"), *(failover_plan.get("fallback_chain") or []), default_venue, *preferred_venues, *active_exchange_codes]:
        normalized = str(venue or "").strip().lower()
        if normalized and normalized not in candidate_venues:
            candidate_venues.append(normalized)
    if not candidate_venues:
        candidate_venues = ["binance"]

    for disabled_venue in failover_plan.get("forced_disable") or []:
        blocked_venues.add(str(disabled_venue).strip().lower())

    resolved: dict[str, Any] = {}
    resolution_error: str | None = None
    try:
        resolved = resolve_exchange_credentials(
            db,
            user_id=payload.user_id,
            exchange=default_venue,
            market_type=payload.market_type,
            environment=payload.environment,
            purpose="execution",
            symbol=payload.symbol,
            include_secrets=False,
        )
    except Exception as exc:  # noqa: BLE001
        resolution_error = str(exc)
        resolved = {"exchange": default_venue, "source": "unresolved", "reason_code": resolution_error}

    resolved_exchange = str(resolved.get("exchange") or "").strip().lower()
    if resolved_exchange and resolved_exchange not in candidate_venues:
        candidate_venues.append(resolved_exchange)

    candidates = []
    for index, exchange in enumerate(candidate_venues):
        policy_effect = _policy_effect_for_symbol(
            market_policy_rules,
            exchange=exchange,
            market_type=payload.market_type,
            environment=payload.environment,
            symbol=payload.symbol,
        )
        capability_effect = _capability_effect_for_symbol(
            db,
            capability_matrix,
            exchange=exchange,
            market_type=payload.market_type,
            environment=payload.environment,
            symbol=payload.symbol,
        )
        health_effect = health_map.get(exchange) or {
            "exchange": exchange,
            "health_score": 50,
            "health_status": "unknown",
            "rate_limit_status": "unknown",
            "latency_ms_p95": None,
            "validation_success_rate": None,
            "rate_limit_pressure": 0,
            "websocket_sync_health": "unknown",
            "orderbook_sync_health": "unknown",
            "reason_codes": ["exchange_health_unknown"],
        }

        route_score = 100
        reason_codes: list[str] = []
        decision_factors: list[dict] = []

        if exchange == failover_plan.get("active_venue"):
            route_score += 12
            decision_factors.append({"name": "failover_active_venue", "status": "PASS", "impact": "+", "detail": "Failover active venue seçimi."})
        elif exchange in (failover_plan.get("fallback_chain") or []):
            route_score += max(1, 8 - index)
            decision_factors.append({"name": "failover_fallback_chain", "status": "WARN", "impact": "+", "detail": "Failover fallback chain adayı."})

        if exchange == default_venue:
            decision_factors.append({"name": "default_venue", "status": "PASS", "impact": "+", "detail": "Default venue önceliği uygulandı."})
            route_score += 6
        elif preferred_venues:
            if exchange in preferred_venues:
                pref_rank = preferred_venues.index(exchange)
                bonus = max(2, 8 - (pref_rank * 2))
                route_score += bonus
                decision_factors.append({"name": "preferred_venue_rank", "status": "PASS", "impact": "+", "detail": f"Preferred rank {pref_rank + 1}"})
            else:
                route_score -= 8
                _add_reason(reason_codes, "selected_venue_not_in_preferred")
                decision_factors.append({"name": "preferred_venue_rank", "status": "WARN", "impact": "-", "detail": "Venue preferred listesinde değil."})

        if exchange in blocked_venues:
            route_score -= 100
            _add_reason(reason_codes, "selected_venue_blocked_by_routing_policy")
            decision_factors.append({"name": "routing_policy_blocked", "status": "BLOCK", "impact": "-", "detail": "Venue blocked_venues içinde."})

        if bool(policy_effect.get("is_blocked")):
            route_score -= 90
            for code in policy_effect.get("reason_codes") or []:
                _add_reason(reason_codes, code)
            decision_factors.append(
                {
                    "name": "market_policy",
                    "status": "BLOCK",
                    "impact": "-",
                    "detail": f"Policy action={policy_effect.get('symbol_action')} / class={policy_effect.get('symbol_class')}",
                }
            )
        else:
            decision_factors.append({"name": "market_policy", "status": "PASS", "impact": "+", "detail": "Symbol policy allow."})

        support_level = str(capability_effect.get("support_level") or "partial").lower()
        if support_level == "unsupported":
            route_score -= 75
            _add_reason(reason_codes, "capability_unsupported")
            decision_factors.append({"name": "capability", "status": "BLOCK", "impact": "-", "detail": "Capability unsupported."})
        elif support_level == "partial":
            route_score -= 18
            _add_reason(reason_codes, "capability_partial_support")
            decision_factors.append({"name": "capability", "status": "WARN", "impact": "-", "detail": "Capability partial support."})
        else:
            route_score += 4
            decision_factors.append({"name": "capability", "status": "PASS", "impact": "+", "detail": "Capability supported."})

        health_status = str(health_effect.get("health_status") or "unknown").lower()
        if health_status == "down":
            route_score -= 75
            _add_reason(reason_codes, "exchange_operational_down")
            decision_factors.append({"name": "operational_health", "status": "BLOCK", "impact": "-", "detail": "Venue operational health down."})
        elif health_status == "degraded":
            route_score -= 22
            _add_reason(reason_codes, "exchange_operational_degraded")
            decision_factors.append({"name": "operational_health", "status": "WARN", "impact": "-", "detail": "Venue operational health degraded."})
        else:
            decision_factors.append({"name": "operational_health", "status": "PASS", "impact": "+", "detail": "Venue operational health healthy."})

        latency_p95 = _safe_float_value(health_effect.get("latency_ms_p95"))
        if latency_p95 is not None and latency_p95 >= 1200:
            route_score -= 12
            _add_reason(reason_codes, "exchange_latency_high")
            decision_factors.append({"name": "latency_ms_p95", "status": "WARN", "impact": "-", "detail": f"p95 latency={latency_p95}ms"})

        validation_rate = _safe_float_value(health_effect.get("validation_success_rate"))
        if validation_rate is not None and validation_rate < 85:
            route_score -= 10
            _add_reason(reason_codes, "exchange_validation_success_low")
            decision_factors.append({"name": "validation_success_rate", "status": "WARN", "impact": "-", "detail": f"validation_success_rate={validation_rate}%"})

        pressure = int(health_effect.get("rate_limit_pressure") or 0)
        if pressure >= 80:
            route_score -= 10
            _add_reason(reason_codes, "exchange_rate_limit_pressure_high")
            decision_factors.append({"name": "rate_limit_pressure", "status": "WARN", "impact": "-", "detail": f"pressure={pressure}"})

        allocation_weight = allocation_weights.get(exchange)
        if allocation_weight is None:
            route_score -= 4
            _add_reason(reason_codes, "allocation_state_missing")
            decision_factors.append({"name": "allocation_state", "status": "WARN", "impact": "-", "detail": "Bu venue için allocation tanımı yok."})
        else:
            normalized_weight = float(allocation_weight)
            if normalized_weight <= 0:
                route_score -= 24
                _add_reason(reason_codes, "allocation_weight_zero")
                decision_factors.append({"name": "allocation_state", "status": "BLOCK", "impact": "-", "detail": "Allocation weight <= 0"})
            elif normalized_weight < 0.15:
                route_score -= 8
                _add_reason(reason_codes, "allocation_weight_low")
                decision_factors.append({"name": "allocation_state", "status": "WARN", "impact": "-", "detail": f"Allocation weight düşük: {normalized_weight}"})
            else:
                bonus = min(14, int(round(normalized_weight * 16)))
                route_score += bonus
                decision_factors.append({"name": "allocation_state", "status": "PASS", "impact": "+", "detail": f"Allocation weight: {normalized_weight}"})

        route_score = max(0, min(100, int(round(route_score))))
        has_block_reason = any(
            code in {
                "selected_venue_blocked_by_routing_policy",
                "symbol_policy_blocked",
                "restricted_symbol_class_blocked",
                "capability_unsupported",
                "exchange_operational_down",
                "allocation_weight_zero",
            }
            for code in reason_codes
        )
        has_warn_reason = any(
            code in {
                "selected_venue_not_in_preferred",
                "capability_partial_support",
                "exchange_operational_degraded",
                "exchange_latency_high",
                "exchange_validation_success_low",
                "exchange_rate_limit_pressure_high",
                "allocation_state_missing",
                "allocation_weight_low",
            }
            for code in reason_codes
        )
        status_value = "BLOCK" if has_block_reason else ("WARN" if has_warn_reason or route_score < 80 else "PASS")

        candidates.append(
            {
                "exchange": exchange,
                "status": status_value,
                "route_score": route_score,
                "reason_codes": reason_codes,
                "decision_factors": decision_factors,
                "policy_effect": policy_effect,
                "capability_effect": capability_effect,
                "health_effect": health_effect,
                "allocation_state": {"weight": allocation_weight, "source": "routing_policy.capital_allocation"},
            }
        )

    ordered = sorted(
        candidates,
        key=lambda item: (
            _STATUS_RANK.get(str(item.get("status") or "BLOCK"), 2),
            -int(item.get("route_score") or 0),
            str(item.get("exchange") or ""),
        ),
    )
    selected_path = ordered[0] if ordered else {
        "exchange": default_venue,
        "status": "BLOCK",
        "route_score": 0,
        "reason_codes": ["no_route_candidate"],
        "decision_factors": [],
        "policy_effect": {},
        "capability_effect": {},
        "health_effect": {},
        "allocation_state": {"weight": None, "source": "routing_policy.capital_allocation"},
    }
    alternative_paths = ordered[1:]

    validation_report = _build_execution_validation_report(db)

    reason_codes = list(selected_path.get("reason_codes") or [])
    if resolution_error:
        _add_reason(reason_codes, str(resolution_error))
    if resolved_exchange and resolved_exchange != str(selected_path.get("exchange") or ""):
        _add_reason(reason_codes, "credential_resolution_path_differs_from_policy_best_route")
    if not has_explicit_failover_policy and str(payload.environment).lower() == "live":
        _add_reason(reason_codes, "failover_policy_missing_live_block")
    if str(validation_report.get("net_status") or "PASS").upper() == "BLOCK":
        _add_reason(reason_codes, "validation_engine_blocked")
    elif str(validation_report.get("net_status") or "PASS").upper() == "WARN":
        _add_reason(reason_codes, "validation_engine_warn")
    if failover_plan.get("reject_reason"):
        _add_reason(reason_codes, str(failover_plan.get("reject_reason")))

    remediation_map = {
        "selected_venue_blocked_by_routing_policy": "blocked_venues listesinden venue kaldırın veya default venue değiştirin.",
        "selected_venue_not_in_preferred": "preferred_venues sıralamasını güncelleyin.",
        "symbol_policy_blocked": "Market policy symbol_rules içinde ilgili sembolü allow yapın.",
        "restricted_symbol_class_blocked": "restricted_symbol_classes politikasını gözden geçirin.",
        "capability_unsupported": "Capability matrix override ile symbol capability düzeltin.",
        "capability_partial_support": "Partial capability için execution policy override tanımlayın.",
        "exchange_operational_down": "Operational health nedeni çözülene kadar venue route'u kapatın.",
        "exchange_operational_degraded": "Venue telemetry metriklerini stabilize edin.",
        "exchange_latency_high": "Latency p95 düşene kadar alternatif venue önceliği verin.",
        "exchange_validation_success_low": "Validation başarım oranını iyileştirmek için credential/adapter kontrolü yapın.",
        "exchange_rate_limit_pressure_high": "Rate limit pressure düşene kadar throughput azaltın.",
        "credential_not_found": "Routing preview için user/tenant/global approved credential ekleyin.",
        "allocation_state_missing": "capital_allocation içinde venue ağırlık tanımlayın.",
        "allocation_weight_low": "Düşük allocation ağırlığını strateji riskiyle hizalayın.",
        "allocation_weight_zero": "Ağırlığı sıfır olan venue route zincirinden çıkarılmalı.",
        "failover_policy_missing_live_block": "Live route için explicit failover policy tanımlayın.",
        "validation_engine_blocked": "Validation engine BLOCK döndürdüğü için routing engellendi.",
        "validation_engine_warn": "Validation engine WARN; route canlıya alınmadan önce kontrolleri iyileştirin.",
        "failover_no_available_venue": "Primary/secondary/fallback zincirinde kullanılabilir venue kalmadı.",
    }
    remediation = []
    for code in reason_codes:
        if code in remediation_map and remediation_map[code] not in remediation:
            remediation.append(remediation_map[code])

    net_status = str(selected_path.get("status") or "BLOCK").upper()
    if "validation_engine_blocked" in reason_codes or "failover_policy_missing_live_block" in reason_codes or "failover_no_available_venue" in reason_codes:
        net_status = "BLOCK"

    reject_reason = None
    if net_status == "BLOCK":
        reject_reason = reason_codes[0] if reason_codes else "route_blocked"

    explainability = (
        f"{selected_path.get('exchange')} venue seçildi; "
        f"score={selected_path.get('route_score')}, "
        f"policy={selected_path.get('policy_effect', {}).get('symbol_action', 'allow')}, "
        f"capability={selected_path.get('capability_effect', {}).get('support_level', 'unknown')}, "
        f"health={selected_path.get('health_effect', {}).get('health_status', 'unknown')}, "
        f"allocation={selected_path.get('allocation_state', {}).get('weight')}, "
        f"failover={failover_plan.get('selection_reason')}"
    )

    checks = [
        {
            "name": "routing_policy_priority",
            "status": net_status,
            "reason_code": reason_codes[0] if reason_codes else "routing_ok",
            "severity": "high" if net_status == "BLOCK" else ("medium" if net_status == "WARN" else "low"),
            "remediation_suggestions": remediation,
        },
        {
            "name": "market_policy_effect",
            "status": "BLOCK" if bool(selected_path.get("policy_effect", {}).get("is_blocked")) else "PASS",
            "reason_code": (selected_path.get("policy_effect", {}).get("reason_codes") or ["policy_allow"])[0],
            "severity": "high" if bool(selected_path.get("policy_effect", {}).get("is_blocked")) else "low",
            "remediation_suggestions": remediation,
        },
        {
            "name": "capability_effect",
            "status": "BLOCK"
            if str(selected_path.get("capability_effect", {}).get("support_level") or "") == "unsupported"
            else ("WARN" if str(selected_path.get("capability_effect", {}).get("support_level") or "") == "partial" else "PASS"),
            "reason_code": (selected_path.get("capability_effect", {}).get("reason_codes") or ["capability_supported"])[0],
            "severity": "high" if str(selected_path.get("capability_effect", {}).get("support_level") or "") == "unsupported" else "medium",
            "remediation_suggestions": remediation,
        },
        {
            "name": "operational_health_effect",
            "status": "BLOCK"
            if str(selected_path.get("health_effect", {}).get("health_status") or "") == "down"
            else ("WARN" if str(selected_path.get("health_effect", {}).get("health_status") or "") == "degraded" else "PASS"),
            "reason_code": (selected_path.get("health_effect", {}).get("reason_codes") or ["health_ok"])[0],
            "severity": "high",
            "remediation_suggestions": remediation,
        },
        {
            "name": "validation_engine_consistency",
            "status": str(validation_report.get("net_status") or "PASS").upper(),
            "reason_code": (validation_report.get("reason_codes") or ["validation_engine_ok"])[0],
            "severity": "high" if str(validation_report.get("net_status") or "PASS").upper() == "BLOCK" else "medium",
            "remediation_suggestions": validation_report.get("remediation_suggestions") or [],
        },
    ]
    if resolution_error:
        checks.append(
            {
                "name": "credential_resolution",
                "status": "BLOCK",
                "reason_code": resolution_error,
                "severity": "high",
                "remediation_suggestions": remediation,
            }
        )

    decision_log = _append_routing_decision_log(
        failover_runtime_config,
        {
            "key": failover_key,
            "user_id": payload.user_id,
            "strategy_id": payload.strategy_id,
            "market_type": payload.market_type,
            "environment": payload.environment,
            "selected_venue": selected_path.get("exchange"),
            "net_status": net_status,
            "reason_codes": reason_codes,
            "fallback_chain": failover_plan.get("fallback_chain") or [],
            "selection_reason": failover_plan.get("selection_reason"),
        },
    )

    validation_timeline_config = get_control_plane_config(db, config_key="validation_center_timeline", default={"items": []})
    validation_timeline_event = _append_validation_timeline_event(
        validation_timeline_config,
        {
            "strategy_key": failover_key,
            "user_id": payload.user_id,
            "strategy_id": payload.strategy_id,
            "market_type": payload.market_type,
            "environment": payload.environment,
            "net_status": validation_report.get("net_status"),
            "reason_codes": validation_report.get("reason_codes") or [],
            "checks": validation_report.get("checks") or [],
            "source": "routing_preview_v2",
        },
    )

    upsert_control_plane_config(db, config_key="failover_runtime", payload=failover_runtime_config, actor_user_id=current_admin.id)
    upsert_control_plane_config(db, config_key="validation_center_timeline", payload=validation_timeline_config, actor_user_id=current_admin.id)

    if failover_transition:
        create_audit_log(
            db,
            action="venue_failover_transition",
            entity_type="venue_failover_state",
            entity_id=failover_key,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            details=failover_transition,
        )

    create_audit_log(
        db,
        action="venue_routing_decision_generated",
        entity_type="venue_routing_decision",
        entity_id=decision_log.get("id"),
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=decision_log,
    )

    return {
        "net_status": net_status,
        "reason_codes": reason_codes,
        "remediation_suggestions": remediation,
        "checks": checks,
        "selected_venue": selected_path.get("exchange"),
        "fallback_chain": failover_plan.get("fallback_chain") or [],
        "reject_reason": reject_reason,
        "resolved_execution_path": resolved,
        "selected_path": selected_path,
        "alternative_paths": alternative_paths,
        "decision_factors": selected_path.get("decision_factors") or [],
        "explainability": explainability,
        "routing_rule": rule,
        "failover_rule": failover_rule,
        "failover_state": failover_plan,
        "failover_transition": failover_transition,
        "failover_transition_logs": [row for row in (failover_runtime_config.get("transition_logs") or []) if row.get("key") == failover_key][:20],
        "routing_decision_log": decision_log,
        "validation_timeline_event": validation_timeline_event,
        "routing_decision_trace": ordered,
        "policy_impact": selected_path.get("policy_effect") or {},
        "capability_impact": selected_path.get("capability_effect") or {},
        "health_impact": selected_path.get("health_effect") or {},
        "allocation_impact": selected_path.get("allocation_state") or {},
        "validation_report": {
            "net_status": validation_report.get("net_status"),
            "reason_codes": validation_report.get("reason_codes") or [],
            "checks": validation_report.get("checks") or [],
            "classification": validation_report.get("classification") or {},
        },
        "capital_allocation": rule.get("capital_allocation") or [],
    }


@router.get("/admin/operational-health")
def admin_operational_health(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _build_operational_health_payload(db)


@router.get("/admin/control-plane-cockpit")
def admin_control_plane_cockpit(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    window_minutes: int = Query(default=30, ge=5, le=180),
    churn_threshold: int = Query(default=5, ge=1, le=20),
):
    operational_health = _build_operational_health_payload(db)
    conflict_report = _build_conflict_detection_report(db)
    validation_center = _build_validation_center_payload(db, window_hours=24, limit=200)
    heatmap = _build_strategy_venue_heatmap_payload(db, window_hours=24)

    routing_policy = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})
    failover_policy = _get_failover_policy_config(db)
    failover_runtime = _get_failover_runtime_config(db)

    transition_logs = list(failover_runtime.get("transition_logs") or [])
    churn_alert = _build_route_churn_alert(transition_logs, window_minutes=window_minutes, threshold=churn_threshold)

    exchange_health = operational_health.get("exchange_health") or {}
    global_overview = {
        "total_venues": len(exchange_health),
        "healthy_venues": sum(1 for status in exchange_health.values() if str(status) == "healthy"),
        "degraded_venues": sum(1 for status in exchange_health.values() if str(status) == "degraded"),
        "down_venues": sum(1 for status in exchange_health.values() if str(status) == "down"),
        "routing_rule_count": len((routing_policy.get("rules") or {})),
        "failover_rule_count": len((failover_policy.get("rules") or {})),
        "active_failover_state_count": len((failover_runtime.get("runtime_state") or {})),
    }

    active_route_map = []
    for key, runtime_state in (failover_runtime.get("runtime_state") or {}).items():
        parts = key.split(":")
        active_route_map.append(
            {
                "key": key,
                "user_id": parts[0] if len(parts) > 0 else None,
                "strategy_id": parts[1] if len(parts) > 1 else None,
                "market_type": parts[2] if len(parts) > 2 else None,
                "environment": parts[3] if len(parts) > 3 else None,
                "active_venue": runtime_state.get("active_venue"),
                "fallback_chain": runtime_state.get("fallback_chain") or [],
                "selection_reason": runtime_state.get("selection_reason"),
                "updated_at": runtime_state.get("updated_at"),
            }
        )

    latest_changes_rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.in_(
                [
                    "venue_failover_policy_updated",
                    "venue_failover_manual_override_applied",
                    "venue_failover_transition",
                    "venue_routing_decision_generated",
                    "venue_routing_policy_updated",
                    "venue_market_policy_updated",
                    "venue_capability_matrix_override_updated",
                ]
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )
    latest_changes = [
        {
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor_user_id": row.actor_user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in latest_changes_rows
    ]

    return {
        "global_overview": global_overview,
        "active_route_map": active_route_map,
        "failover_state_board": list((failover_runtime.get("runtime_state") or {}).values()),
        "misconfiguration_alerts": conflict_report.get("alerts") or [],
        "route_churn_anomaly_alert": churn_alert,
        "last_critical_changes": latest_changes,
        "operational_health": operational_health,
        "conflict_detection_center": conflict_report,
        "validation_center_summary": validation_center.get("summary") or {},
        "validation_drift_alerts": validation_center.get("drift_alerts") or [],
        "strategy_heatmap_summary": {
            "strategy_count": len(heatmap.get("strategies") or []),
            "top_allocation_drifts": heatmap.get("top_allocation_drifts") or [],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/admin/conflict-detection-center")
def admin_conflict_detection_center(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _build_conflict_detection_report(db)


@router.get("/admin/validation-center")
def admin_validation_center(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    window_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=200, ge=10, le=1000),
):
    return _build_validation_center_payload(db, window_hours=window_hours, limit=limit)


@router.post("/admin/validation-center/rerun")
def admin_validation_center_rerun(
    payload: ValidationCenterRerunRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    report = _build_execution_validation_report(db)
    strategy_key = (
        _failover_rule_key(
            user_id=payload.user_id,
            strategy_id=payload.strategy_id,
            market_type=(payload.market_type or "spot"),
            environment=payload.environment,
        )
        if payload.user_id and payload.strategy_id
        else "global"
    )

    timeline_config = get_control_plane_config(db, config_key="validation_center_timeline", default={"items": []})
    timeline_event = _append_validation_timeline_event(
        timeline_config,
        {
            "strategy_key": strategy_key,
            "user_id": payload.user_id,
            "strategy_id": payload.strategy_id,
            "market_type": payload.market_type,
            "environment": payload.environment,
            "net_status": report.get("net_status"),
            "reason_codes": report.get("reason_codes") or [],
            "checks": report.get("checks") or [],
            "source": "validation_center_rerun",
        },
    )
    upsert_control_plane_config(db, config_key="validation_center_timeline", payload=timeline_config, actor_user_id=current_admin.id)

    return {
        "rerun": True,
        "strategy_key": strategy_key,
        "validation_report": report,
        "timeline_event": timeline_event,
        "validation_center": _build_validation_center_payload(db, window_hours=24, limit=200),
    }


@router.get("/admin/strategy-venue-heatmap")
def admin_strategy_venue_heatmap(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    window_hours: int = Query(default=24, ge=1, le=168),
):
    return _build_strategy_venue_heatmap_payload(db, window_hours=window_hours)


@router.get("/admin/conflict-auto-remediation-drafts")
def admin_conflict_auto_remediation_drafts(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    drafts = _build_conflict_auto_remediation_drafts(db)
    return {
        "drafts": drafts,
        "summary": {
            "total_drafts": len(drafts),
            "blocking_draft_count": sum(1 for item in drafts if str(item.get("severity") or "").upper() == "BLOCK"),
            "warning_draft_count": sum(1 for item in drafts if str(item.get("severity") or "").upper() == "WARN"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/admin/conflict-auto-remediation-apply")
def admin_conflict_auto_remediation_apply(
    payload: ConflictAutoRemediationApplyRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    drafts = _build_conflict_auto_remediation_drafts(db)
    draft_id = f"{payload.reason_code}:{payload.entity_id}"
    draft = next((item for item in drafts if item.get("draft_id") == draft_id), None)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="remediation_draft_not_found")

    endpoint = str(draft.get("endpoint") or "")
    draft_payload = dict(draft.get("payload") or {})
    apply_result: dict | None = None

    if endpoint == "PUT /api/venues/admin/routing-policies":
        apply_result = admin_upsert_routing_policies(RoutingPolicyUpsertRequest(**draft_payload), current_admin, db)
    elif endpoint == "PUT /api/venues/admin/failover-policies":
        apply_result = admin_upsert_failover_policy(FailoverPolicyUpsertRequest(**draft_payload), current_admin, db)
    elif endpoint == "POST /api/venues/admin/failover/manual-override":
        apply_result = admin_apply_failover_manual_override(FailoverManualOverrideRequest(**draft_payload), current_admin, db)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_remediation_endpoint")

    create_audit_log(
        db,
        action="venue_conflict_auto_remediation_applied",
        entity_type="venue_conflict_remediation",
        entity_id=draft_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"draft": draft, "apply_result": apply_result},
    )

    return {
        "applied": True,
        "draft_id": draft_id,
        "draft": draft,
        "apply_result": apply_result,
    }


@router.get("/admin/audit-timeline")
def admin_audit_timeline(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    from_dt = _parse_datetime_query(from_date)
    to_dt = _parse_datetime_query(to_date)
    if from_dt and to_dt and from_dt > to_dt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date_range")

    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if from_dt:
        query = query.filter(AuditLog.created_at >= from_dt)
    if to_dt:
        query = query.filter(AuditLog.created_at <= to_dt)

    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    items = []
    for row in rows:
        details = row.details or {}
        old_value = details.get("old_value")
        new_value = details.get("new_value")
        diff_keys = _extract_diff_keys(old_value, new_value)
        diff_highlights = []
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            for key in diff_keys[:30]:
                diff_highlights.append({"field": key, "old": old_value.get(key), "new": new_value.get(key)})
        elif diff_keys:
            diff_highlights.append({"field": "value", "old": old_value, "new": new_value})

        items.append(
            {
                "id": row.id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "old_value": old_value,
                "new_value": new_value,
                "diff_keys": diff_keys,
                "diff_highlights": diff_highlights,
                "details": details,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )

    return {
        "items": items,
        "applied_filters": {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_user_id": actor_user_id,
            "action": action,
            "from_date": from_date,
            "to_date": to_date,
            "limit": limit,
        },
    }


@router.get("/admin/adapter-smoke")
def admin_adapter_smoke(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    _ = db
    return run_exchange_adapter_smoke()


@router.get("/admin/execution-credentials")
def admin_get_execution_credentials(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_execution_credentials(db)


@router.patch("/admin/execution-credentials")
def admin_patch_execution_credentials(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    allowed_keys = {
        "bybit_api_key",
        "bybit_secret",
        "bybit_testnet_api_key",
        "bybit_testnet_secret",
        "bybit_live_api_key",
        "bybit_live_secret",
        "okx_api_key",
        "okx_secret",
        "okx_passphrase",
    }
    sanitized = {key: str(value or "") for key, value in (payload or {}).items() if key in allowed_keys}
    result = upsert_execution_credentials(db, sanitized)
    create_audit_log(
        db,
        action="admin_exchange_execution_credentials_updated",
        entity_type="external_provider_credentials",
        entity_id="exchange_execution_credentials_v1",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "updated_keys": sorted(list(sanitized.keys())),
            "has_bybit_credentials": result.get("has_bybit_credentials"),
            "has_okx_credentials": result.get("has_okx_credentials"),
        },
    )
    return result


@router.post("/admin/execution-validation")
def admin_execution_validation(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    report = _build_execution_validation_report(db)
    timeline_config = get_control_plane_config(db, config_key="validation_center_timeline", default={"items": []})
    timeline_event = _append_validation_timeline_event(
        timeline_config,
        {
            "strategy_key": "global",
            "user_id": None,
            "strategy_id": None,
            "net_status": report.get("net_status"),
            "reason_codes": report.get("reason_codes") or [],
            "checks": report.get("checks") or [],
            "source": "admin_execution_validation",
        },
    )
    upsert_control_plane_config(db, config_key="validation_center_timeline", payload=timeline_config, actor_user_id="system")

    checks_by_name = {item.get("name"): item for item in (report.get("checks") or [])}
    return {
        "net_status": report.get("net_status"),
        "reason_codes": report.get("reason_codes") or [],
        "remediation_suggestions": report.get("remediation_suggestions") or [],
        "checks": report.get("checks") or [],
        "validation": {
            "adapter_smoke_test": checks_by_name.get("real_balance_fetch", {}).get("status", "WARN"),
            "precision_validation": checks_by_name.get("venue_capability_runtime_test", {}).get("status", "WARN"),
            "lot_size_validation": checks_by_name.get("venue_capability_runtime_test", {}).get("status", "WARN"),
            "order_submit_test": checks_by_name.get("test_order_cancel_retry", {}).get("status", "WARN"),
            "cancel_test": checks_by_name.get("test_order_cancel_retry", {}).get("status", "WARN"),
            "retry_behavior": checks_by_name.get("test_order_cancel_retry", {}).get("status", "WARN"),
            "bybit_testnet_live_ready": checks_by_name.get("permission_matrix_test", {}).get("status", "WARN"),
        },
        "validation_report": report,
        "timeline_event": timeline_event,
    }


@router.get("/admin/credentials", response_model=list[AdminExchangeCredentialResponse])
def admin_list_orchestration_credentials(
    exchange: str | None = Query(default=None),
    market_type: str | None = Query(default=None),
    purpose: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    approval_status: str | None = Query(default=None),
    include_inactive: bool = Query(default=True),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = list_admin_credentials(
        db,
        exchange=exchange,
        market_type=market_type,
        purpose=purpose,
        environment=environment,
        scope_type=scope_type,
        approval_status=approval_status,
        include_inactive=include_inactive,
    )
    return [AdminExchangeCredentialResponse(**row) for row in rows]


@router.post("/admin/credentials", response_model=AdminExchangeCredentialResponse, status_code=status.HTTP_201_CREATED)
def admin_create_orchestration_credential(
    payload: AdminExchangeCredentialCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = create_admin_credential(
            db,
            actor=current_admin,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            exchange=payload.exchange,
            market_type=payload.market_type,
            purpose=payload.purpose,
            environment=payload.environment,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            passphrase=payload.passphrase,
            base_url_override=payload.base_url_override,
            ip_binding_note=payload.ip_binding_note,
            is_default=payload.is_default,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    create_audit_log(
        db,
        action="admin_credential_created",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange": row["exchange"],
            "market_type": row["market_type"],
            "environment": row["environment"],
            "scope_type": row["scope_type"],
            "purpose": row["purpose"],
            "approval_status": row["approval_status"],
        },
    )
    return AdminExchangeCredentialResponse(**row)


@router.patch("/admin/credentials/{credential_id}", response_model=AdminExchangeCredentialResponse)
def admin_patch_orchestration_credential(
    credential_id: str,
    payload: AdminExchangeCredentialPatchRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = update_admin_credential(
            db,
            actor=current_admin,
            credential_id=credential_id,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            purpose=payload.purpose,
            base_url_override=payload.base_url_override,
            ip_binding_note=payload.ip_binding_note,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            passphrase=payload.passphrase,
            is_default=payload.is_default,
            is_active=payload.is_active,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    create_audit_log(
        db,
        action="admin_credential_updated",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"updated_fields": sorted([k for k, v in payload.model_dump().items() if v is not None])},
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/approve", response_model=AdminExchangeCredentialResponse)
def admin_approve_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = approve_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_approved",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/disable", response_model=AdminExchangeCredentialResponse)
def admin_disable_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = disable_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_disabled",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/verify", response_model=AdminExchangeCredentialResponse)
def admin_verify_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = verify_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_verified",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"probe_status": row.get("last_probe_status")},
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/revoke", response_model=AdminExchangeCredentialResponse)
def admin_revoke_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = revoke_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_revoked",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/rotate", response_model=AdminExchangeCredentialResponse)
def admin_rotate_orchestration_credential(
    credential_id: str,
    payload: AdminExchangeCredentialRotateRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = rotate_admin_credential(
            db,
            actor=current_admin,
            credential_id=credential_id,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            passphrase=payload.passphrase,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_rotated",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/probe", response_model=AdminExchangeCredentialResponse)
def admin_probe_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = probe_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_probe_executed",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"probe_status": row.get("last_probe_status"), "probe_message": row.get("last_probe_message")},
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/control-plane-sanity-check")
def admin_run_control_plane_sanity_check(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = run_and_cache_venue_control_plane_sanity(db)
    create_audit_log(
        db,
        action="venue_control_plane_sanity_check",
        entity_type="venue_control_plane",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "net_status": result.get("net_status"),
            "reason_codes": result.get("reason_codes") or [],
        },
    )
    return result


@router.get("/admin/control-plane-sanity-last")
def admin_get_control_plane_sanity_last(
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    cached = get_cached_venue_control_plane_sanity()
    if cached is None:
        return {"net_status": "WARN", "reason_codes": ["sanity_not_run"], "remediation_suggestions": ["Sanity check çalıştırın"], "checks": []}
    return cached


@router.get("/admin/credential-rules", response_model=list[CredentialAssignmentRuleResponse])
def admin_list_credential_rules(
    exchange: str | None = Query(default=None),
    market_type: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = list_assignment_rules(db, exchange=exchange, market_type=market_type, environment=environment)
    return [CredentialAssignmentRuleResponse(**row) for row in rows]


@router.put("/admin/credential-rules", response_model=CredentialAssignmentRuleResponse)
def admin_put_credential_rule(
    payload: CredentialAssignmentRuleUpsertRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = upsert_assignment_rule(
            db,
            actor=current_admin,
            exchange=payload.exchange,
            market_type=payload.market_type,
            environment=payload.environment,
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            preferred_source=payload.preferred_source,
            fallback_enabled=payload.fallback_enabled,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    create_audit_log(
        db,
        action="admin_credential_rule_updated",
        entity_type="credential_assignment_rule",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange": row["exchange"],
            "market_type": row["market_type"],
            "environment": row["environment"],
            "preferred_source": row["preferred_source"],
            "fallback_enabled": row["fallback_enabled"],
        },
    )
    return CredentialAssignmentRuleResponse(**row)


@router.get("/admin/credential-resolution-preview", response_model=CredentialResolutionPreviewResponse)
def admin_credential_resolution_preview(
    user_id: str,
    exchange: str = Query(default="binance"),
    market_type: str = Query(default="spot"),
    environment: str = Query(default="testnet"),
    purpose: str = Query(default="execution"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    request_id = str(uuid.uuid4())
    resolved_at = datetime.now(timezone.utc).isoformat()
    try:
        result = resolve_exchange_credentials(
            db,
            user_id=user_id,
            exchange=exchange,
            market_type=market_type,
            environment=environment,
            purpose=purpose,
            include_secrets=False,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    selected_probe_status = None
    selected_probe_message = None
    selected_id = result.get("selected_credential_id")
    if selected_id:
        selected_row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == selected_id).first()
        if selected_row:
            selected_probe_status = selected_row.last_probe_status
            selected_probe_message = selected_row.last_probe_message

    enriched = {
        **result,
        "request_id": request_id,
        "resolved_at": resolved_at,
        "exchange": exchange,
        "market_type": market_type,
        "environment": environment,
        "purpose": purpose,
        "fallback_chain": ["user", "tenant_admin", "global_admin"],
        "selected_probe_status": selected_probe_status,
        "selected_probe_message": selected_probe_message,
    }

    create_audit_log(
        db,
        action="admin_credential_resolution_preview",
        entity_type="credential_resolution_trace",
        entity_id=request_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "request_id": request_id,
            "resolved_at": resolved_at,
            "user_id": user_id,
            "exchange": exchange,
            "market_type": market_type,
            "environment": environment,
            "purpose": purpose,
            "source": result.get("source"),
            "selected_credential_id": result.get("selected_credential_id"),
            "masked_fingerprint": result.get("masked_fingerprint"),
            "selection_reason": (result.get("audit_metadata") or {}).get("selection_reason"),
            "rule_id": (result.get("audit_metadata") or {}).get("rule_id"),
            "selected_probe_status": selected_probe_status,
            "selected_probe_message": selected_probe_message,
        },
    )

    return CredentialResolutionPreviewResponse(**enriched)


@router.get("/options", response_model=list[UserVenueOptionResponse])
def user_allowed_options(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    options = user_allowed_venue_options(db, current_user.id)
    if not options:
        return [
            UserVenueOptionResponse(
                exchange="-",
                market_type="-",
                environment="-",
                venue_state="no_assigned_venues",
            )
        ]
    return [UserVenueOptionResponse(**item) for item in options]


@router.get("/access-check")
def user_access_check(
    exchange: str,
    market_type: str,
    environment: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    seed_binance_venue_registry(db)
    allowed, venue_state, capability_match, reason_codes = check_user_venue_access(
        db,
        current_user.id,
        exchange.lower(),
        market_type.lower(),
        environment.lower(),
    )
    return {
        "allowed": allowed,
        "venue_state": venue_state,
        "capability_match": capability_match,
        "reason_codes": reason_codes,
    }