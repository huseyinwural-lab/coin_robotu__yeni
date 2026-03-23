import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from db import get_db, redis_client
from deps import require_admin, require_super_admin
from models import AuditLog, SignalGovernanceDecision, StrategyObservabilityEvent, SystemAlert, User
from services.audit_service import create_audit_log
from services.strategy_observability_service import (
    get_rejection_analytics,
    get_score_metrics,
    get_strategy_observability_report,
    get_top_signals,
    parse_window_to_since,
)

router = APIRouter(prefix="/admin/strategy", tags=["admin_strategy_observability"])

PREVIEW_TOKEN_TTL_SECONDS = 600
PREVIEW_TOKEN_KEY_PREFIX = "strategy:signal_preview"
SCORE_CONFIG_KEY = "strategy:score_config:v1"
SCORE_OVERRIDE_LOG_KEY = "strategy:score_override_logs:v1"


class TopSignalsSimulateRequest(BaseModel):
    signal_ids: list[str] = Field(..., min_length=1, max_length=50)


class TopSignalsExecuteRequest(BaseModel):
    signal_ids: list[str] = Field(..., min_length=1, max_length=50)
    preview_token: str
    confirm: bool = False
    reason: str = Field(..., min_length=3)


class TopSignalsBulkSimulateRequest(BaseModel):
    window: str = "24h"
    top_n: int = Field(default=10, ge=1, le=50)


class TopSignalsBulkExecuteRequest(BaseModel):
    mode: Literal["preview", "confirm"] = "preview"
    window: str = "24h"
    top_n: int = Field(default=10, ge=1, le=50)
    preview_token: str | None = None
    confirm: bool = False
    reason: str | None = None


class ScoreConfigUpdateRequest(BaseModel):
    threshold: float = Field(..., ge=0, le=1)
    factor_weights: dict[str, float] = Field(default_factory=dict)
    per_strategy: dict[str, dict] = Field(default_factory=dict)
    reason: str = Field(..., min_length=3)


class ScoreOverrideRequest(BaseModel):
    signal_id: str
    override_delta: float = Field(..., ge=-1.0, le=1.0)
    reason: str = Field(..., min_length=3)


class ScorePreviewRequest(BaseModel):
    threshold: float = Field(..., ge=0, le=1)
    factor_weights: dict[str, float] = Field(default_factory=dict)
    strategy_id: str | None = None
    top_n: int = Field(default=20, ge=1, le=50)


class ScoreAutoTuningToggleRequest(BaseModel):
    enabled: bool
    reason: str = Field(..., min_length=3)


class SignalApproveRequest(BaseModel):
    signal_id: str
    reason: str | None = None
    metadata: dict = Field(default_factory=dict)


class SignalRejectRequest(BaseModel):
    signal_id: str
    reason: str = Field(..., min_length=3)
    metadata: dict = Field(default_factory=dict)


def _role_value(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


def _signal_to_dict(row: StrategyObservabilityEvent, governance_status: str = "pending", governance_reason: str | None = None) -> dict:
    return {
        "signal_id": row.id,
        "symbol": row.symbol,
        "strategy_id": row.strategy_id,
        "market_regime": row.market_regime,
        "event_type": row.event_type,
        "base_score": row.base_score,
        "adjusted_score": row.adjusted_score,
        "score_delta": row.score_delta,
        "selection_rank": row.selection_rank,
        "trend_strength": row.trend_strength,
        "relative_volume": row.relative_volume,
        "hard_gate_pass": row.hard_gate_pass,
        "rejection_reason": row.rejection_reason,
        "reject_reasons": row.reject_reasons or [],
        "decision_path": row.decision_path or [],
        "event_metadata": row.event_metadata or {},
        "governance_status": governance_status,
        "governance_reason": governance_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _governance_map(db: Session, signal_ids: list[str]) -> dict[str, SignalGovernanceDecision]:
    if not signal_ids:
        return {}
    rows = db.query(SignalGovernanceDecision).filter(SignalGovernanceDecision.signal_id.in_(signal_ids)).all()
    return {row.signal_id: row for row in rows}


def _signal_with_governance(row: StrategyObservabilityEvent, governance_map: dict[str, SignalGovernanceDecision]) -> dict:
    governance = governance_map.get(row.id)
    return _signal_to_dict(
        row,
        governance_status=(governance.status if governance else "pending"),
        governance_reason=(governance.reason if governance else None),
    )


def _set_signal_governance(
    db: Session,
    *,
    signal_id: str,
    status_value: str,
    actor_id: str,
    reason: str | None,
    metadata: dict | None,
) -> SignalGovernanceDecision:
    row = db.query(SignalGovernanceDecision).filter(SignalGovernanceDecision.signal_id == signal_id).first()
    if row is None:
        row = SignalGovernanceDecision(
            signal_id=signal_id,
            status=status_value,
            actor_id=actor_id,
            reason=reason,
            metadata_payload=metadata or {},
        )
        db.add(row)
    else:
        row.status = status_value
        row.actor_id = actor_id
        row.reason = reason
        row.metadata_payload = metadata or {}
        row.acted_at = datetime.now(timezone.utc)
    return row


def _default_score_config() -> dict:
    return {
        "threshold": 0.65,
        "factor_weights": {
            "base_score": 0.55,
            "trend_strength": 0.25,
            "relative_volume": 0.20,
        },
        "per_strategy": {},
        "auto_tuning_enabled": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_score_config() -> dict:
    raw = redis_client.get(SCORE_CONFIG_KEY)
    if not raw:
        return _default_score_config()
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return _default_score_config()
        return parsed
    except Exception:
        return _default_score_config()


def _save_score_config(config: dict) -> None:
    redis_client.set(SCORE_CONFIG_KEY, json.dumps(config, ensure_ascii=False))


def _save_preview_token(payload: dict) -> str:
    token = str(uuid.uuid4())
    key = f"{PREVIEW_TOKEN_KEY_PREFIX}:{token}"
    redis_client.set(key, json.dumps(payload, ensure_ascii=False))
    redis_client.expire(key, PREVIEW_TOKEN_TTL_SECONDS)
    return token


def _read_preview_token(token: str) -> dict | None:
    key = f"{PREVIEW_TOKEN_KEY_PREFIX}:{token}"
    raw = redis_client.get(key)
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return None


def _fetch_signals_by_ids(db: Session, signal_ids: list[str]) -> list[StrategyObservabilityEvent]:
    return db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id.in_(signal_ids)).all()


def _build_simulation_items(rows: list[StrategyObservabilityEvent], score_config: dict) -> list[dict]:
    threshold = float(score_config.get("threshold", 0.65))
    items = []
    for row in rows:
        adjusted = float(row.adjusted_score or 0)
        items.append(
            {
                "signal_id": row.id,
                "symbol": row.symbol,
                "strategy_id": row.strategy_id,
                "adjusted_score": adjusted,
                "threshold": threshold,
                "simulation_result": "PASS" if adjusted >= threshold else "REJECT",
                "risk_note": "threshold_check",
            }
        )
    return items


def _safe_parse_iso(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    try:
        if normalized.endswith("Z"):
            normalized = normalized.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _resolve_time_range(window: str, time_from: str | None, time_to: str | None) -> tuple[str, datetime, datetime]:
    normalized, default_since = parse_window_to_since(window)
    now = datetime.now(timezone.utc)
    start_at = _safe_parse_iso(time_from) or default_since
    end_at = _safe_parse_iso(time_to) or now
    if end_at < start_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_time_range")
    return normalized, start_at, end_at


def _query_strategy_rows(
    db: Session,
    *,
    strategy_id: str | None,
    window: str,
    time_from: str | None,
    time_to: str | None,
    limit: int = 1500,
) -> tuple[str, datetime, datetime, list[StrategyObservabilityEvent]]:
    normalized, start_at, end_at = _resolve_time_range(window, time_from, time_to)
    query = db.query(StrategyObservabilityEvent).filter(
        StrategyObservabilityEvent.created_at >= start_at,
        StrategyObservabilityEvent.created_at <= end_at,
    )
    if strategy_id:
        query = query.filter(StrategyObservabilityEvent.strategy_id == strategy_id)
    rows = query.order_by(StrategyObservabilityEvent.created_at.asc()).limit(limit).all()
    return normalized, start_at, end_at, rows


def _build_trend_rows(rows: list[StrategyObservabilityEvent], *, window: str) -> list[dict]:
    if window == "24h":
        formatter = "%Y-%m-%d %H:00"
    else:
        formatter = "%Y-%m-%d"

    bucket_map: dict[str, dict] = {}
    for row in rows:
        if not row.created_at:
            continue
        bucket_key = row.created_at.astimezone(timezone.utc).strftime(formatter)
        bucket = bucket_map.setdefault(
            bucket_key,
            {
                "bucket": bucket_key,
                "selected_count": 0,
                "rejected_count": 0,
                "avg_adjusted_score": 0.0,
                "avg_base_score": 0.0,
                "total": 0,
                "sum_adjusted": 0.0,
                "sum_base": 0.0,
            },
        )
        bucket["total"] += 1
        bucket["sum_adjusted"] += float(row.adjusted_score or 0)
        bucket["sum_base"] += float(row.base_score or 0)
        if row.event_type == "selected_for_execution":
            bucket["selected_count"] += 1
        else:
            bucket["rejected_count"] += 1

    trend_rows = []
    for bucket_key in sorted(bucket_map.keys()):
        bucket = bucket_map[bucket_key]
        total = max(int(bucket["total"]), 1)
        trend_rows.append(
            {
                "bucket": bucket_key,
                "selected_count": int(bucket["selected_count"]),
                "rejected_count": int(bucket["rejected_count"]),
                "avg_adjusted_score": round(float(bucket["sum_adjusted"]) / total, 4),
                "avg_base_score": round(float(bucket["sum_base"]) / total, 4),
            }
        )
    return trend_rows


def _rows_to_export_payload(rows: list[StrategyObservabilityEvent]) -> list[dict]:
    return [
        {
            "signal_id": row.id,
            "strategy_id": row.strategy_id,
            "symbol": row.symbol,
            "event_type": row.event_type,
            "market_regime": row.market_regime,
            "base_score": float(row.base_score or 0),
            "adjusted_score": float(row.adjusted_score or 0),
            "score_delta": float(row.score_delta or 0),
            "selection_rank": row.selection_rank,
            "rejection_reason": row.rejection_reason,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _serialize_action_timeline_items(
    *,
    audit_rows: list[AuditLog],
    system_alert_rows: list[SystemAlert],
    strategy_filter: str | None,
    signal_strategy_map: dict[str, str],
) -> list[dict]:
    timeline: list[dict] = []
    manual_by_chain: dict[str, list[dict]] = {}

    ordered_audit_rows = sorted(audit_rows, key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc))

    for row in ordered_audit_rows:
        details = row.details or {}
        row_strategy_id = str(details.get("strategy_id") or "").strip() or None
        if not row_strategy_id:
            signal_ids = [str(item) for item in (details.get("signal_ids") or [])]
            for signal_id in signal_ids:
                if signal_id in signal_strategy_map:
                    row_strategy_id = signal_strategy_map[signal_id]
                    break

        if strategy_filter and row_strategy_id != strategy_filter:
            continue

        chain_id = str(details.get("chain_id") or details.get("preview_token") or details.get("request_id") or row.entity_id or row.id)
        manual_by_chain.setdefault(chain_id, []).append(
            {
                "event_id": row.id,
                "timestamp": row.created_at,
            }
        )

        explicit_parent = str(details.get("parent_event_id") or details.get("parent_audit_id") or "").strip() or None

        timeline.append(
            {
                "event_id": row.id,
                "event_type": "manual_action",
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "strategy_id": row_strategy_id,
                "action": row.action,
                "actor_role": row.actor_role,
                "reason": details.get("reason"),
                "impact_payload": details.get("state_snapshot") or details.get("after_payload") or details,
                "chain_id": chain_id,
                "parent_event_id": explicit_parent,
                "chain_ref": chain_id,
                "is_seed_chain": _is_seed_chain(chain_id, details),
            }
        )

    for row in system_alert_rows:
        details = row.details or {}
        blob = json.dumps(details, ensure_ascii=False)
        row_strategy_id = str(details.get("strategy_id") or "").strip() or None
        if not row_strategy_id:
            for signal_id, signal_strategy in signal_strategy_map.items():
                if signal_id in blob:
                    row_strategy_id = signal_strategy
                    break

        if strategy_filter and row_strategy_id != strategy_filter:
            continue

        chain_id = str(details.get("chain_id") or row.entity_key or row.state_key or row.root_cause_code or row.id)

        manual_candidates = manual_by_chain.get(chain_id, [])
        fallback_parent = None
        if manual_candidates:
            if row.created_at:
                eligible = [item for item in manual_candidates if item.get("timestamp") and item["timestamp"] <= row.created_at]
                selected = eligible[-1] if eligible else manual_candidates[-1]
            else:
                selected = manual_candidates[-1]
            fallback_parent = str(selected.get("event_id") or "").strip() or None

        explicit_parent = str(details.get("parent_event_id") or details.get("parent_audit_id") or "").strip() or None

        timeline.append(
            {
                "event_id": row.id,
                "event_type": "system_reaction",
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "strategy_id": row_strategy_id,
                "action": row.alert_type,
                "actor_role": "system",
                "reason": row.message,
                "impact_payload": details,
                "severity": row.severity,
                "status": row.status,
                "chain_id": chain_id,
                "parent_event_id": explicit_parent or fallback_parent,
                "chain_ref": chain_id,
                "alert_detail_path": f"/api/admin/action-center/alerts/{row.id}/detail",
                "is_seed_chain": _is_seed_chain(chain_id, details),
            }
        )

    timeline.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return timeline


def _safe_iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        if normalized.endswith("Z"):
            normalized = normalized.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _safe_to_float(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        normalized = str(value).strip()
        if not normalized:
            return None
        return float(normalized)
    except Exception:
        return None


def _extract_metric_delta(payload: dict, keys: list[str]) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        numeric_value = _safe_to_float(value)
        if numeric_value is not None:
            return numeric_value
        if isinstance(value, dict):
            for delta_key in ["delta", "change", "diff", "value_delta"]:
                delta_value = _safe_to_float(value.get(delta_key))
                if delta_value is not None:
                    return delta_value
            before_value = _safe_to_float(value.get("before"))
            after_value = _safe_to_float(value.get("after"))
            if before_value is not None and after_value is not None:
                return after_value - before_value
    return None


def _delta_label(label: str, delta: float | None) -> str | None:
    if delta is None:
        return None
    if abs(delta) < 1e-9:
        return f"{label} = (0)"
    direction = "↑" if delta > 0 else "↓"
    normalized = round(delta, 4)
    sign = "+" if normalized > 0 else ""
    return f"{label} {direction} ({sign}{normalized})"


def _build_impact_labels(node: dict) -> list[str]:
    payload = node.get("impact_payload")
    if not isinstance(payload, dict):
        payload = {}

    labels: list[str] = []
    risk_delta = _extract_metric_delta(
        payload,
        ["risk_delta", "risk_change", "var_change", "risk_breaches_delta", "risk_breaches", "realized_risk_drop"],
    )
    exposure_delta = _extract_metric_delta(payload, ["exposure_delta", "exposure_change", "notional_exposure_delta"])
    accepted_delta = _extract_metric_delta(
        payload,
        ["selected_signals", "selected_signals_delta", "accepted_signals", "accepted_signals_delta"],
    )
    rejected_delta = _extract_metric_delta(
        payload,
        ["rejected_signals", "rejected_signals_delta", "reject_signals", "reject_count_delta"],
    )

    for candidate in [
        _delta_label("Risk", risk_delta),
        _delta_label("Exposure", exposure_delta),
        _delta_label("Signals accepted", accepted_delta),
        _delta_label("Signals rejected", rejected_delta),
    ]:
        if candidate:
            labels.append(candidate)

    if str(node.get("event_type") or "") == "system_reaction":
        reaction_status = str(node.get("status") or "").lower()
        if reaction_status in {"resolved", "closed"}:
            labels.append("Alert resolved")
        elif reaction_status:
            labels.append("Alert triggered")

    return labels or ["Impact etiketi üretilemedi"]


def _chain_sort_key(node: dict) -> tuple[datetime, str]:
    timestamp = _safe_iso_to_dt(node.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)
    return (timestamp, str(node.get("event_id") or ""))


def _flow_stage_for_node(node: dict) -> str:
    event_type = str(node.get("event_type") or "")
    status_value = str(node.get("status") or "").lower()
    if event_type == "manual_action":
        return "manual_action"
    if event_type == "system_reaction" and status_value in {"resolved", "closed"}:
        return "impact"
    return "system_reaction"


def _is_seed_chain(chain_id: str | None, payload: dict | None) -> bool:
    normalized_chain_id = str(chain_id or "").strip().lower()
    payload_dict = payload if isinstance(payload, dict) else {}
    explicit_marker = bool(payload_dict.get("is_seed_data")) or bool(payload_dict.get("seed_namespace"))
    namespace_marker = str(payload_dict.get("data_namespace") or "").strip().lower().startswith("seed")
    prefixed = normalized_chain_id.startswith("seed::") or normalized_chain_id.startswith("seed-") or normalized_chain_id.startswith("test::")
    return explicit_marker or namespace_marker or prefixed


def _build_root_cause_hint(invalid_reasons: set[str], broken_count: int, root_count: int) -> dict | None:
    if not invalid_reasons:
        return None

    reason_signature = ",".join(sorted(invalid_reasons))
    rules = [
        (
            {"seed_chain_hidden"},
            "seed_chain_hidden",
            "Bu zincir test/seed namespace içinde işaretli. Operasyon ekranında görmek için seed filtresini bilinçli şekilde açın.",
        ),
        (
            {"cycle_detected"},
            "graph_cycle_detected",
            "Parent zincirinde döngü tespit edildi; parent_event_id üretimini tek yönlü olacak şekilde normalize edin.",
        ),
        (
            {"parent_after_child"},
            "parent_timestamp_order_mismatch",
            "Parent zamanı child’dan sonra görünüyor; event timestamp kaynağı ve ingestion sırasını tutarlı hale getirin.",
        ),
        (
            {"multiple_roots", "parent_not_found"},
            "missing_parent_mapping_with_split_roots",
            "Parent referansı eksik ve zincir birden fazla köke ayrılmış; chain_id + parent_event_id eşlemesini tek kök etrafında yeniden bağlayın.",
        ),
        (
            {"parent_not_found"},
            "missing_parent_mapping",
            "Parent event bulunamadı; parent_event_id üretimi ile retention penceresini kontrol edip eksik parent kayıtlarını geri doldurun.",
        ),
        (
            {"self_parent_reference"},
            "self_parent_reference",
            "Event kendi parent’ı olarak işaretlenmiş; parent atama kuralında self-reference blokajı ekleyin.",
        ),
        (
            {"missing_manual_anchor"},
            "missing_manual_anchor",
            "Sistem reaksiyonu var ama manuel anchor yok; manuel aksiyon kaydının chain başlatma adımını zorunlu hale getirin.",
        ),
        (
            {"detached_node"},
            "detached_nodes_detected",
            "Bazı node’lar zincire bağlanamadı; correlation/chain mapping alanlarını normalize edip detached kayıtları yeniden ilişkilendirin.",
        ),
    ]

    matched_rule_key = "generic_chain_integrity"
    matched_hint = "Chain bütünlüğünde kırık tespit edildi; parent-child mapping ve event ingestion sırasını birlikte gözden geçirin."
    for required_reasons, rule_key, hint in rules:
        if required_reasons.issubset(invalid_reasons):
            matched_rule_key = rule_key
            matched_hint = hint
            break

    return {
        "classification": "ÖNERİ (kesin neden değildir)",
        "deterministic": True,
        "rule_key": matched_rule_key,
        "reason_signature": reason_signature,
        "hint": matched_hint,
        "metrics": {
            "broken_links_count": int(broken_count),
            "root_nodes_count": int(root_count),
        },
    }


def _enrich_chain_nodes(chain_nodes: list[dict]) -> tuple[list[dict], dict]:
    if not chain_nodes:
        return [], {
            "total_nodes": 0,
            "manual_action_count": 0,
            "system_reaction_count": 0,
            "broken_links_count": 0,
            "root_nodes_count": 0,
            "is_chain_valid": False,
            "invalid_reasons": ["chain_empty"],
            "root_cause_hint": {
                "classification": "ÖNERİ (kesin neden değildir)",
                "deterministic": True,
                "rule_key": "chain_empty",
                "reason_signature": "chain_empty",
                "hint": "Bu chain için görünür event bulunamadı; filtre penceresi, strategy_id ve scope alanlarını kontrol edin.",
                "metrics": {"broken_links_count": 0, "root_nodes_count": 0},
            },
            "max_depth": 0,
            "default_view": "summary",
            "lazy_load_recommended": False,
            "virtualization_recommended": False,
        }

    ordered = sorted([dict(item) for item in chain_nodes], key=_chain_sort_key)
    node_map = {str(item.get("event_id") or ""): item for item in ordered if str(item.get("event_id") or "").strip()}
    children_map: dict[str, list[dict]] = {}
    roots: list[dict] = []
    invalid_reasons: set[str] = set()

    for node in ordered:
        node_id = str(node.get("event_id") or "").strip()
        parent_id = str(node.get("parent_event_id") or "").strip() or None
        node["impact_labels"] = _build_impact_labels(node)
        node["flow_stage"] = _flow_stage_for_node(node)
        node["relation_status"] = "root"
        node["is_broken_link"] = False
        node["broken_reason"] = None

        if not node_id:
            node["relation_status"] = "broken_link"
            node["is_broken_link"] = True
            node["broken_reason"] = "missing_event_id"
            invalid_reasons.add("missing_event_id")
            roots.append(node)
            continue

        if parent_id is None:
            roots.append(node)
            continue

        if parent_id == node_id:
            node["relation_status"] = "broken_link"
            node["is_broken_link"] = True
            node["broken_reason"] = "self_parent_reference"
            invalid_reasons.add("self_parent_reference")
            roots.append(node)
            continue

        parent_node = node_map.get(parent_id)
        if parent_node is None:
            node["relation_status"] = "broken_link"
            node["is_broken_link"] = True
            node["broken_reason"] = "parent_not_found"
            invalid_reasons.add("parent_not_found")
            roots.append(node)
            continue

        parent_ts = _safe_iso_to_dt(parent_node.get("timestamp"))
        child_ts = _safe_iso_to_dt(node.get("timestamp"))
        if parent_ts and child_ts and parent_ts > child_ts:
            node["relation_status"] = "broken_link"
            node["is_broken_link"] = True
            node["broken_reason"] = "parent_after_child"
            invalid_reasons.add("parent_after_child")
            roots.append(node)
            continue

        node["relation_status"] = "linked"
        children_map.setdefault(parent_id, []).append(node)

    if len(roots) > 1:
        invalid_reasons.add("multiple_roots")

    visited: set[str] = set()
    stack: set[str] = set()
    traversed: list[dict] = []

    def visit(node: dict, depth: int) -> None:
        node_id = str(node.get("event_id") or "").strip()
        if not node_id:
            node["causal_depth"] = depth
            traversed.append(node)
            return
        if node_id in stack:
            node["relation_status"] = "broken_link"
            node["is_broken_link"] = True
            node["broken_reason"] = "cycle_detected"
            invalid_reasons.add("cycle_detected")
            return
        if node_id in visited:
            return
        stack.add(node_id)
        node["causal_depth"] = depth
        traversed.append(node)
        for child in sorted(children_map.get(node_id, []), key=_chain_sort_key):
            visit(child, depth + 1)
        stack.remove(node_id)
        visited.add(node_id)

    for root in sorted(roots, key=_chain_sort_key):
        visit(root, 0)

    for node in ordered:
        node_id = str(node.get("event_id") or "").strip()
        if node_id and node_id in visited:
            continue
        node["relation_status"] = "broken_link"
        node["is_broken_link"] = True
        node["broken_reason"] = node.get("broken_reason") or "detached_node"
        invalid_reasons.add("detached_node")
        visit(node, 0)

    for index, node in enumerate(traversed, start=1):
        node["causal_index"] = index

    manual_count = len([item for item in traversed if str(item.get("event_type") or "") == "manual_action"])
    system_count = len([item for item in traversed if str(item.get("event_type") or "") == "system_reaction"])
    broken_count = len([item for item in traversed if bool(item.get("is_broken_link"))])
    if manual_count == 0 and system_count > 0:
        invalid_reasons.add("missing_manual_anchor")

    summary = {
        "total_nodes": len(traversed),
        "manual_action_count": manual_count,
        "system_reaction_count": system_count,
        "broken_links_count": broken_count,
        "root_nodes_count": len(roots),
        "is_chain_valid": broken_count == 0 and len(invalid_reasons) == 0,
        "invalid_reasons": sorted(invalid_reasons),
        "root_cause_hint": _build_root_cause_hint(invalid_reasons, broken_count, len(roots)),
        "max_depth": max([int(item.get("causal_depth") or 0) for item in traversed], default=0),
        "default_view": "summary",
        "lazy_load_recommended": len(traversed) > 120,
        "virtualization_recommended": len(traversed) > 500,
    }
    return traversed, summary


@router.get("/top-signals")
def top_signals(
    window: str = Query(default="24h"),
    top_n: int = Query(default=10, ge=1, le=50),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = get_top_signals(db, window=window, top_n=top_n)
    signal_ids = [str(item.get("signal_id")) for item in (payload.get("items") or []) if item.get("signal_id")]
    governance = _governance_map(db, signal_ids)
    items = []
    for item in payload.get("items") or []:
        signal_id = str(item.get("signal_id") or "")
        decision = governance.get(signal_id)
        items.append(
            {
                **item,
                "governance_status": decision.status if decision else "pending",
                "governance_reason": decision.reason if decision else None,
            }
        )
    return {
        **payload,
        "items": items,
    }


@router.post("/signals/approve")
def approve_signal(
    payload: SignalApproveRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    signal_row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == payload.signal_id).first()
    if signal_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")

    governance_row = _set_signal_governance(
        db,
        signal_id=payload.signal_id,
        status_value="approved",
        actor_id=current_admin.id,
        reason=payload.reason,
        metadata=payload.metadata,
    )
    create_audit_log(
        db,
        action="strategy_signal_approve",
        entity_type="strategy_signal",
        entity_id=payload.signal_id,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "metadata": payload.metadata,
            "status": "approved",
        },
    )
    db.commit()
    return {
        "status": "success",
        "message": "signal_approved",
        "signal_id": payload.signal_id,
        "governance_status": governance_row.status,
    }


@router.post("/signals/reject")
def reject_signal(
    payload: SignalRejectRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    signal_row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == payload.signal_id).first()
    if signal_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")

    governance_row = _set_signal_governance(
        db,
        signal_id=payload.signal_id,
        status_value="rejected",
        actor_id=current_admin.id,
        reason=payload.reason,
        metadata=payload.metadata,
    )
    create_audit_log(
        db,
        action="strategy_signal_reject",
        entity_type="strategy_signal",
        entity_id=payload.signal_id,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "metadata": payload.metadata,
            "status": "rejected",
        },
    )
    db.commit()
    return {
        "status": "success",
        "message": "signal_rejected",
        "signal_id": payload.signal_id,
        "governance_status": governance_row.status,
    }


@router.post("/top-signals/simulate")
def simulate_top_signals(
    payload: TopSignalsSimulateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = _fetch_signals_by_ids(db, payload.signal_ids)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signals_not_found")

    simulation_items = _build_simulation_items(rows, _load_score_config())
    preview_payload = {
        "type": "selected_simulation",
        "signal_ids": sorted([row.id for row in rows]),
        "actor_id": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = _save_preview_token(preview_payload)
    create_audit_log(
        db,
        action="strategy_top_signals_simulate",
        entity_type="strategy_signal",
        entity_id=preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "signal_ids": preview_payload["signal_ids"],
            "preview_token": preview_token,
        },
    )
    db.commit()
    return {
        "status": "success",
        "message": "simulation_completed",
        "preview_token": preview_token,
        "items": simulation_items,
    }


@router.post("/top-signals/execute")
def execute_top_signals(
    payload: TopSignalsExecuteRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    preview = _read_preview_token(payload.preview_token)
    if not preview:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_invalid_or_expired")
    if sorted(payload.signal_ids) != sorted(preview.get("signal_ids", [])):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_signal_mismatch")

    rows = _fetch_signals_by_ids(db, payload.signal_ids)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signals_not_found")

    governance = _governance_map(db, [row.id for row in rows])
    not_approved = [
        row.id
        for row in rows
        if (governance.get(row.id).status if governance.get(row.id) else "pending") != "approved"
    ]
    if not_approved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"signals_not_approved_for_execution:{','.join(sorted(not_approved))}",
        )

    executed_items = []
    for row in rows:
        metadata = dict(row.event_metadata or {})
        metadata["last_execution_action"] = "executed"
        metadata["last_execution_reason"] = payload.reason
        row.event_metadata = metadata
        _set_signal_governance(
            db,
            signal_id=row.id,
            status_value="executed",
            actor_id=current_admin.id,
            reason=payload.reason,
            metadata={"source": "execute_top_signals", "preview_token": payload.preview_token},
        )
        executed_items.append({"signal_id": row.id, "symbol": row.symbol, "status": "EXECUTED"})

    create_audit_log(
        db,
        action="strategy_top_signals_execute",
        entity_type="strategy_signal",
        entity_id=payload.preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "signal_ids": sorted(payload.signal_ids),
            "preview_token": payload.preview_token,
            "simulation_before_execution": True,
        },
    )
    db.commit()
    return {
        "status": "success",
        "message": "execute_completed",
        "executed_count": len(executed_items),
        "items": executed_items,
    }


@router.post("/top-signals/bulk-simulate")
def bulk_simulate_top_signals(
    payload: TopSignalsBulkSimulateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    top_payload = get_top_signals(db, window=payload.window, top_n=payload.top_n)
    signal_ids = [item["signal_id"] for item in top_payload.get("items", []) if item.get("signal_id")]
    if not signal_ids:
        return {"status": "success", "message": "no_signals", "preview_token": None, "items": []}

    rows = _fetch_signals_by_ids(db, signal_ids)
    simulation_items = _build_simulation_items(rows, _load_score_config())
    preview_payload = {
        "type": "bulk_simulation",
        "signal_ids": sorted(signal_ids),
        "actor_id": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = _save_preview_token(preview_payload)
    create_audit_log(
        db,
        action="strategy_top_signals_bulk_simulate",
        entity_type="strategy_signal",
        entity_id=preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={"window": payload.window, "top_n": payload.top_n, "signal_ids": preview_payload["signal_ids"]},
    )
    db.commit()
    return {
        "status": "success",
        "message": "bulk_simulation_completed",
        "preview_token": preview_token,
        "items": simulation_items,
    }


@router.post("/top-signals/bulk-execute")
def bulk_execute_top_signals(
    payload: TopSignalsBulkExecuteRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if payload.mode == "preview":
        top_payload = get_top_signals(db, window=payload.window, top_n=payload.top_n)
        signal_ids = [item["signal_id"] for item in top_payload.get("items", []) if item.get("signal_id")]
        rows = _fetch_signals_by_ids(db, signal_ids)
        simulation_items = _build_simulation_items(rows, _load_score_config()) if rows else []
        preview_payload = {
            "type": "bulk_execute_preview",
            "signal_ids": sorted(signal_ids),
            "actor_id": current_admin.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        preview_token = _save_preview_token(preview_payload)
        create_audit_log(
            db,
            action="strategy_top_signals_bulk_execute_preview",
            entity_type="strategy_signal",
            entity_id=preview_token,
            actor_user_id=current_admin.id,
            actor_role=_role_value(current_admin),
            details={"window": payload.window, "top_n": payload.top_n, "signal_ids": preview_payload["signal_ids"]},
        )
        db.commit()
        return {
            "status": "success",
            "message": "bulk_execute_preview_ready",
            "preview_token": preview_token,
            "items": simulation_items,
        }

    if payload.mode != "confirm":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_mode")
    if not payload.preview_token:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_required")
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirm_required")
    if not (payload.reason and payload.reason.strip()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="reason_required")

    preview = _read_preview_token(payload.preview_token)
    if not preview:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="preview_token_invalid_or_expired")
    signal_ids = sorted(preview.get("signal_ids", []))
    rows = _fetch_signals_by_ids(db, signal_ids)

    governance = _governance_map(db, [row.id for row in rows])
    not_approved = [
        row.id
        for row in rows
        if (governance.get(row.id).status if governance.get(row.id) else "pending") != "approved"
    ]
    if not_approved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"signals_not_approved_for_execution:{','.join(sorted(not_approved))}",
        )

    for row in rows:
        metadata = dict(row.event_metadata or {})
        metadata["last_execution_action"] = "bulk_executed"
        metadata["last_execution_reason"] = payload.reason
        row.event_metadata = metadata
        _set_signal_governance(
            db,
            signal_id=row.id,
            status_value="executed",
            actor_id=current_admin.id,
            reason=payload.reason,
            metadata={"source": "bulk_execute", "preview_token": payload.preview_token},
        )

    create_audit_log(
        db,
        action="strategy_top_signals_bulk_execute_confirm",
        entity_type="strategy_signal",
        entity_id=payload.preview_token,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={"reason": payload.reason, "signal_ids": signal_ids, "simulation_before_execution": True},
    )
    db.commit()
    return {
        "status": "success",
        "message": "bulk_execute_completed",
        "executed_count": len(rows),
        "items": [{"signal_id": row.id, "symbol": row.symbol, "status": "EXECUTED"} for row in rows],
    }


@router.get("/score-config")
def get_score_config_endpoint(_: User = Depends(require_admin)):
    return {
        "status": "success",
        "config": _load_score_config(),
    }


@router.put("/score-config")
def update_score_config(
    payload: ScoreConfigUpdateRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    previous = _load_score_config()
    updated = {
        "threshold": payload.threshold,
        "factor_weights": payload.factor_weights,
        "per_strategy": payload.per_strategy,
        "auto_tuning_enabled": bool(previous.get("auto_tuning_enabled", False)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_score_config(updated)
    create_audit_log(
        db,
        action="strategy_score_config_apply",
        entity_type="strategy_score_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "before_payload": previous,
            "after_payload": updated,
        },
    )
    db.commit()
    return {"status": "success", "message": "score_config_updated", "config": updated}


@router.post("/score-preview")
def score_preview(
    payload: ScorePreviewRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    current = _load_score_config()
    top_payload = get_top_signals(db, window="24h", top_n=payload.top_n)
    rows = _fetch_signals_by_ids(db, [item["signal_id"] for item in top_payload.get("items", []) if item.get("signal_id")])
    if payload.strategy_id:
        rows = [row for row in rows if row.strategy_id == payload.strategy_id]

    before_selected = 0
    after_selected = 0
    impact_rows = []
    factor_weights = payload.factor_weights or current.get("factor_weights", {})

    for row in rows:
        current_score = float(row.adjusted_score or 0)
        base = float(row.base_score or 0)
        trend = float(row.trend_strength or 0)
        rel_vol = float(row.relative_volume or 0)
        preview_score = (
            base * float(factor_weights.get("base_score", 0.55))
            + trend * float(factor_weights.get("trend_strength", 0.25))
            + rel_vol * float(factor_weights.get("relative_volume", 0.20))
        )
        if current_score >= float(current.get("threshold", 0.65)):
            before_selected += 1
        if preview_score >= payload.threshold:
            after_selected += 1
        if abs(preview_score - current_score) >= 0.03:
            impact_rows.append(
                {
                    "signal_id": row.id,
                    "symbol": row.symbol,
                    "current_score": round(current_score, 4),
                    "preview_score": round(preview_score, 4),
                    "delta": round(preview_score - current_score, 4),
                }
            )

    return {
        "status": "success",
        "message": "score_preview_ready",
        "state_snapshot": {
            "before_selected": before_selected,
            "after_selected": after_selected,
            "selected_delta": after_selected - before_selected,
            "impact_rows": impact_rows[:20],
        },
    }


@router.post("/score-override")
def score_override(
    payload: ScoreOverrideRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == payload.signal_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")

    before_adjusted = float(row.adjusted_score or 0)
    after_adjusted = min(max(before_adjusted + float(payload.override_delta), 0.0), 1.0)
    row.adjusted_score = after_adjusted
    row.score_delta = round(after_adjusted - float(row.base_score or 0), 6)

    override_record = {
        "signal_id": row.id,
        "symbol": row.symbol,
        "override_delta": float(payload.override_delta),
        "before_adjusted_score": before_adjusted,
        "after_adjusted_score": after_adjusted,
        "reason": payload.reason,
        "actor_id": current_admin.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    redis_client.lpush(SCORE_OVERRIDE_LOG_KEY, json.dumps(override_record, ensure_ascii=False))
    redis_client.ltrim(SCORE_OVERRIDE_LOG_KEY, 0, 999)

    create_audit_log(
        db,
        action="strategy_score_override",
        entity_type="strategy_signal",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "before_payload": {"adjusted_score": before_adjusted},
            "after_payload": {"adjusted_score": after_adjusted},
            **override_record,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "status": "success",
        "message": "score_override_applied",
        "signal": _signal_to_dict(row),
    }


@router.post("/score-auto-tuning/toggle")
def toggle_score_auto_tuning(
    payload: ScoreAutoTuningToggleRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    current = _load_score_config()
    updated = dict(current)
    updated["auto_tuning_enabled"] = bool(payload.enabled)
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_score_config(updated)

    create_audit_log(
        db,
        action="strategy_score_auto_tuning_toggle",
        entity_type="strategy_score_config",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "reason": payload.reason,
            "before_payload": {"auto_tuning_enabled": current.get("auto_tuning_enabled", False)},
            "after_payload": {"auto_tuning_enabled": updated.get("auto_tuning_enabled", False)},
        },
    )
    db.commit()
    return {"status": "success", "message": "auto_tuning_updated", "enabled": bool(payload.enabled)}


@router.get("/signals/{signal_id}/explainability")
def signal_explainability(signal_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == signal_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")

    score_config = _load_score_config()
    metadata = row.event_metadata or {}
    component_scores = metadata.get("component_scores") if isinstance(metadata.get("component_scores"), dict) else {}
    contribution_map = component_scores or {
        "base_score": float(row.base_score or 0),
        "trend_strength": float(row.trend_strength or 0),
        "relative_volume": float(row.relative_volume or 0),
        "score_delta": float(row.score_delta or 0),
    }

    override_history = []
    for item in redis_client.lrange(SCORE_OVERRIDE_LOG_KEY, 0, 200):
        parsed = json.loads(item.decode("utf-8") if isinstance(item, bytes) else item)
        if parsed.get("signal_id") == signal_id:
            override_history.append(parsed)

    timeline_rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == signal_id, AuditLog.action.like("strategy_%"))
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "status": "success",
        "signal": _signal_to_dict(row),
        "factor_weights": score_config.get("factor_weights", {}),
        "contribution_map": contribution_map,
        "triggered_rules": row.decision_path or [],
        "final_decision": row.event_type,
        "override_history": override_history,
        "decision_log": [
            {
                "audit_id": item.id,
                "action": item.action,
                "reason": item.reason,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "details": item.details or {},
            }
            for item in timeline_rows
        ],
    }


@router.get("/rejection-analytics")
def rejection_analytics(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_rejection_analytics(db, window=window)


@router.get("/rejection-analytics/details")
def rejection_analytics_details(
    window: str = Query(default="24h"),
    strategy_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    reason: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _, since = parse_window_to_since(window)
    query = db.query(StrategyObservabilityEvent).filter(
        StrategyObservabilityEvent.created_at >= since,
        or_(
            StrategyObservabilityEvent.event_type == "rejected",
            StrategyObservabilityEvent.rejection_reason.is_not(None),
        ),
    )
    if strategy_id:
        query = query.filter(StrategyObservabilityEvent.strategy_id == strategy_id)
    if symbol:
        query = query.filter(StrategyObservabilityEvent.symbol == symbol.upper())
    if reason:
        token = f"%{reason.strip()}%"
        query = query.filter(
            or_(
                StrategyObservabilityEvent.rejection_reason.ilike(token),
            )
        )

    rows = query.order_by(StrategyObservabilityEvent.created_at.desc()).limit(300).all()
    return {
        "window": window,
        "count": len(rows),
        "items": [_signal_to_dict(row) for row in rows],
    }


@router.get("/rejection-analytics/reasons")
def rejection_analytics_reasons(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    details = rejection_analytics_details(window=window, strategy_id=None, symbol=None, reason=None, _=None, db=db)
    reason_counts: dict[str, int] = {}
    for item in details["items"]:
        reject_reasons = item.get("reject_reasons") or []
        if not reject_reasons and item.get("rejection_reason"):
            reject_reasons = [item["rejection_reason"]]
        for reason_item in reject_reasons:
            key = str(reason_item)
            reason_counts[key] = reason_counts.get(key, 0) + 1
    return {
        "window": window,
        "reasons": [{"reason": key, "count": value} for key, value in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


@router.get("/rejection-analytics/signals/{signal_id}")
def rejection_signal_detail(signal_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id == signal_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signal_not_found")
    return {
        "status": "success",
        "signal": _signal_to_dict(row),
        "actions": {
            "simulate": True,
            "explain": True,
            "retry": True,
        },
    }


@router.get("/observability/strategies")
def strategy_observability_strategy_list(
    window: str = Query(default="24h"),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at, rows = _query_strategy_rows(
        db,
        strategy_id=None,
        window=window,
        time_from=time_from,
        time_to=time_to,
        limit=5000,
    )
    strategy_ids = sorted({str(row.strategy_id) for row in rows if row.strategy_id})
    return {
        "window": normalized,
        "time_from": start_at.isoformat(),
        "time_to": end_at.isoformat(),
        "items": strategy_ids,
        "count": len(strategy_ids),
    }


@router.get("/observability/{strategy_id}/detail")
def strategy_observability_detail(
    strategy_id: str,
    window: str = Query(default="24h"),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at, rows = _query_strategy_rows(
        db,
        strategy_id=strategy_id,
        window=window,
        time_from=time_from,
        time_to=time_to,
        limit=5000,
    )

    selected_rows = [row for row in rows if row.event_type == "selected_for_execution"]
    rejected_rows = [row for row in rows if row.event_type != "selected_for_execution"]
    avg_adjusted = round(sum(float(row.adjusted_score or 0) for row in rows) / max(len(rows), 1), 4)
    avg_base = round(sum(float(row.base_score or 0) for row in rows) / max(len(rows), 1), 4)

    rejection_counts: dict[str, int] = {}
    symbols_counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.rejection_reason or "")
        if reason:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        symbols_counts[row.symbol] = symbols_counts.get(row.symbol, 0) + 1

    trend_rows = _build_trend_rows(rows, window=normalized)
    top_symbols = [
        {"symbol": key, "count": value}
        for key, value in sorted(symbols_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    ]
    rejection_reasons = [
        {"reason": key, "count": value}
        for key, value in sorted(rejection_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:30]
    ]

    return {
        "status": "success",
        "strategy_id": strategy_id,
        "filters": {
            "window": normalized,
            "time_from": start_at.isoformat(),
            "time_to": end_at.isoformat(),
        },
        "summary": {
            "signals_total": len(rows),
            "signals_selected": len(selected_rows),
            "signals_rejected": len(rejected_rows),
            "avg_adjusted_score": avg_adjusted,
            "avg_base_score": avg_base,
        },
        "trend_rows": trend_rows,
        "top_symbols": top_symbols,
        "rejection_reasons": rejection_reasons,
        "recent_rows": _rows_to_export_payload(rows[-150:]),
    }


@router.get("/observability/export")
def strategy_observability_export(
    export_format: Literal["json", "csv"] = Query(default="json"),
    window: str = Query(default="24h"),
    strategy_id: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    top_n: int = Query(default=1000, ge=1, le=5000),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot_timestamp = datetime.now(timezone.utc)
    effective_time_to = time_to or snapshot_timestamp.isoformat()
    normalized, start_at, end_at, rows = _query_strategy_rows(
        db,
        strategy_id=strategy_id,
        window=window,
        time_from=time_from,
        time_to=effective_time_to,
        limit=top_n,
    )
    payload_rows = _rows_to_export_payload(rows)
    filters_payload = {
        "window": normalized,
        "strategy_id": strategy_id,
        "time_from": start_at.isoformat(),
        "time_to": end_at.isoformat(),
        "top_n": top_n,
        "snapshot_timestamp": snapshot_timestamp.isoformat(),
    }

    create_audit_log(
        db,
        action="strategy_observability_export",
        entity_type="strategy_observability",
        entity_id=strategy_id or "all",
        actor_user_id=current_admin.id,
        actor_role=_role_value(current_admin),
        details={
            "export_type": export_format,
            "filters": filters_payload,
            "dataset_size": len(payload_rows),
            "row_count": len(payload_rows),
        },
    )
    db.commit()

    if export_format == "json":
        return {
            "status": "success",
            "export_format": "json",
            "filters": filters_payload,
            "snapshot_timestamp": snapshot_timestamp.isoformat(),
            "count": len(payload_rows),
            "row_count": len(payload_rows),
            "items": payload_rows,
        }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["signal_id", "strategy_id", "symbol", "event_type", "market_regime", "base_score", "adjusted_score", "score_delta", "selection_rank", "rejection_reason", "created_at"])
    for row in payload_rows:
        writer.writerow(
            [
                row.get("signal_id"),
                row.get("strategy_id"),
                row.get("symbol"),
                row.get("event_type"),
                row.get("market_regime"),
                row.get("base_score"),
                row.get("adjusted_score"),
                row.get("score_delta"),
                row.get("selection_rank"),
                row.get("rejection_reason"),
                row.get("created_at"),
            ]
        )

    filename_strategy = strategy_id or "all"
    filename = f"observability_{filename_strategy}_{normalized}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Observability-Filters": json.dumps(filters_payload, ensure_ascii=False),
            "X-Snapshot-Timestamp": snapshot_timestamp.isoformat(),
            "X-Row-Count": str(len(payload_rows)),
        },
    )


@router.get("/action-impact-timeline")
def strategy_action_impact_timeline(
    window: str = Query(default="24h"),
    strategy_id: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=2000),
    include_seed: bool = Query(default=False),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at = _resolve_time_range(window, time_from, time_to)
    window_duration = end_at - start_at
    prev_start = start_at - window_duration
    prev_end = start_at

    audit_rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.created_at >= start_at,
            AuditLog.created_at <= end_at,
            AuditLog.action.like("strategy_%"),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    system_alert_rows = (
        db.query(SystemAlert)
        .filter(
            SystemAlert.last_triggered_at >= start_at,
            SystemAlert.last_triggered_at <= end_at,
        )
        .order_by(SystemAlert.last_triggered_at.desc())
        .limit(limit)
        .all()
    )

    signal_ids: set[str] = set()
    for row in audit_rows:
        details = row.details or {}
        for signal_id in details.get("signal_ids") or []:
            value = str(signal_id or "").strip()
            if value:
                signal_ids.add(value)

    signal_strategy_map: dict[str, str] = {}
    if signal_ids:
        signal_rows = db.query(StrategyObservabilityEvent).filter(StrategyObservabilityEvent.id.in_(list(signal_ids))).all()
        signal_strategy_map = {str(item.id): str(item.strategy_id) for item in signal_rows if item.id and item.strategy_id}

    timeline_rows = _serialize_action_timeline_items(
        audit_rows=audit_rows,
        system_alert_rows=system_alert_rows,
        strategy_filter=strategy_id,
        signal_strategy_map=signal_strategy_map,
    )

    seed_rows = [item for item in timeline_rows if bool(item.get("is_seed_chain"))]
    if not include_seed:
        timeline_rows = [item for item in timeline_rows if not bool(item.get("is_seed_chain"))]

    timeline_rows = timeline_rows[:limit]
    manual_count = sum(1 for item in timeline_rows if item.get("event_type") == "manual_action")
    system_count = sum(1 for item in timeline_rows if item.get("event_type") == "system_reaction")

    def _event_kpis(range_start: datetime, range_end: datetime) -> dict:
        base_query = db.query(StrategyObservabilityEvent).filter(
            StrategyObservabilityEvent.created_at >= range_start,
            StrategyObservabilityEvent.created_at <= range_end,
        )
        if strategy_id:
            base_query = base_query.filter(StrategyObservabilityEvent.strategy_id == strategy_id)
        selected = base_query.filter(StrategyObservabilityEvent.event_type == "selected_for_execution").count()
        rejected = base_query.filter(StrategyObservabilityEvent.event_type != "selected_for_execution").count()
        return {
            "selected_signals": int(selected),
            "rejected_signals": int(rejected),
        }

    def _risk_breach_count(range_start: datetime, range_end: datetime) -> int:
        rows = (
            db.query(SystemAlert)
            .filter(
                SystemAlert.created_at >= range_start,
                SystemAlert.created_at <= range_end,
                or_(
                    SystemAlert.alert_type.ilike("%breach%"),
                    SystemAlert.root_cause_code.ilike("%breach%"),
                ),
            )
            .all()
        )
        if not strategy_id:
            return len(rows)
        matched = []
        for row in rows:
            details_blob = json.dumps(row.details or {}, ensure_ascii=False)
            if strategy_id in str(row.entity_key or "") or strategy_id in details_blob:
                matched.append(row)
        return len(matched)

    after_kpis = _event_kpis(start_at, end_at)
    before_kpis = _event_kpis(prev_start, prev_end)
    after_kpis["risk_breaches"] = _risk_breach_count(start_at, end_at)
    before_kpis["risk_breaches"] = _risk_breach_count(prev_start, prev_end)

    kpi_cards = {}
    for key in ["selected_signals", "rejected_signals", "risk_breaches"]:
        before_value = int(before_kpis.get(key, 0))
        after_value = int(after_kpis.get(key, 0))
        kpi_cards[key] = {
            "before": before_value,
            "after": after_value,
            "delta": after_value - before_value,
        }

    return {
        "status": "success",
        "filters": {
            "window": normalized,
            "strategy_id": strategy_id,
            "time_from": start_at.isoformat(),
            "time_to": end_at.isoformat(),
            "limit": limit,
            "include_seed": include_seed,
        },
        "summary": {
            "total": len(timeline_rows),
            "manual_action_count": manual_count,
            "system_reaction_count": system_count,
            "seed_rows_total": len(seed_rows),
            "seed_rows_filtered": 0 if include_seed else len(seed_rows),
        },
        "kpi_cards": kpi_cards,
        "items": timeline_rows,
    }


@router.get("/timeline/{chain_id}")
def strategy_timeline_chain_detail(
    chain_id: str,
    window: str = Query(default="30d"),
    strategy_id: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    include_seed: bool = Query(default=False),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized, start_at, end_at = _resolve_time_range(window, time_from, time_to)

    audit_rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.created_at >= start_at,
            AuditLog.created_at <= end_at,
            AuditLog.action.like("strategy_%"),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(2000)
        .all()
    )
    system_alert_rows = (
        db.query(SystemAlert)
        .filter(
            SystemAlert.created_at >= start_at,
            SystemAlert.created_at <= end_at,
        )
        .order_by(SystemAlert.created_at.desc())
        .limit(2000)
        .all()
    )

    signal_strategy_map: dict[str, str] = {}
    timeline_rows = _serialize_action_timeline_items(
        audit_rows=audit_rows,
        system_alert_rows=system_alert_rows,
        strategy_filter=strategy_id,
        signal_strategy_map=signal_strategy_map,
    )

    chain_nodes = [item for item in timeline_rows if str(item.get("chain_id") or "") == chain_id]
    seed_chain_nodes = [item for item in chain_nodes if bool(item.get("is_seed_chain"))]
    if seed_chain_nodes and not include_seed:
        hidden_hint = _build_root_cause_hint({"seed_chain_hidden"}, 0, 0)
        return {
            "status": "success",
            "chain_id": chain_id,
            "filters": {
                "window": normalized,
                "strategy_id": strategy_id,
                "time_from": start_at.isoformat(),
                "time_to": end_at.isoformat(),
                "include_seed": include_seed,
            },
            "count": 0,
            "summary": {
                "total_nodes": 0,
                "manual_action_count": 0,
                "system_reaction_count": 0,
                "broken_links_count": 0,
                "root_nodes_count": 0,
                "is_chain_valid": False,
                "invalid_reasons": ["seed_chain_hidden"],
                "root_cause_hint": hidden_hint,
                "max_depth": 0,
                "default_view": "summary",
                "lazy_load_recommended": False,
                "virtualization_recommended": False,
                "seed_nodes_filtered": len(seed_chain_nodes),
            },
            "nodes": [],
            "meta": {
                "seed_chain": True,
                "seed_chain_hidden": True,
                "seed_nodes_total": len(seed_chain_nodes),
            },
        }

    filtered_chain_nodes = chain_nodes if include_seed else [item for item in chain_nodes if not bool(item.get("is_seed_chain"))]
    enriched_nodes, chain_summary = _enrich_chain_nodes(filtered_chain_nodes)

    return {
        "status": "success",
        "chain_id": chain_id,
        "filters": {
            "window": normalized,
            "strategy_id": strategy_id,
            "time_from": start_at.isoformat(),
            "time_to": end_at.isoformat(),
            "include_seed": include_seed,
        },
        "count": len(enriched_nodes),
        "summary": chain_summary,
        "nodes": enriched_nodes,
        "meta": {
            "seed_chain": bool(seed_chain_nodes),
            "seed_nodes_total": len(seed_chain_nodes),
            "seed_nodes_filtered": 0 if include_seed else len(seed_chain_nodes),
        },
    }


@router.get("/score-metrics")
def score_metrics(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_score_metrics(db, window=window)


@router.get("/report")
def strategy_observability_report(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_strategy_observability_report(db, window=window)


@router.get("/audit-log")
def strategy_audit_log(
    limit: int = Query(default=100, ge=1, le=300),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.like("strategy_%"))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "items": [
            {
                "audit_id": row.id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "reason": (row.details or {}).get("reason"),
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "details": row.details or {},
            }
            for row in rows
        ],
    }


@router.get("/observability-report")
def strategy_observability_report_alias(
    window: str = Query(default="24h"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_strategy_observability_report(db, window=window)
