from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import AuditLog, ExecutionIntent, ExecutionIntentEvent, FailedEvent, StrategyDefinition, StrategyVersion
from services.audit_service import create_audit_log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_state(value: Any) -> str:
    state = str(value or "").strip().upper()
    return "CANCELED" if state == "CANCELLED" else state


def _window_delta(window: str) -> timedelta:
    normalized = str(window or "7d").strip().lower()
    if normalized == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _read_manifest(path: str, *, window: str) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    cutoff = _utcnow() - _window_delta(window)
    rows: list[dict] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            created_at_raw = row.get("created_at")
            try:
                created_at = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
            except Exception:
                continue
            created_at = _as_utc(created_at)
            if not created_at or created_at < cutoff:
                continue
            row["_created_at"] = created_at
            rows.append(row)
    return rows


def analytics_gate_failures(*, window: str = "7d") -> dict:
    rows = _read_manifest("/app/artifacts/manifests/execution_safety_gate_manifest.jsonl", window=window)
    ready = 0
    degraded = 0
    blocked = 0
    timeseries: dict[str, dict[str, int]] = {}

    for row in rows:
        payload = dict(row.get("payload") or {})
        gate = dict(payload.get("gate") or payload)
        state = _normalize_state(gate.get("gate_state") or gate.get("state") or "UNKNOWN")
        day_key = row["_created_at"].strftime("%Y-%m-%d")
        bucket = timeseries.setdefault(day_key, {"ready": 0, "degraded": 0, "blocked": 0, "total": 0})
        bucket["total"] += 1
        if state == "READY":
            ready += 1
            bucket["ready"] += 1
        elif state == "BLOCKED":
            blocked += 1
            bucket["blocked"] += 1
        else:
            degraded += 1
            bucket["degraded"] += 1

    total = ready + degraded + blocked
    return {
        "window": window,
        "total_evaluations": total,
        "blocked_count": blocked,
        "degraded_count": degraded,
        "ready_count": ready,
        "failure_rate": round((blocked / total) if total else 0.0, 4),
        "timeseries": [
            {
                "date": day,
                "ready": payload["ready"],
                "degraded": payload["degraded"],
                "blocked": payload["blocked"],
                "total": payload["total"],
            }
            for day, payload in sorted(timeseries.items())
        ],
    }


def analytics_blockers(*, window: str = "7d") -> dict:
    rows = _read_manifest("/app/artifacts/manifests/execution_safety_gate_manifest.jsonl", window=window)
    counts: dict[str, int] = {}
    distribution_by_day: dict[str, dict[str, int]] = {}
    for row in rows:
        payload = dict(row.get("payload") or {})
        gate = dict(payload.get("gate") or payload)
        blockers = gate.get("hard_blockers") or gate.get("blockers") or []
        day_key = row["_created_at"].strftime("%Y-%m-%d")
        bucket = distribution_by_day.setdefault(day_key, {})
        for blocker in blockers:
            code = str(blocker or "unknown")
            counts[code] = counts.get(code, 0) + 1
            bucket[code] = bucket.get(code, 0) + 1

    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return {
        "window": window,
        "top_blockers": [{"code": code, "count": count} for code, count in top[:20]],
        "distribution": [
            {"date": day, "blockers": payload}
            for day, payload in sorted(distribution_by_day.items())
        ],
    }


def analytics_recovery(db: Session, *, window: str = "7d") -> dict:
    cutoff = _utcnow() - _window_delta(window)
    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.created_at >= cutoff)
        .filter(AuditLog.action.in_(["execution_bulk_recovery_item", "execution_quarantine_recovery_action", "execution_reconcile_completed"]))
        .all()
    )
    retry_total = 0
    retry_success = 0
    reconcile_total = 0
    reconcile_success = 0
    for row in audit_rows:
        details = dict(row.details or {})
        action = str(details.get("action") or row.action)
        error = details.get("error")
        if "retry" in action:
            retry_total += 1
            if not error:
                retry_success += 1
        if "reconcile" in action:
            reconcile_total += 1
            if not error:
                reconcile_success += 1

    quarantines = db.query(FailedEvent).filter(FailedEvent.created_at >= cutoff).all()
    resolved = [row for row in quarantines if row.resolved_at]
    avg_recovery_time_sec = 0.0
    if resolved:
        avg_recovery_time_sec = sum(
            max(((_as_utc(row.resolved_at) or _utcnow()) - (_as_utc(row.created_at) or _utcnow())).total_seconds(), 0)
            for row in resolved
        ) / len(resolved)

    intents_total = db.query(ExecutionIntent).filter(ExecutionIntent.created_at >= cutoff).count()
    return {
        "window": window,
        "retry_success_rate": round((retry_success / retry_total) if retry_total else 0.0, 4),
        "reconcile_success_rate": round((reconcile_success / reconcile_total) if reconcile_total else 0.0, 4),
        "quarantine_rate": round((len(quarantines) / intents_total) if intents_total else 0.0, 4),
        "avg_recovery_time_sec": round(avg_recovery_time_sec, 2),
    }


def detect_false_decisions(db: Session, *, window: str = "7d", severity: str | None = None, anomaly_type: str | None = None) -> dict:
    rows = _read_manifest("/app/artifacts/manifests/execution_safety_gate_manifest.jsonl", window=window)
    items: list[dict] = []

    for row in rows:
        payload = dict(row.get("payload") or {})
        gate = dict(payload.get("gate") or payload)
        state = _normalize_state(gate.get("gate_state") or gate.get("state") or "UNKNOWN")
        blockers = gate.get("hard_blockers") or gate.get("blockers") or []
        execution_allowed = bool(gate.get("execution_allowed") or payload.get("execution_allowed"))
        decision_type = None
        reason = None
        risk = 0.0
        if state == "READY" and blockers:
            decision_type = "FALSE_READY"
            reason = "blocker_present_but_ready"
            risk = 0.88
        elif execution_allowed and blockers:
            decision_type = "FALSE_ALLOW"
            reason = "blocker_present_but_allowed"
            risk = 0.93
        if decision_type:
            sev = "HIGH" if risk >= 0.9 else "MEDIUM"
            items.append(
                {
                    "intent_id": (payload.get("gate") or {}).get("correlation_id"),
                    "type": decision_type,
                    "reason": reason,
                    "risk_score": risk,
                    "severity": sev,
                    "requires_manual_intervention": True,
                    "detected_at": row.get("created_at"),
                }
            )

    cutoff = _utcnow() - _window_delta(window)
    corr_failures = (
        db.query(FailedEvent)
        .filter(FailedEvent.created_at >= cutoff)
        .filter(FailedEvent.failure_class == "correlation_violation")
        .all()
    )
    for row in corr_failures:
        items.append(
            {
                "intent_id": row.entity_id,
                "type": "CORRELATION_BREACH",
                "reason": row.error_message,
                "risk_score": 0.91,
                "severity": "HIGH",
                "requires_manual_intervention": True,
                "detected_at": _as_utc(row.created_at).isoformat() if _as_utc(row.created_at) else None,
            }
        )

    if severity:
        items = [item for item in items if str(item.get("severity") or "").upper() == str(severity).upper()]
    if anomaly_type:
        items = [item for item in items if str(item.get("type") or "").upper() == str(anomaly_type).upper()]

    return {
        "window": window,
        "total_anomalies": len(items),
        "items": items[:500],
    }


def _bybit_market_read(symbol: str) -> dict:
    load_dotenv("/app/backend/.env", override=True)
    base_url = str(os.environ.get("BYBIT_TESTNET_BASE_URL") or "https://api-testnet.bybit.com").strip()
    try:
        ticker_resp = httpx.get(
            f"{base_url}/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
            timeout=10,
        )
        book_resp = httpx.get(
            f"{base_url}/v5/market/orderbook",
            params={"category": "linear", "symbol": symbol, "limit": 5},
            timeout=10,
        )
        ticker_data = ticker_resp.json() if ticker_resp.status_code == 200 else {}
        book_data = book_resp.json() if book_resp.status_code == 200 else {}
        mark_price = _safe_float((((ticker_data.get("result") or {}).get("list") or [{}])[0]).get("markPrice"), 0.0)
        bid = _safe_float((((book_data.get("result") or {}).get("b") or [[0]])[0])[0], 0.0)
        ask = _safe_float((((book_data.get("result") or {}).get("a") or [[0]])[0])[0], 0.0)
        return {
            "ok": ticker_resp.status_code == 200 and book_resp.status_code == 200 and mark_price > 0,
            "mark_price": mark_price,
            "best_bid": bid,
            "best_ask": ask,
            "degrade_mode": not (ticker_resp.status_code == 200 and book_resp.status_code == 200),
            "http_status": {"ticker": ticker_resp.status_code, "orderbook": book_resp.status_code},
            "base_url": base_url,
        }
    except Exception as exc:
        return {
            "ok": False,
            "mark_price": 0.0,
            "best_bid": 0.0,
            "best_ask": 0.0,
            "degrade_mode": True,
            "error": str(exc),
            "base_url": base_url,
        }


def _create_simulation_events(db: Session, *, intent_id: str, mode: str, payload: dict) -> None:
    db.add(
        ExecutionIntentEvent(
            id=str(uuid.uuid4()),
            intent_id=intent_id,
            event_type="EXECUTION_SIMULATION_SIGNAL",
            event_status="CREATED",
            payload={"mode": mode, **payload},
        )
    )
    db.add(
        ExecutionIntentEvent(
            id=str(uuid.uuid4()),
            intent_id=intent_id,
            event_type="EXECUTION_SIMULATION_DECISION",
            event_status="SUBMITTED",
            payload={"mode": mode, **payload},
        )
    )
    db.add(
        ExecutionIntentEvent(
            id=str(uuid.uuid4()),
            intent_id=intent_id,
            event_type="EXECUTION_SIMULATION_RISK",
            event_status="ACKED",
            payload={"mode": mode, **payload},
        )
    )


def _ensure_simulation_strategy_seed(db: Session, *, requested_by: str) -> tuple[str, str]:
    strategy_id = "execution_safety_simulation"
    strategy_version_id = "execution_safety_simulation_v1"

    strategy = db.query(StrategyDefinition).filter(StrategyDefinition.strategy_id == strategy_id).first()
    if not strategy:
        strategy = StrategyDefinition(
            strategy_id=strategy_id,
            name="Execution Safety Simulation",
            code="execution_safety_simulation",
            description="Synthetic strategy for execution safety dry-run/shadow simulation",
            owner_type="system",
            owner_name="execution-safety",
            category="execution_safety",
            tags=["simulation", "dry-run", "shadow"],
            created_by=requested_by,
            status="active",
            active_version_id=strategy_version_id,
        )
        db.add(strategy)
    elif not strategy.active_version_id:
        strategy.active_version_id = strategy_version_id

    version = db.query(StrategyVersion).filter(StrategyVersion.version_id == strategy_version_id).first()
    if not version:
        version = StrategyVersion(
            version_id=strategy_version_id,
            strategy_id=strategy_id,
            version_number=1,
            config_json={
                "engine": "execution_safety_p1",
                "mode": "simulation",
                "supports": ["dry-run", "shadow"],
            },
            config_schema_version="1.0",
            created_by=requested_by,
            version_hash=uuid.uuid4().hex,
        )
        db.add(version)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        strategy = db.query(StrategyDefinition).filter(StrategyDefinition.strategy_id == strategy_id).first()
        version = db.query(StrategyVersion).filter(StrategyVersion.version_id == strategy_version_id).first()
        if not strategy or not version:
            raise

    return strategy_id, strategy_version_id


def run_execution_simulation(
    db: Session,
    *,
    mode: str,
    symbol: str = "BTCUSDT",
    qty: float = 0.001,
    side: str = "BUY",
    requested_by: str,
) -> dict:
    normalized_mode = str(mode or "dry-run").strip().lower()
    if normalized_mode not in {"dry-run", "shadow"}:
        raise ValueError("invalid_mode")

    market = _bybit_market_read(symbol)
    mark = market.get("mark_price") or 0.0
    if mark <= 0:
        mark = 1000.0
    spread = max((market.get("best_ask") or mark) - (market.get("best_bid") or mark), 0.0)
    slippage = round(min(max(spread / mark if mark else 0.001, 0.0005), 0.01), 6)
    expected_fill = mark * (1 + slippage if str(side).upper() == "BUY" else 1 - slippage)
    expected_pnl = round((expected_fill - mark) * qty * (1 if str(side).upper() == "BUY" else -1), 4)
    notional = round(expected_fill * qty, 4)
    confidence = 0.88 if market.get("ok") else 0.62

    strategy_id, strategy_version_id = _ensure_simulation_strategy_seed(db, requested_by=requested_by)

    correlation_id = f"sim-{normalized_mode}-{uuid.uuid4().hex[:16]}"
    intent_id = f"sim-intent-{uuid.uuid4().hex[:16]}"
    intent = ExecutionIntent(
        intent_id=intent_id,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        account_id="simulation",
        symbol=symbol,
        side=str(side).upper(),
        order_type="MARKET",
        quantity=qty,
        price_reference={"mode": normalized_mode, "mark_price": mark},
        decision_hash=uuid.uuid4().hex,
        context_hash=uuid.uuid4().hex,
        intent_hash=uuid.uuid4().hex,
        correlation_id=correlation_id,
        status="RECONCILED" if normalized_mode == "shadow" else "ACKED",
        metadata={"simulation_mode": normalized_mode, "degrade_mode": bool(market.get("degrade_mode"))},
    )
    db.add(intent)
    db.flush()

    _create_simulation_events(
        db,
        intent_id=intent_id,
        mode=normalized_mode,
        payload={
            "request_id": f"req-{uuid.uuid4().hex[:16]}",
            "execution_id": f"exe-{uuid.uuid4().hex[:16]}",
            "session_id": f"ses-{uuid.uuid4().hex[:16]}",
            "correlation_id": correlation_id,
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "expected_fill_price": expected_fill,
        },
    )
    db.commit()

    create_audit_log(
        db,
        action=f"execution_simulation_{normalized_mode}",
        entity_type="execution_intent",
        entity_id=intent_id,
        actor_user_id=requested_by,
        actor_role="user",
        severity="info",
        details={
            "actor_type": "user",
            "actor_id": requested_by,
            "action": normalized_mode,
            "target_type": "execution_intent",
            "target_id": intent_id,
            "reason": "simulation_run",
            "before_state": "CREATED",
            "after_state": intent.status,
            "correlation_id": correlation_id,
        },
    )

    return {
        "mode": normalized_mode,
        "symbol": symbol,
        "qty": qty,
        "side": str(side).upper(),
        "expected_fill_price": round(expected_fill, 4),
        "expected_slippage": slippage,
        "expected_pnl": expected_pnl,
        "risk_exposure": {
            "notional": notional,
            "max_drawdown_estimate": round(notional * 0.015, 4),
            "leverage_assumed": 1,
        },
        "divergence_from_real_market": {
            "mark_price": round(mark, 4),
            "abs_diff": round(abs(expected_fill - mark), 6),
            "pct_diff": round(abs(expected_fill - mark) / mark if mark else 0.0, 6),
        },
        "degrade_mode": bool(market.get("degrade_mode")),
        "confidence": round(confidence, 2),
        "intent_id": intent_id,
        "correlation_id": correlation_id,
    }
