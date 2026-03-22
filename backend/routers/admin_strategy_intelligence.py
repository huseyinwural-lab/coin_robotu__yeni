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
    RiskSimulationResponse,
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


@router.post("/risk-simulation", response_model=RiskSimulationResponse)
def risk_simulation(
    payload: RiskSimulationRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_valid_user_id(db, payload.user_id)
    intent_payload = payload.intent_payload or {}
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

        intent_payload = {
            **(payload.intent_payload or {}),
            "symbol": valid_symbol,
        }
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
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_user
    _ensure_intelligence_tables(db)
    safe_limit = max(min(limit, 200), 1)
    rows = db.query(SimulationRun).filter(SimulationRun.scope == "strategy_intelligence").order_by(desc(SimulationRun.created_at)).limit(safe_limit).all()
    return SimulationHistoryResponse(items=[SimulationHistoryItemResponse(**_serialize_history_row(row)) for row in rows])
