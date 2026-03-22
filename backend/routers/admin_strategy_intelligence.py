from datetime import datetime, timezone
from datetime import timedelta
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from core.policy.quote_policy import InvalidSymbol, normalize_symbol
from db import get_db
from deps import require_admin
from models import DecisionApprovalRequest, SimulationRun, SimulationScenarioItem, User, UserRole
from schemas import (
    AdminStrategyIntelligenceResponse,
    DecisionApprovalActionRequest,
    DecisionApprovalRequestResponse,
    DecisionRequestCreateRequest,
    DecisionRequestExecuteRequest,
    DecisionRequestPreviewResponse,
    DecisionApprovalRequestsResponse,
    HedgeSuggestionResponse,
    ManualOverrideSubmissionResponse,
    ManualOverrideRequest,
    ManualOverrideRevokeRequest,
    ManualOverrideRevokeResponse,
    ManualOverrideResponse,
    RebalanceGovernanceSummaryResponse,
    RiskBatchSimulationRequest,
    RiskBatchSimulationResponse,
    RiskBatchSimulationItem,
    RiskSimulationRequest,
    RiskSimulationPresetItem,
    RiskSimulationPresetsResponse,
    RiskSimulationResponse,
    SimulationCompareCurrentResponse,
    SimulationHistoryItemResponse,
    SimulationHistoryResponse,
    StrategyConflictResponse,
    CapitalRebalanceEventResponse,
)
from services.portfolio_risk_service import portfolio_risk_check
from services.strategy_intelligence_service import (
    build_strategy_intelligence_snapshot,
    evaluate_capital_rebalance,
    evaluate_conflict_warning,
    evaluate_hedge_suggestion,
    list_active_manual_overrides,
    list_manual_overrides,
    normalize_manual_override_row,
    record_manual_override,
    revoke_manual_override,
    simulate_risk_impact,
)

router = APIRouter(prefix="/admin", tags=["admin_strategy_intelligence"])
_SIMULATION_REGISTRY: dict[str, dict] = {}

SIMULATION_PRESET_DEFINITIONS = {
    "high_volatility": {
        "label": "High Volatility",
        "description": "Volatiliteyi artırır, notional ve güven skorunu daha konservatif hale getirir.",
        "defaults": {
            "volatility_pct": 9.0,
            "notional_scale": 0.75,
            "signal_confidence": 0.58,
            "position_size_scale": 0.8,
        },
    },
    "liquidity_shock": {
        "label": "Liquidity Shock",
        "description": "Likidite baskısını artırır, boyutu küçültür, risk tamponunu yükseltir.",
        "defaults": {
            "volatility_pct": 6.5,
            "notional_scale": 0.55,
            "position_size_scale": 0.65,
            "projected_liquidity_impact": 0.8,
        },
    },
    "conflict_heavy": {
        "label": "Conflict Heavy",
        "description": "Çatışma olasılığı yüksek akış için güven skorunu düşürüp volatiliteyi yükseltir.",
        "defaults": {
            "volatility_pct": 7.0,
            "notional_scale": 0.85,
            "signal_confidence": 0.45,
            "position_size_scale": 0.9,
        },
    },
}


def _role_name(user: User) -> str:
    role = user.role
    if isinstance(role, UserRole):
        return str(role.value)
    return str(role)


def _require_override_write_access(user: User) -> None:
    role = _role_name(user)
    if role == "ops":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops role cannot apply/revoke overrides")


def _resolve_expiry(*, expires_at: datetime | None, ttl_minutes: int | None) -> datetime:
    if expires_at is None and ttl_minutes is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Override için expires_at veya ttl_minutes zorunlu")

    if expires_at is not None:
        resolved = expires_at
    else:
        resolved = datetime.now(timezone.utc) + timedelta(minutes=int(ttl_minutes or 0))

    if resolved <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Override expiry gelecekte olmalı")
    return resolved


def _require_simulation(simulation_id: str, db: Session | None = None) -> dict:
    entry = _SIMULATION_REGISTRY.get(simulation_id)
    if not entry and db is not None:
        run = db.query(SimulationRun).filter(SimulationRun.run_id == simulation_id).first()
        if run:
            output_payload = run.output_payload or {}
            entry = {
                "created_at": run.created_at,
                "expires_at": run.created_at + timedelta(hours=24),
                "impact_preview": {
                    "projected_risk_score": output_payload.get("projected_risk_score"),
                    "projected_gate_decision": output_payload.get("projected_gate_decision"),
                    "risk_delta": output_payload.get("risk_delta"),
                    "decision_delta": output_payload.get("decision_delta"),
                    "projected_pnl": output_payload.get("projected_pnl"),
                    "projected_drawdown": output_payload.get("projected_drawdown"),
                    "confidence_adjusted_risk_score": output_payload.get("confidence_adjusted_risk_score"),
                },
                "before_state": output_payload.get("before_state") or {},
                "after_state": output_payload.get("after_state") or {},
            }

    if not entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apply öncesi geçerli simulation zorunlu")

    expires_at = entry.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at <= datetime.now(timezone.utc):
        _SIMULATION_REGISTRY.pop(simulation_id, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Simulation süresi doldu, tekrar çalıştırın")
    return entry


def _ensure_intelligence_tables(db: Session) -> None:
    bind = db.get_bind()
    SimulationRun.__table__.create(bind=bind, checkfirst=True)
    SimulationScenarioItem.__table__.create(bind=bind, checkfirst=True)
    DecisionApprovalRequest.__table__.create(bind=bind, checkfirst=True)


def _summary_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _persist_simulation_run(
    db: Session,
    *,
    simulation: dict,
    current_user: User,
    symbols: list[str],
    request_mode: str,
    status_value: str = "preview",
) -> SimulationRun:
    _ensure_intelligence_tables(db)
    run_id = str(simulation.get("simulation_id") or f"sim_{uuid.uuid4().hex[:12]}")

    row = SimulationRun(
        run_id=run_id,
        actor_id=str(current_user.id),
        actor_role=_role_name(current_user),
        scope="strategy_intelligence",
        status=status_value,
        request_mode=request_mode,
        symbols=symbols,
        summary_hash=_summary_hash(simulation),
        input_payload=simulation.get("simulation_payload") or {},
        output_payload=simulation,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)

    scenario = SimulationScenarioItem(
        run_id=run_id,
        symbol=(symbols[0] if symbols else str((simulation.get("simulation_payload") or {}).get("symbol") or "UNKNOWN")),
        scenario_label="default",
        input_payload=simulation.get("simulation_payload") or {},
        output_payload={
            "projected_risk_score": simulation.get("projected_risk_score"),
            "projected_gate_decision": simulation.get("projected_gate_decision"),
            "risk_delta": simulation.get("risk_delta"),
            "decision_delta": simulation.get("decision_delta"),
            "confidence_adjusted_risk_score": simulation.get("confidence_adjusted_risk_score"),
        },
        risk_delta=float(simulation.get("risk_delta") or 0),
        decision_delta=str(simulation.get("decision_delta") or "UNCHANGED"),
    )
    db.add(scenario)
    db.flush()
    return row


def _serialize_history_row(row: SimulationRun) -> dict:
    return {
        "run_id": row.run_id,
        "actor_id": row.actor_id,
        "actor_role": row.actor_role,
        "scope": row.scope,
        "status": row.status,
        "request_mode": row.request_mode,
        "symbols": row.symbols or [],
        "summary_hash": row.summary_hash,
        "input_payload": row.input_payload or {},
        "output_payload": row.output_payload or {},
        "approval_request_id": row.approval_request_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _coerce_float(value: object, *, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _apply_simulation_preset(*, intent_payload: dict, preset_scenario: str | None, preset_overrides: dict | None) -> dict:
    if not preset_scenario:
        return dict(intent_payload)

    preset = SIMULATION_PRESET_DEFINITIONS.get(str(preset_scenario))
    if not preset:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz preset_scenario")

    merged = {
        **(preset.get("defaults") or {}),
        **(preset_overrides or {}),
    }
    payload = dict(intent_payload)

    base_notional = _coerce_float(payload.get("notional") or payload.get("position_size_value"), default=100)
    base_position = _coerce_float(payload.get("position_size_value") or payload.get("notional"), default=base_notional)

    if merged.get("volatility_pct") is not None:
        payload["volatility_pct"] = _coerce_float(merged.get("volatility_pct"), default=3.0)
    if merged.get("signal_confidence") is not None:
        payload["signal_confidence"] = _coerce_float(merged.get("signal_confidence"), default=0.65)

    notional_scale = _coerce_float(merged.get("notional_scale"), default=1.0)
    position_scale = _coerce_float(merged.get("position_size_scale"), default=1.0)

    payload["notional"] = round(_coerce_float(merged.get("notional"), default=base_notional * max(notional_scale, 0.05)), 8)
    payload["position_size_value"] = round(
        _coerce_float(merged.get("position_size_value"), default=base_position * max(position_scale, 0.05)),
        8,
    )
    payload["preset_scenario"] = str(preset_scenario)
    payload["preset_overrides"] = merged
    return payload


def _decision_sla_snapshot(*, created_at: datetime | None, request_status: str) -> dict:
    if str(request_status) != "pending" or not isinstance(created_at, datetime):
        return {
            "sla_countdown_seconds": None,
            "sla_state": "n/a",
            "escalation_state": "none",
        }

    now = datetime.now(timezone.utc)
    created_utc = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    elapsed_seconds = int(max((now - created_utc).total_seconds(), 0))

    sla_total_seconds = 60 * 60
    warning_threshold = 15 * 60
    remaining = sla_total_seconds - elapsed_seconds

    if remaining <= 0:
        return {
            "sla_countdown_seconds": 0,
            "sla_state": "breach",
            "escalation_state": "escalated_super_admin",
        }
    if remaining <= warning_threshold:
        return {
            "sla_countdown_seconds": remaining,
            "sla_state": "warning",
            "escalation_state": "notify_ops",
        }
    return {
        "sla_countdown_seconds": remaining,
        "sla_state": "healthy",
        "escalation_state": "none",
    }


def _serialize_approval_row(row: DecisionApprovalRequest) -> dict:
    return {
        "request_id": row.request_id,
        "request_type": row.request_type,
        "status": row.status,
        "requested_by": row.requested_by,
        "requested_role": row.requested_role,
        "reason_note": row.reason_note,
        "simulation_run_id": row.simulation_run_id,
        "payload": row.payload or {},
        "expires_at": row.expires_at,
        "created_at": row.created_at,
        "decided_at": row.decided_at,
        "approved_by": row.approved_by,
        "review_note": row.review_note,
    }


def _queue_approval_request(
    db: Session,
    *,
    request_type: str,
    current_user: User,
    reason_note: str,
    simulation_run_id: str,
    payload: dict,
) -> DecisionApprovalRequest:
    _ensure_intelligence_tables(db)
    row = DecisionApprovalRequest(
        request_id=f"req_{uuid.uuid4().hex[:12]}",
        request_type=request_type,
        status="pending",
        requested_by=str(current_user.id),
        requested_role=_role_name(current_user),
        reason_note=reason_note,
        simulation_run_id=simulation_run_id,
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def _resolve_valid_user_id(db: Session, user_id: str) -> str:
    key = str(user_id or "").strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id zorunlu")
    exists = db.query(User).filter(User.id == key).first()
    if not exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz user_id")
    return key


def _severity_band(risk_delta_score: float) -> str:
    score = abs(float(risk_delta_score or 0))
    if score >= 0.6:
        return "critical"
    if score >= 0.35:
        return "high"
    if score >= 0.15:
        return "medium"
    return "low"


def _compute_risk_delta_priority_score(*, simulation_output: dict | None, fallback_risk_delta: float | None = None) -> float:
    output = simulation_output or {}
    risk_delta = abs(float(output.get("risk_delta") if output.get("risk_delta") is not None else (fallback_risk_delta or 0)))
    confidence_adjusted_risk = abs(
        float(output.get("confidence_adjusted_risk_score") or output.get("projected_risk_score") or 0)
    )
    projected_drawdown = abs(float(output.get("projected_drawdown") or 0))
    projected_liquidity = abs(float(output.get("projected_liquidity_impact") or 0))
    decision_delta = str(output.get("decision_delta") or "UNCHANGED")
    decision_shift_bonus = 0.04 if decision_delta != "UNCHANGED" else 0.0

    score = (
        (risk_delta * 0.5)
        + (confidence_adjusted_risk * 0.25)
        + (projected_drawdown * 0.15)
        + (projected_liquidity * 0.1)
        + decision_shift_bonus
    )
    return round(score, 6)


def _build_decision_request_response(row: DecisionApprovalRequest) -> dict:
    base = _serialize_approval_row(row)
    payload = row.payload or {}
    risk_delta_score = float(payload.get("risk_delta_score") or 0)
    sla = _decision_sla_snapshot(created_at=row.created_at, request_status=row.status)
    return {
        **base,
        "target_type": payload.get("target_type"),
        "target_id": payload.get("target_id"),
        "simulation_required": bool(payload.get("simulation_required", True)),
        "simulation_present": bool(payload.get("simulation_run_id")),
        "preview_token": payload.get("preview_token"),
        "risk_delta_score": risk_delta_score,
        "severity_band": payload.get("severity_band") or _severity_band(risk_delta_score),
        "impact_summary": payload.get("impact_summary") or {},
        "sla_countdown_seconds": sla.get("sla_countdown_seconds"),
        "sla_state": str(sla.get("sla_state") or "n/a"),
        "escalation_state": str(sla.get("escalation_state") or "none"),
    }


def _create_decision_request(
    db: Session,
    *,
    request_type: str,
    current_user: User,
    payload: DecisionRequestCreateRequest,
) -> DecisionApprovalRequest:
    role = _role_name(current_user)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="decision request sadece admin oluşturabilir")

    simulation_run_id = payload.simulation_run_id
    if not simulation_run_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="simulation_run_id zorunlu")

    _ensure_intelligence_tables(db)
    run = db.query(SimulationRun).filter(SimulationRun.run_id == simulation_run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="simulation_run_id bulunamadı")

    run_out = run.output_payload or {}
    derived_risk_delta = (
        float(payload.risk_delta_score)
        if payload.risk_delta_score is not None
        else _compute_risk_delta_priority_score(
            simulation_output=run_out,
            fallback_risk_delta=float(run_out.get("risk_delta") or 0),
        )
    )
    impact_summary = payload.impact_summary or {
        "projected_risk_score": float(run_out.get("projected_risk_score") or 0),
        "projected_gate_decision": str(run_out.get("projected_gate_decision") or "ALLOW"),
        "projected_pnl": float(run_out.get("projected_pnl") or 0),
        "projected_drawdown": float(run_out.get("projected_drawdown") or 0),
        "projected_exposure": float(run_out.get("projected_exposure") or 0),
        "projected_var": float(run_out.get("projected_var") or 0),
        "projected_liquidity_impact": float(run_out.get("projected_liquidity_impact") or 0),
        "confidence_adjusted_risk_score": float(run_out.get("confidence_adjusted_risk_score") or 0),
        "risk_delta": float(run_out.get("risk_delta") or 0),
        "decision_delta": str(run_out.get("decision_delta") or "UNCHANGED"),
    }

    preview_token = f"preview_{uuid.uuid4().hex[:14]}"
    request_payload = {
        "target_type": payload.target_type,
        "target_id": payload.target_id,
        "simulation_required": True,
        "simulation_run_id": simulation_run_id,
        "simulation_present": True,
        "preview_token": preview_token,
        "risk_delta_score": derived_risk_delta,
        "severity_band": _severity_band(derived_risk_delta),
        "impact_summary": impact_summary,
    }

    request_row = DecisionApprovalRequest(
        request_id=f"req_{uuid.uuid4().hex[:12]}",
        request_type=request_type,
        status="pending",
        requested_by=str(current_user.id),
        requested_role=role,
        reason_note=payload.reason_note,
        simulation_run_id=simulation_run_id,
        payload=request_payload,
        expires_at=payload.expires_at or (datetime.now(timezone.utc) + timedelta(hours=24)),
        created_at=datetime.now(timezone.utc),
    )
    db.add(request_row)
    db.flush()

    run.approval_request_id = request_row.request_id
    run.updated_at = datetime.now(timezone.utc)
    return request_row


@router.get("/strategy-intelligence", response_model=AdminStrategyIntelligenceResponse)
def strategy_intelligence_dashboard(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).filter(User.role == UserRole.USER).order_by(User.created_at.desc()).limit(20).all()
    conflict_items: list[dict] = []
    rebalance_items: list[dict] = []
    hedge_items: list[dict] = []
    allocation_drift_values: list[float] = []
    perf_delta_values: list[float] = []
    rar_values: list[float] = []
    governance_snapshots: list[dict] = []

    for user in users:
        snapshot = build_strategy_intelligence_snapshot(db, user_id=user.id)
        conflict_items.extend(snapshot.get("strategy_conflicts", []))
        rebalance_items.extend(snapshot.get("capital_rebalance_events", []))
        hedge_items.extend(snapshot.get("hedge_suggestions", []))
        allocation_drift_values.append(float(snapshot.get("allocation_drift") or 0))
        perf_delta_values.append(float(snapshot.get("strategy_performance_delta") or 0))
        rar_values.append(float(snapshot.get("risk_adjusted_return") or 0))
        governance_snapshots.append(snapshot.get("governance_summary") or {})

    allocation_drift = sum(allocation_drift_values) / max(len(allocation_drift_values), 1)
    strategy_performance_delta = sum(perf_delta_values) / max(len(perf_delta_values), 1)
    risk_adjusted_return = sum(rar_values) / max(len(rar_values), 1)
    first_governance = next((item for item in governance_snapshots if item), {})
    governance_summary = RebalanceGovernanceSummaryResponse(
        cadence_window_minutes=int(first_governance.get("cadence_window_minutes") or 30),
        max_weight_shift_per_cycle=float(first_governance.get("max_weight_shift_per_cycle") or 0.12),
        max_capital_shift_pct=float(first_governance.get("max_capital_shift_pct") or 0.2),
        drift_threshold=float(first_governance.get("drift_threshold") or 0.08),
        cadence_blocked_strategies=sum(int(item.get("cadence_blocked_strategies") or 0) for item in governance_snapshots),
        weight_shift_capped_strategies=sum(int(item.get("weight_shift_capped_strategies") or 0) for item in governance_snapshots),
        capital_shift_capped_strategies=sum(int(item.get("capital_shift_capped_strategies") or 0) for item in governance_snapshots),
    )

    return AdminStrategyIntelligenceResponse(
        generated_at=datetime.now(timezone.utc),
        strategy_conflicts=[StrategyConflictResponse(**item) for item in conflict_items[:100]],
        capital_rebalance_events=[CapitalRebalanceEventResponse(**item) for item in rebalance_items[:100]],
        hedge_suggestions=[HedgeSuggestionResponse(**item) for item in hedge_items[:50]],
        governance_summary=governance_summary,
        allocation_drift=round(allocation_drift, 6),
        strategy_performance_delta=round(strategy_performance_delta, 6),
        risk_adjusted_return=round(risk_adjusted_return, 6),
    )


@router.post("/manual-overrides", response_model=ManualOverrideSubmissionResponse)
def create_manual_override(
    payload: ManualOverrideRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_override_write_access(current_user)
    if len((payload.reason or "").strip()) < 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason minimum 12 karakter olmalı")

    simulation_entry = _require_simulation(payload.simulation_id, db=db)
    resolved_expiry = _resolve_expiry(expires_at=payload.expires_at, ttl_minutes=payload.ttl_minutes)
    role = _role_name(current_user)

    _ensure_intelligence_tables(db)

    simulation_run = db.query(SimulationRun).filter(SimulationRun.run_id == payload.simulation_id).first()
    if simulation_run:
        simulation_run.updated_at = datetime.now(timezone.utc)

    if role == "admin":
        request_row = _queue_approval_request(
            db,
            request_type="manual_override_apply",
            current_user=current_user,
            reason_note=payload.reason,
            simulation_run_id=payload.simulation_id,
            payload={
                "override_payload": payload.model_dump(),
                "resolved_expiry": resolved_expiry.isoformat(),
            },
        )
        if simulation_run:
            simulation_run.status = "pending_approval"
            simulation_run.approval_request_id = request_row.request_id
        db.commit()
        return ManualOverrideSubmissionResponse(
            status="pending_approval",
            message=f"Override isteği onaya gönderildi: {request_row.request_id}",
            request_id=request_row.request_id,
            override=None,
        )

    row = record_manual_override(
        db,
        admin_id=current_user.id,
        action_type=payload.action_type,
        reason=payload.reason,
        scope=payload.scope,
        target_type=payload.target_type,
        target_id=payload.target_id,
        simulation_id=payload.simulation_id,
        confirmation_id=payload.confirmation_id,
        previous_state=payload.previous_state,
        next_state=payload.next_state,
        impact_preview=payload.impact_preview or simulation_entry.get("impact_preview") or {},
        expires_at=resolved_expiry,
        actor_role=role,
        payload=payload.payload,
    )
    if simulation_run:
        simulation_run.status = "applied"
        simulation_run.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return ManualOverrideSubmissionResponse(
        status="applied",
        message="Override başarıyla uygulandı",
        request_id=None,
        override=ManualOverrideResponse(**normalize_manual_override_row(row)),
    )


@router.get("/manual-overrides", response_model=list[ManualOverrideResponse])
def get_manual_overrides(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = list_manual_overrides(db, limit=200)
    normalized = [normalize_manual_override_row(row) for row in rows]
    filtered = [row for row in normalized if row.get("scope") == "strategy_intelligence"]
    return [ManualOverrideResponse(**row) for row in filtered]


@router.get("/active-overrides", response_model=list[ManualOverrideResponse])
def get_active_overrides(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = list_active_manual_overrides(db, limit=200)
    return [ManualOverrideResponse(**row) for row in rows]


@router.post("/manual-overrides/{override_id}/revoke", response_model=ManualOverrideRevokeResponse)
def revoke_override(
    override_id: str,
    payload: ManualOverrideRevokeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_override_write_access(current_user)
    if len((payload.reason or "").strip()) < 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason minimum 12 karakter olmalı")
    try:
        result = revoke_manual_override(
            db,
            override_id=override_id,
            revoked_by=str(current_user.id),
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    return ManualOverrideRevokeResponse(**result)


@router.get("/override-approval-requests", response_model=DecisionApprovalRequestsResponse)
def list_override_approval_requests(
    status_filter: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    _ensure_intelligence_tables(db)
    query = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_type == "manual_override_apply")
    if status_filter:
        query = query.filter(DecisionApprovalRequest.status == status_filter)
    rows = query.order_by(desc(DecisionApprovalRequest.created_at)).limit(200).all()
    return DecisionApprovalRequestsResponse(items=[_serialize_approval_row(row) for row in rows])


@router.post("/decision-requests/conflict-resolve", response_model=DecisionApprovalRequestResponse)
def create_conflict_decision_request(
    payload: DecisionRequestCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_intelligence_tables(db)
    row = _create_decision_request(
        db,
        request_type="conflict_resolve",
        current_user=current_user,
        payload=payload,
    )
    db.commit()
    return DecisionApprovalRequestResponse(**_build_decision_request_response(row))


@router.post("/decision-requests/hedge-apply", response_model=DecisionApprovalRequestResponse)
def create_hedge_decision_request(
    payload: DecisionRequestCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_intelligence_tables(db)
    row = _create_decision_request(
        db,
        request_type="hedge_apply",
        current_user=current_user,
        payload=payload,
    )
    db.commit()
    return DecisionApprovalRequestResponse(**_build_decision_request_response(row))


@router.post("/decision-requests/rebalance-change", response_model=DecisionApprovalRequestResponse)
def create_rebalance_decision_request(
    payload: DecisionRequestCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ensure_intelligence_tables(db)
    row = _create_decision_request(
        db,
        request_type="rebalance_change",
        current_user=current_user,
        payload=payload,
    )
    db.commit()
    return DecisionApprovalRequestResponse(**_build_decision_request_response(row))


@router.get("/decision-requests", response_model=DecisionApprovalRequestsResponse)
def list_decision_requests(
    status_filter: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    _ensure_intelligence_tables(db)
    query = db.query(DecisionApprovalRequest).filter(
        DecisionApprovalRequest.request_type.in_(["conflict_resolve", "hedge_apply", "rebalance_change"])
    )
    if status_filter:
        query = query.filter(DecisionApprovalRequest.status == status_filter)
    rows = query.order_by(desc(DecisionApprovalRequest.created_at)).limit(300).all()
    mapped = [_build_decision_request_response(row) for row in rows]

    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    status_rank = {
        "pending": 0,
        "approved": 1,
        "rejected": 2,
        "executed": 3,
        "revoked": 4,
        "expired": 5,
    }
    sla_rank = {
        "breach": 0,
        "warning": 1,
        "healthy": 2,
        "n/a": 9,
    }

    def _decision_sort_key(item: dict) -> tuple:
        created_at = item.get("created_at")
        created_ts = created_at.timestamp() if isinstance(created_at, datetime) else float("inf")
        item_status = str(item.get("status") or "")
        item_sla = str(item.get("sla_state") or "n/a")
        return (
            status_rank.get(item_status, 99),
            sla_rank.get(item_sla, 9) if item_status == "pending" else 9,
            -severity_rank.get(str(item.get("severity_band") or "low"), 0),
            -abs(float(item.get("risk_delta_score") or 0)),
            created_ts,
        )

    mapped.sort(
        key=_decision_sort_key
    )
    return DecisionApprovalRequestsResponse(items=[DecisionApprovalRequestResponse(**item) for item in mapped])


@router.post("/decision-requests/{request_id}/approve", response_model=DecisionApprovalRequestResponse)
def approve_decision_request(
    request_id: str,
    payload: DecisionApprovalActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approve sadece super_admin")
    _ensure_intelligence_tables(db)
    row = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_id == request_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request bulunamadı")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request pending değil")
    if row.expires_at <= datetime.now(timezone.utc):
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request expired")

    row.status = "approved"
    row.approved_by = str(current_user.id)
    row.review_note = payload.reason_note
    row.decided_at = datetime.now(timezone.utc)
    db.commit()
    return DecisionApprovalRequestResponse(**_build_decision_request_response(row))


@router.post("/decision-requests/{request_id}/reject", response_model=DecisionApprovalRequestResponse)
def reject_decision_request(
    request_id: str,
    payload: DecisionApprovalActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="reject sadece super_admin")
    _ensure_intelligence_tables(db)
    row = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_id == request_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request bulunamadı")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request pending değil")

    row.status = "rejected"
    row.approved_by = str(current_user.id)
    row.review_note = payload.reason_note
    row.decided_at = datetime.now(timezone.utc)
    db.commit()
    return DecisionApprovalRequestResponse(**_build_decision_request_response(row))


@router.post("/decision-requests/{request_id}/execute", response_model=DecisionApprovalRequestResponse)
def execute_decision_request(
    request_id: str,
    payload: DecisionRequestExecuteRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="execute sadece super_admin")
    _ensure_intelligence_tables(db)
    row = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_id == request_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request bulunamadı")
    if row.status != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="execute için request approved olmalı")
    if row.expires_at <= datetime.now(timezone.utc):
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request expired")

    request_payload = row.payload or {}
    expected_token = str(request_payload.get("preview_token") or "")
    if not expected_token or payload.preview_token != expected_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="preview_token doğrulaması başarısız")

    row.status = "executed"
    row.approved_by = str(current_user.id)
    row.review_note = payload.reason_note
    row.decided_at = datetime.now(timezone.utc)

    record_manual_override(
        db,
        admin_id=current_user.id,
        action_type=f"decision_request_execute::{row.request_type}",
        reason=row.reason_note,
        scope="strategy_intelligence",
        target_type=request_payload.get("target_type") or "unknown",
        target_id=request_payload.get("target_id"),
        simulation_id=row.simulation_run_id,
        confirmation_id=payload.preview_token,
        previous_state={},
        next_state={},
        impact_preview=request_payload.get("impact_summary") or {},
        expires_at=row.expires_at,
        actor_role=_role_name(current_user),
        payload={"source": "decision_request_execute", "request_id": row.request_id},
    )

    db.commit()
    return DecisionApprovalRequestResponse(**_build_decision_request_response(row))


@router.post("/decision-requests/{request_id}/revoke", response_model=DecisionApprovalRequestResponse)
def revoke_decision_request(
    request_id: str,
    payload: DecisionApprovalActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="revoke sadece super_admin")
    _ensure_intelligence_tables(db)
    row = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_id == request_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request bulunamadı")
    if row.status not in {"pending", "approved"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sadece pending/approved request revoke edilebilir")

    row.status = "revoked"
    row.approved_by = str(current_user.id)
    row.review_note = payload.reason_note
    row.decided_at = datetime.now(timezone.utc)
    db.commit()
    return DecisionApprovalRequestResponse(**_build_decision_request_response(row))


@router.get("/decision-requests/{request_id}/preview", response_model=DecisionRequestPreviewResponse)
def preview_decision_request(
    request_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    role = _role_name(current_user)
    if role not in {"ops", "admin", "super_admin", "viewer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="preview yetkisi yok")

    _ensure_intelligence_tables(db)
    row = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_id == request_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request bulunamadı")

    payload = row.payload or {}
    risk_delta_score = float(payload.get("risk_delta_score") or 0)
    return DecisionRequestPreviewResponse(
        request_id=row.request_id,
        status=row.status,
        preview_token=str(payload.get("preview_token") or ""),
        risk_delta_score=risk_delta_score,
        severity_band=payload.get("severity_band") or _severity_band(risk_delta_score),
        impact_summary=payload.get("impact_summary") or {},
    )


@router.get("/simulation-runs/{run_id}/compare-current", response_model=SimulationCompareCurrentResponse)
def compare_simulation_run_current(
    run_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    _ensure_intelligence_tables(db)
    run = db.query(SimulationRun).filter(SimulationRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="simulation run bulunamadı")

    input_payload = run.input_payload or {}
    symbol = normalize_symbol(str(input_payload.get("symbol") or "BTCUSDT"), missing_error_code="symbol_required", invalid_error_code="invalid_quote_asset")
    strategy_id = str(input_payload.get("strategy_binding") or input_payload.get("strategy_id") or "manual_execution")
    side = str(input_payload.get("side") or "buy")
    notional = float(input_payload.get("notional") or input_payload.get("position_size_value") or 0)
    user_id = str(input_payload.get("user_id") or run.actor_id or "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="simulation run user context eksik")

    conflict_result = evaluate_conflict_warning(
        db,
        user_id=user_id,
        strategy_id=strategy_id,
        symbol=symbol,
        signal_direction=side,
        confidence_score=float(input_payload.get("signal_confidence") or 0.65),
    )
    rebalance_result = evaluate_capital_rebalance(db, user_id=user_id, apply_changes=False)
    hedge_result = evaluate_hedge_suggestion(db, user_id=user_id, volatility=float(input_payload.get("volatility_pct") or 0))
    risk_result = portfolio_risk_check(
        db,
        user_id=user_id,
        execution_intent={"symbol": symbol, "notional": notional, "position_size": float(input_payload.get("size") or 0)},
        strategy_context={"strategy_id": strategy_id},
        market_state={"volatility_pct": float(input_payload.get("volatility_pct") or 0)},
    )
    current_output = simulate_risk_impact(
        simulation_payload=input_payload,
        conflict_result=conflict_result,
        rebalance_result=rebalance_result,
        hedge_result=hedge_result,
        risk_payload=risk_result,
    )

    before_output = run.output_payload or {}
    compare_summary = {
        "risk_delta_vs_history": round(float(current_output.get("projected_risk_score") or 0) - float(before_output.get("projected_risk_score") or 0), 6),
        "confidence_adjusted_risk_delta_vs_history": round(
            float(current_output.get("confidence_adjusted_risk_score") or 0)
            - float(before_output.get("confidence_adjusted_risk_score") or 0),
            6,
        ),
        "decision_delta_vs_history": f"{before_output.get('projected_gate_decision')}->{current_output.get('projected_gate_decision')}",
    }

    return SimulationCompareCurrentResponse(
        run_id=run.run_id,
        status=run.status,
        before=before_output,
        current=current_output,
        compare_summary=compare_summary,
    )


@router.post("/override-approval-requests/{request_id}/approve", response_model=ManualOverrideSubmissionResponse)
def approve_override_request(
    request_id: str,
    payload: DecisionApprovalActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approve sadece super_admin")

    _ensure_intelligence_tables(db)
    row = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_id == request_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval request bulunamadı")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request pending değil")
    if row.expires_at <= datetime.now(timezone.utc):
        row.status = "expired"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approval request expired")

    request_payload = row.payload or {}
    override_payload = request_payload.get("override_payload") or {}
    resolved_expiry_raw = request_payload.get("resolved_expiry")
    resolved_expiry = datetime.fromisoformat(str(resolved_expiry_raw).replace("Z", "+00:00")) if resolved_expiry_raw else datetime.now(timezone.utc) + timedelta(minutes=60)

    simulation_entry = _require_simulation(str(override_payload.get("simulation_id") or ""), db=db)
    applied_row = record_manual_override(
        db,
        admin_id=current_user.id,
        action_type=str(override_payload.get("action_type") or "manual_override"),
        reason=str(override_payload.get("reason") or row.reason_note),
        scope=str(override_payload.get("scope") or "strategy_intelligence"),
        target_type=str(override_payload.get("target_type") or "user"),
        target_id=override_payload.get("target_id"),
        simulation_id=str(override_payload.get("simulation_id") or row.simulation_run_id),
        confirmation_id=override_payload.get("confirmation_id"),
        previous_state=override_payload.get("previous_state") or simulation_entry.get("before_state") or {},
        next_state=override_payload.get("next_state") or simulation_entry.get("after_state") or {},
        impact_preview=override_payload.get("impact_preview") or simulation_entry.get("impact_preview") or {},
        expires_at=resolved_expiry,
        actor_role=_role_name(current_user),
        payload=override_payload.get("payload") or {},
    )

    row.status = "approved"
    row.approved_by = str(current_user.id)
    row.review_note = payload.reason_note
    row.decided_at = datetime.now(timezone.utc)

    run = db.query(SimulationRun).filter(SimulationRun.run_id == row.simulation_run_id).first()
    if run:
        run.status = "applied"
        run.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(applied_row)
    return ManualOverrideSubmissionResponse(
        status="approved_applied",
        message="Override request onaylandı ve uygulandı",
        request_id=row.request_id,
        override=ManualOverrideResponse(**normalize_manual_override_row(applied_row)),
    )


@router.post("/override-approval-requests/{request_id}/reject", response_model=ManualOverrideSubmissionResponse)
def reject_override_request(
    request_id: str,
    payload: DecisionApprovalActionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if _role_name(current_user) != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="reject sadece super_admin")

    _ensure_intelligence_tables(db)
    row = db.query(DecisionApprovalRequest).filter(DecisionApprovalRequest.request_id == request_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval request bulunamadı")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request pending değil")

    row.status = "rejected"
    row.approved_by = str(current_user.id)
    row.review_note = payload.reason_note
    row.decided_at = datetime.now(timezone.utc)

    run = db.query(SimulationRun).filter(SimulationRun.run_id == row.simulation_run_id).first()
    if run:
        run.status = "superseded"
        run.updated_at = datetime.now(timezone.utc)

    db.commit()
    return ManualOverrideSubmissionResponse(
        status="rejected",
        message="Override request reddedildi",
        request_id=row.request_id,
        override=None,
    )


@router.get("/risk-simulation/presets", response_model=RiskSimulationPresetsResponse)
def list_risk_simulation_presets(
    current_user: User = Depends(require_admin),
):
    _ = current_user
    items = [
        RiskSimulationPresetItem(
            preset_key=key,
            label=str(config.get("label") or key),
            description=str(config.get("description") or ""),
            defaults=config.get("defaults") or {},
        )
        for key, config in SIMULATION_PRESET_DEFINITIONS.items()
    ]
    return RiskSimulationPresetsResponse(items=items)


@router.post("/risk-simulation", response_model=RiskSimulationResponse)
def risk_simulation(
    payload: RiskSimulationRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_valid_user_id(db, payload.user_id)
    intent_payload = _apply_simulation_preset(
        intent_payload={
            **(payload.intent_payload or {}),
            "user_id": resolved_user_id,
        },
        preset_scenario=payload.preset_scenario,
        preset_overrides=payload.preset_overrides,
    )
    try:
        symbol = normalize_symbol(
            intent_payload.get("symbol"),
            missing_error_code="symbol_required",
            invalid_error_code="invalid_quote_asset",
        )
    except InvalidSymbol as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    side = str(intent_payload.get("side") or "buy")
    strategy_id = str(intent_payload.get("strategy_binding") or intent_payload.get("strategy_id") or "manual_execution")
    notional = float(intent_payload.get("notional") or intent_payload.get("position_size_value") or 0)

    conflict_result = evaluate_conflict_warning(
        db,
        user_id=resolved_user_id,
        strategy_id=strategy_id,
        symbol=symbol,
        signal_direction=side,
        confidence_score=float(intent_payload.get("signal_confidence") or 0.65),
    )
    rebalance_result = evaluate_capital_rebalance(db, user_id=resolved_user_id, apply_changes=False)
    hedge_result = evaluate_hedge_suggestion(
        db,
        user_id=resolved_user_id,
        volatility=float(intent_payload.get("volatility_pct") or 0),
    )
    risk_result = portfolio_risk_check(
        db,
        user_id=resolved_user_id,
        execution_intent={"symbol": symbol, "notional": notional, "position_size": float(intent_payload.get("size") or 0)},
        strategy_context={"strategy_id": strategy_id},
        market_state={"volatility_pct": float(intent_payload.get("volatility_pct") or 0)},
    )

    simulation = simulate_risk_impact(
        simulation_payload=intent_payload,
        conflict_result=conflict_result,
        rebalance_result=rebalance_result,
        hedge_result=hedge_result,
        risk_payload=risk_result,
    )

    simulation_id = str(simulation.get("simulation_id") or "")
    impact_preview = {
        "projected_risk_score": float(simulation.get("projected_risk_score") or 0),
        "projected_gate_decision": str(simulation.get("projected_gate_decision") or "ALLOW"),
        "projected_pnl": float(simulation.get("projected_pnl") or 0),
        "projected_drawdown": float(simulation.get("projected_drawdown") or 0),
        "projected_exposure": float(simulation.get("projected_exposure") or 0),
        "projected_var": float(simulation.get("projected_var") or 0),
        "projected_liquidity_impact": float(simulation.get("projected_liquidity_impact") or 0),
        "confidence_adjusted_risk_score": float(simulation.get("confidence_adjusted_risk_score") or 0),
        "risk_delta": float(simulation.get("risk_delta") or 0),
        "decision_delta": str(simulation.get("decision_delta") or "UNCHANGED"),
    }

    if simulation_id:
        _SIMULATION_REGISTRY[simulation_id] = {
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=20),
            "impact_preview": impact_preview,
            "before_state": simulation.get("before_state") or {},
            "after_state": simulation.get("after_state") or {},
        }

    _persist_simulation_run(
        db,
        simulation=simulation,
        current_user=current_user,
        symbols=[symbol],
        request_mode="single",
        status_value="preview",
    )
    db.commit()

    if payload.apply_override:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="apply_override bu endpointte kapalı. Override için /admin/manual-overrides kullanın.",
        )

    return RiskSimulationResponse(
        simulated_at=datetime.now(timezone.utc),
        simulation_id=simulation_id,
        dry_run=True,
        simulation_payload=simulation.get("simulation_payload", {}),
        strategy_conflict=simulation.get("strategy_conflict", {}),
        allocation_adjustment=simulation.get("allocation_adjustment", {}),
        hedge_suggestion=simulation.get("hedge_suggestion", {}),
        projected_risk_score=float(simulation.get("projected_risk_score") or 0),
        projected_gate_decision=str(simulation.get("projected_gate_decision") or "ALLOW"),
        projected_pnl=float(simulation.get("projected_pnl") or 0),
        projected_drawdown=float(simulation.get("projected_drawdown") or 0),
        projected_exposure=float(simulation.get("projected_exposure") or 0),
        projected_var=float(simulation.get("projected_var") or 0),
        projected_liquidity_impact=float(simulation.get("projected_liquidity_impact") or 0),
        confidence_adjusted_risk_score=float(simulation.get("confidence_adjusted_risk_score") or 0),
        before_state=simulation.get("before_state") or {},
        after_state=simulation.get("after_state") or {},
        decision_summary=simulation.get("decision_summary") or {},
        risk_delta=float(simulation.get("risk_delta") or 0),
        decision_delta=str(simulation.get("decision_delta") or "UNCHANGED"),
    )


@router.post("/risk-simulation/batch", response_model=RiskBatchSimulationResponse)
def risk_simulation_batch(
    payload: RiskBatchSimulationRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_valid_user_id(db, payload.user_id)
    symbols = [str(item or "").upper().strip() for item in (payload.symbols or []) if str(item or "").strip()]
    if not symbols:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch simulation için en az 1 symbol gerekli")

    items = []
    for symbol in symbols:
        try:
            valid_symbol = normalize_symbol(symbol, missing_error_code="symbol_required", invalid_error_code="invalid_quote_asset")
        except InvalidSymbol:
            continue

        intent_payload = _apply_simulation_preset(
            intent_payload={
                **(payload.intent_payload or {}),
                "symbol": valid_symbol,
                "user_id": resolved_user_id,
            },
            preset_scenario=payload.preset_scenario,
            preset_overrides=payload.preset_overrides,
        )
        side = str(intent_payload.get("side") or "buy")
        strategy_id = str(intent_payload.get("strategy_binding") or intent_payload.get("strategy_id") or "manual_execution")
        notional = float(intent_payload.get("notional") or intent_payload.get("position_size_value") or 0)

        conflict_result = evaluate_conflict_warning(
            db,
            user_id=resolved_user_id,
            strategy_id=strategy_id,
            symbol=valid_symbol,
            signal_direction=side,
            confidence_score=float(intent_payload.get("signal_confidence") or 0.65),
        )
        rebalance_result = evaluate_capital_rebalance(db, user_id=resolved_user_id, apply_changes=False)
        hedge_result = evaluate_hedge_suggestion(db, user_id=resolved_user_id, volatility=float(intent_payload.get("volatility_pct") or 0))
        risk_result = portfolio_risk_check(
            db,
            user_id=resolved_user_id,
            execution_intent={"symbol": valid_symbol, "notional": notional, "position_size": float(intent_payload.get("size") or 0)},
            strategy_context={"strategy_id": strategy_id},
            market_state={"volatility_pct": float(intent_payload.get("volatility_pct") or 0)},
        )
        simulation = simulate_risk_impact(
            simulation_payload=intent_payload,
            conflict_result=conflict_result,
            rebalance_result=rebalance_result,
            hedge_result=hedge_result,
            risk_payload=risk_result,
        )

        _persist_simulation_run(
            db,
            simulation=simulation,
            current_user=current_user,
            symbols=[valid_symbol],
            request_mode="batch",
            status_value="preview",
        )

        items.append(
            RiskBatchSimulationItem(
                simulation_id=str(simulation.get("simulation_id")),
                symbol=valid_symbol,
                projected_risk_score=float(simulation.get("projected_risk_score") or 0),
                projected_gate_decision=str(simulation.get("projected_gate_decision") or "ALLOW"),
                risk_delta=float(simulation.get("risk_delta") or 0),
                decision_delta=str(simulation.get("decision_delta") or "UNCHANGED"),
                confidence_adjusted_risk_score=float(simulation.get("confidence_adjusted_risk_score") or 0),
            )
        )

    db.commit()

    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçerli symbol bulunamadı")

    avg_risk = sum(item.projected_risk_score for item in items) / max(len(items), 1)
    avg_adj_risk = sum(item.confidence_adjusted_risk_score for item in items) / max(len(items), 1)
    return RiskBatchSimulationResponse(
        batch_id=f"batch_{uuid.uuid4().hex[:12]}",
        simulated_at=datetime.now(timezone.utc),
        total_symbols=len(items),
        summary={
            "avg_projected_risk_score": round(avg_risk, 6),
            "avg_confidence_adjusted_risk_score": round(avg_adj_risk, 6),
        },
        items=items,
    )


@router.get("/risk-simulation/history", response_model=SimulationHistoryResponse)
def risk_simulation_history(
    limit: int = 100,
    run_id: str | None = None,
    status_filter: str | None = None,
    request_mode: str | None = None,
    severity_band: str | None = None,
    request_type: str | None = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    _ensure_intelligence_tables(db)
    safe_limit = max(min(limit, 200), 1)
    query = db.query(SimulationRun).filter(SimulationRun.scope == "strategy_intelligence")
    if run_id:
        query = query.filter(SimulationRun.run_id.ilike(f"%{run_id.strip()}%"))
    if status_filter:
        query = query.filter(SimulationRun.status == str(status_filter).strip())
    if request_mode:
        query = query.filter(SimulationRun.request_mode == str(request_mode).strip())

    rows = query.order_by(desc(SimulationRun.created_at)).limit(min(safe_limit * 5, 800)).all()
    run_ids = [row.run_id for row in rows if row.run_id]

    request_map: dict[str, dict] = {}
    if run_ids:
        request_rows = (
            db.query(DecisionApprovalRequest)
            .filter(DecisionApprovalRequest.simulation_run_id.in_(run_ids))
            .order_by(desc(DecisionApprovalRequest.created_at))
            .all()
        )
        for request_row in request_rows:
            simulation_run_id = str(request_row.simulation_run_id or "")
            if not simulation_run_id or simulation_run_id in request_map:
                continue
            payload = request_row.payload or {}
            request_map[simulation_run_id] = {
                "decision_request_type": request_row.request_type,
                "decision_severity_band": str(payload.get("severity_band") or ""),
            }

    filtered_items: list[dict] = []
    for row in rows:
        base = _serialize_history_row(row)
        decision_meta = request_map.get(str(row.run_id), {})
        base.update({
            "decision_request_type": decision_meta.get("decision_request_type"),
            "decision_severity_band": decision_meta.get("decision_severity_band"),
        })

        if severity_band and str(base.get("decision_severity_band") or "") != str(severity_band).strip():
            continue
        if request_type and str(base.get("decision_request_type") or "") != str(request_type).strip():
            continue

        filtered_items.append(base)
        if len(filtered_items) >= safe_limit:
            break

    return SimulationHistoryResponse(items=[SimulationHistoryItemResponse(**item) for item in filtered_items])
