import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import StrategyDefinition, StrategyVersion, User
from schemas import (
    DecisionContextInput,
    DecisionResultResponse,
    StrategyDefinitionCreate,
    StrategyDefinitionResponse,
    StrategyDetailResponse,
    StrategyVersionCreate,
    StrategyVersionResponse,
)
from services.audit_service import create_audit_log
from services.decision_kernel_service import build_context_hash, build_decision_hash, evaluate_decision_context
from services.strategy_domain_service import (
    activate_strategy_version,
    archive_strategy,
    create_strategy_definition,
    create_strategy_version,
    get_active_strategy_set,
    get_strategy,
    get_version,
)


router = APIRouter(prefix="/strategy-domain", tags=["strategy_domain"])


@router.get("/admin/strategies", response_model=list[StrategyDefinitionResponse])
def admin_list_strategies(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return db.query(StrategyDefinition).order_by(StrategyDefinition.updated_at.desc()).all()


@router.post("/admin/strategies", response_model=StrategyDefinitionResponse, status_code=status.HTTP_201_CREATED)
def admin_create_strategy(
    payload: StrategyDefinitionCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = create_strategy_definition(
        db,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        created_by=current_admin.id,
    )
    create_audit_log(
        db,
        action="strategy_definition_created",
        entity_type="strategy_definition",
        entity_id=row.strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": row.name, "code": row.code},
    )
    return row


@router.get("/admin/strategies/{strategy_id}", response_model=StrategyDetailResponse)
def admin_get_strategy_detail(strategy_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    strategy = get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy_not_found")

    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.desc())
        .all()
    )
    return StrategyDetailResponse(
        strategy=StrategyDefinitionResponse.model_validate(strategy),
        versions=[StrategyVersionResponse.model_validate(item) for item in versions],
    )


@router.post("/admin/strategies/{strategy_id}/versions", response_model=StrategyVersionResponse, status_code=status.HTTP_201_CREATED)
def admin_create_strategy_version(
    strategy_id: str,
    payload: StrategyVersionCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = create_strategy_version(
        db,
        strategy_id=strategy_id,
        config_json=payload.config_json,
        config_schema_version=payload.config_schema_version,
        created_by=current_admin.id,
    )
    create_audit_log(
        db,
        action="strategy_version_created",
        entity_type="strategy_version",
        entity_id=row.version_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"strategy_id": strategy_id, "version_number": row.version_number, "version_hash": row.version_hash},
    )
    return row


@router.post("/admin/strategies/{strategy_id}/activate/{version_id}", response_model=StrategyDefinitionResponse)
def admin_activate_strategy_version(
    strategy_id: str,
    version_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    strategy = activate_strategy_version(db, strategy_id=strategy_id, version_id=version_id)
    create_audit_log(
        db,
        action="strategy_version_activated",
        entity_type="strategy_definition",
        entity_id=strategy.strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"active_version_id": strategy.active_version_id},
    )
    return strategy


@router.post("/admin/strategies/{strategy_id}/archive", response_model=StrategyDefinitionResponse)
def admin_archive_strategy(strategy_id: str, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    strategy = archive_strategy(db, strategy_id=strategy_id)
    create_audit_log(
        db,
        action="strategy_archived",
        entity_type="strategy_definition",
        entity_id=strategy.strategy_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"status": strategy.status},
    )
    return strategy


@router.get("/admin/registry/active", response_model=list[StrategyDefinitionResponse])
def admin_active_strategy_set(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _ = current_admin
    return get_active_strategy_set(db)


@router.post("/admin/kernel/evaluate", response_model=DecisionResultResponse)
def admin_evaluate_kernel(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    try:
        context = DecisionContextInput.model_validate(payload)
    except ValidationError:
        reject_payload = {
            "action": "REJECT",
            "order_intent": {"intent_type": "REJECT", "symbol": payload.get("symbol")},
            "size": 0.0,
            "price_reference": {"source": "market_snapshot", "value": None},
            "confidence": 0.0,
            "risk_score": 1.0,
            "reason_codes": ["validation_error"],
            "strategy_version_id": payload.get("strategy_version_id"),
            "context_hash": build_context_hash(payload),
        }
        reject_payload["decision_hash"] = build_decision_hash(reject_payload)
        return DecisionResultResponse(decision_id=str(uuid.uuid4()), **reject_payload)

    version = get_version(db, context.strategy_version_id)

    context_payload = context.model_dump()
    context_hash = build_context_hash(context_payload)

    if version is None:
        result_payload = {
            "action": "REJECT",
            "order_intent": {"intent_type": "REJECT", "symbol": context.symbol},
            "size": 0.0,
            "price_reference": {"source": "market_snapshot", "value": context.market_snapshot.get("last_price")},
            "confidence": 0.0,
            "risk_score": 1.0,
            "reason_codes": ["strategy_version_not_found"],
            "strategy_version_id": context.strategy_version_id,
            "context_hash": context_hash,
        }
        result_payload["decision_hash"] = build_decision_hash(result_payload)
        return DecisionResultResponse(decision_id=str(uuid.uuid4()), **result_payload)

    if version.version_hash != context.strategy_version_hash:
        result_payload = {
            "action": "REJECT",
            "order_intent": {"intent_type": "REJECT", "symbol": context.symbol},
            "size": 0.0,
            "price_reference": {"source": "market_snapshot", "value": context.market_snapshot.get("last_price")},
            "confidence": 0.0,
            "risk_score": 1.0,
            "reason_codes": ["strategy_version_hash_mismatch"],
            "strategy_version_id": context.strategy_version_id,
            "context_hash": context_hash,
        }
        result_payload["decision_hash"] = build_decision_hash(result_payload)
        return DecisionResultResponse(decision_id=str(uuid.uuid4()), **result_payload)

    decision = evaluate_decision_context(context_payload)
    return DecisionResultResponse(decision_id=str(uuid.uuid4()), **decision)
