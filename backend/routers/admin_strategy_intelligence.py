from datetime import datetime, timezone
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.policy.quote_policy import InvalidSymbol, normalize_symbol
from db import get_db
from deps import require_admin
from models import User, UserRole
from schemas import (
    AdminStrategyIntelligenceResponse,
    HedgeSuggestionResponse,
    ManualOverrideRequest,
    ManualOverrideRevokeRequest,
    ManualOverrideRevokeResponse,
    ManualOverrideResponse,
    RebalanceGovernanceSummaryResponse,
    RiskSimulationRequest,
    RiskSimulationResponse,
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


def _require_simulation(simulation_id: str) -> dict:
    entry = _SIMULATION_REGISTRY.get(simulation_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apply öncesi geçerli simulation zorunlu")

    expires_at = entry.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at <= datetime.now(timezone.utc):
        _SIMULATION_REGISTRY.pop(simulation_id, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Simulation süresi doldu, tekrar çalıştırın")
    return entry


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


@router.post("/manual-overrides", response_model=ManualOverrideResponse)
def create_manual_override(
    payload: ManualOverrideRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_override_write_access(current_user)
    if len((payload.reason or "").strip()) < 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason minimum 12 karakter olmalı")

    simulation_entry = _require_simulation(payload.simulation_id)
    resolved_expiry = _resolve_expiry(expires_at=payload.expires_at, ttl_minutes=payload.ttl_minutes)
    role = _role_name(current_user)

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
    db.commit()
    db.refresh(row)
    return ManualOverrideResponse(**normalize_manual_override_row(row))


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


@router.post("/risk-simulation", response_model=RiskSimulationResponse)
def risk_simulation(
    payload: RiskSimulationRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
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
        user_id=payload.user_id,
        strategy_id=strategy_id,
        symbol=symbol,
        signal_direction=side,
        confidence_score=float(intent_payload.get("signal_confidence") or 0.65),
    )
    rebalance_result = evaluate_capital_rebalance(db, user_id=payload.user_id, apply_changes=False)
    hedge_result = evaluate_hedge_suggestion(
        db,
        user_id=payload.user_id,
        volatility=float(intent_payload.get("volatility_pct") or 0),
    )
    risk_result = portfolio_risk_check(
        db,
        user_id=payload.user_id,
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

    if payload.apply_override:
        _require_override_write_access(current_user)
        if not payload.override_reason or len(payload.override_reason.strip()) < 12:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="override_reason minimum 12 karakter olmalı")
        simulation_entry = _require_simulation(simulation_id)
        record_manual_override(
            db,
            admin_id=current_user.id,
            action_type=payload.override_action_type or "risk_simulation_override",
            reason=payload.override_reason or "manual_override_from_simulation",
            scope="strategy_intelligence",
            target_type="user",
            target_id=payload.user_id,
            simulation_id=simulation_id,
            confirmation_id=f"confirm_{simulation_id}",
            previous_state=simulation_entry.get("before_state") or {},
            next_state=simulation_entry.get("after_state") or {},
            impact_preview=simulation_entry.get("impact_preview") or {},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
            actor_role=_role_name(current_user),
            payload={"simulation": simulation, "target_user_id": payload.user_id, "source": "risk_simulation_apply_override"},
        )
        db.commit()

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
        before_state=simulation.get("before_state") or {},
        after_state=simulation.get("after_state") or {},
        decision_summary=simulation.get("decision_summary") or {},
        risk_delta=float(simulation.get("risk_delta") or 0),
        decision_delta=str(simulation.get("decision_delta") or "UNCHANGED"),
    )
