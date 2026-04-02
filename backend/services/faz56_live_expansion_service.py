from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import AuditLog, FailedEvent, PaperPosition, LiveExecutionLog
from services.artifact_service import write_signed_artifact
from services.execution_safety_service import execution_safety_snapshot
from services.live_mode_service import get_or_create_live_config, release_gate_view
from services.live_trading_dashboard_service import build_daily_report, build_live_trading_summary
from services.system_alert_service import create_system_alert


EXPANSION_STATE_KEY = "faz56:expansion_state"
DAILY_REPORT_META_KEY = "faz56:daily_report_latest"
ROLLBACK_META_KEY = "faz56:auto_rollback_latest"
OBSERVATION_WINDOW_MINUTES = 120
FILL_RATE_THRESHOLD = 0.85
FAILED_ORDER_RATE_THRESHOLD = 0.15
LATENCY_P95_THRESHOLD_MS = 2500.0

EXPANSION_STEPS = [
    {"key": "size_scale_current_symbol", "title": "Mevcut symbol size artışı"},
    {"key": "add_second_symbol", "title": "2. symbol ekleme"},
    {"key": "add_second_template", "title": "2. template açma"},
    {"key": "parallel_strategy", "title": "Paralel strateji"},
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _read_json(cache, key: str, default):
    try:
        raw = cache.get(key)
    except Exception:
        return default
    if not raw:
        return default
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return payload if isinstance(payload, type(default)) else default


def _write_json(cache, key: str, payload: dict) -> None:
    cache.set(key, json.dumps(payload, ensure_ascii=False, default=str))


def _percentile_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * 0.95))))
    return round(float(ordered[index]), 4)


def get_or_create_expansion_state(cache, *, timezone_name: str = "Europe/Istanbul") -> dict:
    existing = _read_json(cache, EXPANSION_STATE_KEY, {})
    if existing:
        return existing

    now = _now_utc()
    state = {
        "phase": "FAZ_5",
        "status": "active",
        "halted": False,
        "observation_window_minutes": OBSERVATION_WINDOW_MINUTES,
        "current_step_index": 0,
        "current_step_key": EXPANSION_STEPS[0]["key"],
        "completed_steps": [],
        "steps": EXPANSION_STEPS,
        "started_at": now.isoformat(),
        "last_transition_at": (now - timedelta(minutes=OBSERVATION_WINDOW_MINUTES)).isoformat(),
        "timezone": timezone_name,
        "principle": "Sistem para kaybetmeden büyümeli, hızlı değil kontrollü büyümeli.",
        "sim_auto_switch_enabled": False,
        "second_template_enabled": False,
        "parallel_strategy_enabled": False,
    }
    _write_json(cache, EXPANSION_STATE_KEY, state)
    return state


def compute_live_session_metrics(db: Session, *, window_minutes: int = OBSERVATION_WINDOW_MINUTES) -> dict:
    now = _now_utc()
    since = now - timedelta(minutes=max(window_minutes, 5))

    rows = (
        db.query(LiveExecutionLog)
        .filter(LiveExecutionLog.created_at >= since)
        .order_by(LiveExecutionLog.created_at.desc())
        .limit(1200)
        .all()
    )

    total = len(rows)
    filled = sum(1 for row in rows if str(row.status or "").lower() == "filled")
    failed = sum(1 for row in rows if str(row.status or "").lower() == "failed")
    fill_rate = round(filled / max(total, 1), 6) if total else 0.0
    failed_rate = round(failed / max(total, 1), 6) if total else 0.0
    rejection_rate = failed_rate

    latencies = [_safe_float(row.execution_latency) for row in rows if row.execution_latency is not None]
    latency_p95 = _percentile_p95(latencies)

    drift_values: list[float] = []
    for row in rows:
        expected = _safe_float(row.expected_price)
        fill_price = _safe_float(row.fill_price)
        if expected > 0 and fill_price > 0:
            drift_values.append(abs(fill_price - expected) / expected * 100)
    pnl_drift_pct = round(sum(drift_values) / max(len(drift_values), 1), 6) if drift_values else 0.0

    retry_count = (
        db.query(func.coalesce(func.sum(FailedEvent.retry_count), 0))
        .filter(FailedEvent.updated_at >= since, FailedEvent.status.in_(["pending", "failed"]))
        .scalar()
        or 0
    )
    failed_orders_count = (
        db.query(func.count(FailedEvent.id))
        .filter(FailedEvent.updated_at >= since, FailedEvent.status.in_(["pending", "failed"]))
        .scalar()
        or 0
    )

    exposure = execution_safety_snapshot(db)
    symbol_rows = (
        db.query(PaperPosition.symbol, func.sum(func.abs(PaperPosition.quantity * PaperPosition.entry_price)))
        .filter(func.lower(PaperPosition.status) == "open")
        .group_by(PaperPosition.symbol)
        .all()
    )
    symbol_exposure = [
        {"symbol": str(symbol or "UNKNOWN").upper(), "notional": round(_safe_float(notional), 6)}
        for symbol, notional in symbol_rows
    ]
    symbol_exposure.sort(key=lambda item: item["notional"], reverse=True)

    anomalies: list[dict] = []
    if total > 0 and fill_rate < FILL_RATE_THRESHOLD:
        anomalies.append({"code": "low_fill_rate", "value": fill_rate, "threshold": FILL_RATE_THRESHOLD})
    if total > 0 and failed_rate > FAILED_ORDER_RATE_THRESHOLD:
        anomalies.append({"code": "high_failed_order_rate", "value": failed_rate, "threshold": FAILED_ORDER_RATE_THRESHOLD})
    if latency_p95 > LATENCY_P95_THRESHOLD_MS:
        anomalies.append({"code": "high_latency_p95", "value": latency_p95, "threshold": LATENCY_P95_THRESHOLD_MS})

    return {
        "window_minutes": window_minutes,
        "generated_at": now.isoformat(),
        "sample_size": total,
        "fill_rate": fill_rate,
        "rejection_rate": rejection_rate,
        "failed_order_rate": failed_rate,
        "retry_count": int(retry_count),
        "execution_latency_p95_ms": latency_p95,
        "pnl_drift_pct": pnl_drift_pct,
        "exposure": {
            "total_notional": round(_safe_float(exposure.get("current_total_exposure")), 6),
            "symbol_top": symbol_exposure[:5],
        },
        "failed_orders_count": int(failed_orders_count),
        "thresholds": {
            "fill_rate_min": FILL_RATE_THRESHOLD,
            "failed_order_rate_max": FAILED_ORDER_RATE_THRESHOLD,
            "latency_p95_ms_max": LATENCY_P95_THRESHOLD_MS,
        },
        "anomalies": anomalies,
        "is_anomaly": bool(anomalies),
    }


def apply_auto_rollback_if_needed(
    db: Session,
    cache,
    *,
    actor_user_id: str,
    actor_role: str,
    reason: str,
    metrics: dict,
) -> dict:
    now = _now_utc()
    if not bool(metrics.get("is_anomaly")):
        payload = {
            "status": "no_action",
            "reason": "anomaly_not_detected",
            "evaluated_at": now.isoformat(),
            "sim_switch_recommended": False,
        }
        _write_json(cache, ROLLBACK_META_KEY, payload)
        return payload

    config = get_or_create_live_config(db)
    before = {
        "canary_max_capital_usdt": float(config.canary_max_capital_usdt or 0),
        "canary_symbols": list(config.canary_symbols or []),
        "max_position_pct": float(config.max_position_pct or 0),
        "leverage_cap": int(config.leverage_cap or 1),
    }

    config.canary_max_capital_usdt = max(5.0, round(before["canary_max_capital_usdt"] * 0.7, 2))
    config.max_position_pct = max(0.05, round(before["max_position_pct"] - 0.01, 4))
    config.leverage_cap = max(1, before["leverage_cap"] - 1)
    symbols = [str(item or "").upper() for item in before["canary_symbols"] if str(item or "").strip()]
    config.canary_symbols = symbols[:1] if symbols else ["BTCUSDT"]
    config.updated_at = now
    db.commit()

    after = {
        "canary_max_capital_usdt": float(config.canary_max_capital_usdt or 0),
        "canary_symbols": list(config.canary_symbols or []),
        "max_position_pct": float(config.max_position_pct or 0),
        "leverage_cap": int(config.leverage_cap or 1),
    }

    payload = {
        "status": "applied",
        "reason": reason,
        "evaluated_at": now.isoformat(),
        "actions": [
            "size_dusuruldu",
            "symbol_seti_daraltildi",
            "risk_limitleri_sikilastirildi",
        ],
        "before": before,
        "after": after,
        "sim_switch_recommended": True,
        "sim_auto_switch_enabled": False,
        "anomalies": list(metrics.get("anomalies") or []),
    }
    _write_json(cache, ROLLBACK_META_KEY, payload)

    create_system_alert(
        db,
        alert_type="faz56_auto_rollback_applied",
        severity="WARNING",
        message="Faz 5-6 otomatik geri çekilme uygulandı (SIM'e otomatik geçiş kapalı)",
        details=payload,
        entity_key="faz56",
        root_cause_code="faz56_anomaly_rollback",
        state_key="rollback_applied",
    )
    db.add(
        AuditLog(
            action="FAZ56_AUTO_ROLLBACK_APPLIED",
            entity_type="faz56",
            entity_id="global",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="warning",
            details=payload,
        )
    )
    db.commit()
    return payload


def advance_expansion_step(
    db: Session,
    cache,
    *,
    actor_user_id: str,
    actor_role: str,
    reason: str,
    timezone_name: str = "Europe/Istanbul",
) -> dict:
    state = get_or_create_expansion_state(cache, timezone_name=timezone_name)
    now = _now_utc()
    metrics = compute_live_session_metrics(db, window_minutes=state.get("observation_window_minutes", OBSERVATION_WINDOW_MINUTES))

    if bool(metrics.get("is_anomaly")):
        state["status"] = "halted"
        state["halted"] = True
        state["halt_reason"] = "anomaly_detected"
        state["halted_at"] = now.isoformat()
        _write_json(cache, EXPANSION_STATE_KEY, state)

        rollback = apply_auto_rollback_if_needed(
            db,
            cache,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason="faz56_halt_anomaly",
            metrics=metrics,
        )
        return {
            "status": "halted",
            "reason": "anomaly_detected",
            "metrics": metrics,
            "rollback": rollback,
            "state": state,
        }

    if bool(state.get("halted")):
        return {"status": "blocked", "reason": "expansion_halted", "state": state, "metrics": metrics}

    idx = int(state.get("current_step_index") or 0)
    steps = list(state.get("steps") or EXPANSION_STEPS)
    if idx >= len(steps):
        state["status"] = "completed"
        _write_json(cache, EXPANSION_STATE_KEY, state)
        return {"status": "completed", "state": state, "metrics": metrics}

    last_transition = datetime.fromisoformat(str(state.get("last_transition_at")).replace("Z", "+00:00"))
    elapsed_minutes = (now - last_transition).total_seconds() / 60
    required_minutes = int(state.get("observation_window_minutes") or OBSERVATION_WINDOW_MINUTES)
    if elapsed_minutes < required_minutes:
        return {
            "status": "blocked",
            "reason": "observation_window_not_completed",
            "elapsed_minutes": round(elapsed_minutes, 2),
            "required_minutes": required_minutes,
            "state": state,
            "metrics": metrics,
        }

    config = get_or_create_live_config(db)
    current_step = steps[idx]
    applied_actions: list[dict] = []

    if current_step["key"] == "size_scale_current_symbol":
        previous = float(config.canary_max_capital_usdt or 0)
        config.canary_max_capital_usdt = min(120.0, round(previous + 5.0, 2))
        config.max_position_pct = min(0.25, round(float(config.max_position_pct or 0.1) + 0.01, 4))
        config.leverage_cap = min(5, int(config.leverage_cap or 1) + 1)
        applied_actions.append({"field": "canary_max_capital_usdt", "before": previous, "after": config.canary_max_capital_usdt})
    elif current_step["key"] == "add_second_symbol":
        symbols = [str(item or "").upper() for item in list(config.canary_symbols or []) if str(item or "").strip()]
        if "ETHUSDT" not in symbols:
            symbols.append("ETHUSDT")
        config.canary_symbols = symbols[:2]
        applied_actions.append({"field": "canary_symbols", "after": config.canary_symbols})
    elif current_step["key"] == "add_second_template":
        state["second_template_enabled"] = True
        applied_actions.append({"field": "second_template_enabled", "after": True})
    elif current_step["key"] == "parallel_strategy":
        state["parallel_strategy_enabled"] = True
        applied_actions.append({"field": "parallel_strategy_enabled", "after": True})

    config.updated_at = now
    db.commit()

    state["completed_steps"] = [*list(state.get("completed_steps") or []), current_step["key"]]
    state["current_step_index"] = idx + 1
    state["current_step_key"] = steps[idx + 1]["key"] if (idx + 1) < len(steps) else "done"
    state["status"] = "completed" if state["current_step_key"] == "done" else "active"
    state["last_transition_at"] = now.isoformat()
    state["timezone"] = timezone_name
    _write_json(cache, EXPANSION_STATE_KEY, state)

    audit_payload = {
        "step": current_step,
        "reason": reason,
        "applied_actions": applied_actions,
        "metrics": metrics,
    }
    db.add(
        AuditLog(
            action="FAZ56_EXPANSION_STEP_APPLIED",
            entity_type="faz56",
            entity_id=current_step["key"],
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            severity="info",
            details=audit_payload,
        )
    )
    db.commit()

    return {
        "status": "advanced",
        "applied_step": current_step,
        "applied_actions": applied_actions,
        "state": state,
        "metrics": metrics,
    }


def generate_daily_live_report_artifact(db: Session, cache, *, timezone_name: str = "Europe/Istanbul") -> dict:
    tz = ZoneInfo(timezone_name)
    now_local = _now_utc().astimezone(tz)
    local_day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_day_start = local_day_start.astimezone(timezone.utc)

    day_rows = (
        db.query(LiveExecutionLog)
        .filter(LiveExecutionLog.created_at >= utc_day_start)
        .order_by(LiveExecutionLog.created_at.desc())
        .all()
    )
    total_trades = len(day_rows)
    filled_count = sum(1 for row in day_rows if str(row.status or "").lower() == "filled")
    failed_count = sum(1 for row in day_rows if str(row.status or "").lower() == "failed")

    risk_block_count = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.created_at >= utc_day_start, AuditLog.action == "EXECUTION_BLOCKED")
        .scalar()
        or 0
    )
    kill_switch_usage = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.created_at >= utc_day_start, AuditLog.action.ilike("%kill_switch%"))
        .scalar()
        or 0
    )

    session_metrics = compute_live_session_metrics(db, window_minutes=1440)
    anomaly_list = list(session_metrics.get("anomalies") or [])
    pass_fail = "PASS" if not anomaly_list else "FAIL"

    base_report = build_daily_report(db, cache)
    payload = {
        "date": local_day_start.date().isoformat(),
        "timezone": timezone_name,
        "generated_at": now_local.isoformat(),
        "pass_fail": pass_fail,
        "total_trades": total_trades,
        "filled_vs_failed": {"filled": filled_count, "failed": failed_count},
        "risk_block_count": int(risk_block_count),
        "kill_switch_usage_count": int(kill_switch_usage),
        "anomaly_list": anomaly_list,
        "session_metrics": session_metrics,
        "base_report": base_report,
    }

    artifact = write_signed_artifact(
        payload,
        artifact_type="faz56_daily_live_report",
        filename_prefix="faz56_daily_live_report",
    )
    result = {**payload, "artifact": artifact}
    _write_json(cache, DAILY_REPORT_META_KEY, result)
    return result


def latest_daily_live_report(cache) -> dict:
    return _read_json(cache, DAILY_REPORT_META_KEY, {})


def build_closure_proof_bundle(db: Session, cache, *, timezone_name: str = "Europe/Istanbul") -> dict:
    now = _now_utc()
    since_24h = now - timedelta(hours=24)
    gate = release_gate_view(db, environment="prod")
    metrics_24h = compute_live_session_metrics(db, window_minutes=1440)

    latest_filled = (
        db.query(LiveExecutionLog)
        .filter(LiveExecutionLog.created_at >= since_24h, LiveExecutionLog.status == "filled")
        .order_by(LiveExecutionLog.created_at.desc())
        .first()
    )

    kill_switch_proof_count = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since_24h, AuditLog.action.ilike("%kill_switch%"))
        .scalar()
        or 0
    )
    rollback_meta = _read_json(cache, ROLLBACK_META_KEY, {})

    summary_24h = build_live_trading_summary(db, cache, window="24h")
    ui_backend_sync_ok = len(list(summary_24h.get("component_errors") or [])) == 0
    stable_24h = not bool(metrics_24h.get("is_anomaly"))

    proofs = {
        "final_release_gate_go": str(gate.get("status") or "") == "PASS",
        "canary_live_report_pass": latest_filled is not None,
        "execution_proof": {
            "exists": latest_filled is not None,
            "execution_id": latest_filled.id if latest_filled else None,
            "filled_at": latest_filled.created_at.isoformat() if latest_filled else None,
            "details": latest_filled.details if latest_filled else {},
        },
        "kill_switch_proof": {
            "exists": kill_switch_proof_count > 0,
            "events_last_24h": int(kill_switch_proof_count),
        },
        "rollback_proof": {
            "exists": bool(rollback_meta),
            "payload": rollback_meta,
        },
        "stability_24h": stable_24h,
        "ui_backend_sync": ui_backend_sync_ok,
    }

    closure_ok = all(
        [
            proofs["final_release_gate_go"],
            proofs["canary_live_report_pass"],
            proofs["kill_switch_proof"]["exists"],
            proofs["stability_24h"],
            proofs["ui_backend_sync"],
        ]
    )

    return {
        "timezone": timezone_name,
        "generated_at": now.isoformat(),
        "principle": "Sistem para kaybetmeden büyümeli, hızlı değil kontrollü büyümeli.",
        "proofs": proofs,
        "metrics_24h": metrics_24h,
        "final_release_gate": gate,
        "system_status": "PRODUCTION ACTIVE" if closure_ok else "HARDENING_IN_PROGRESS",
        "closure_ready": closure_ok,
        "backlog_post_production": [
            "Visual Policy Builder",
            "advanced capital allocation",
            "explainability graph",
        ],
    }


def finalize_closure_artifact(db: Session, cache, *, timezone_name: str = "Europe/Istanbul") -> dict:
    bundle = build_closure_proof_bundle(db, cache, timezone_name=timezone_name)
    artifact = write_signed_artifact(bundle, artifact_type="faz6_closure_bundle", filename_prefix="faz6_closure_bundle")
    return {**bundle, "artifact": artifact}


def build_operator_cheat_sheet() -> dict:
    markdown = """# Operatör Cheat Sheet (Faz 6)\n\n## 1) Sistem Başlatma\n- Admin panelden execution mode: `LIVE` (onay: `SWITCH TO LIVE`)\n- `kill-switch` durumu: trading enabled\n- `/api/phase4/faz56/live-session-metrics` ile oturum metriklerini kontrol et\n\n## 2) Sistem Durdurma\n- Önce `kill-switch` ile trading kapat\n- Gerekirse açık botları durdur: `/api/phase4/kill-switch/stop-all-bots`\n- Gerekirse pozisyonları kapat: `/api/phase4/kill-switch/close-all-positions`\n\n## 3) Kill Switch Ne Zaman Kullanılır\n- Fill başarısızlık oranı yükselirse\n- Beklenmeyen execution hataları artarsa\n- UI/backend senkronu bozulursa\n\n## 4) Risk Limitleri Nereden Değişir\n- `/api/admin/live-trading/control-layer/risk-controls`\n- Günlük max loss ilk etapta artırılmaz\n\n## 5) Acil Durum Prosedürü\n1. Kill switch ON\n2. Faz56 auto-rollback evaluate\n3. Günlük rapor artefact üret\n4. Kapanış proof bundle kontrol\n"""
    return {
        "title": "Faz 6 Operatör Cheat Sheet",
        "generated_at": _now_utc().isoformat(),
        "content_markdown": markdown,
    }
