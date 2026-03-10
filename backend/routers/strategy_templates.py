from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import StrategyTemplate, User
from schemas import StrategyTemplateCreate, StrategyTemplateResponse, StrategyTemplateUpdate
from services.audit_service import create_audit_log

router = APIRouter(prefix="/strategy-templates", tags=["strategy_templates"])


@router.get("", response_model=list[StrategyTemplateResponse])
def list_strategy_templates(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(StrategyTemplate).order_by(StrategyTemplate.created_at.desc()).all()


@router.post("", response_model=StrategyTemplateResponse)
def create_strategy_template(
    payload: StrategyTemplateCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    duplicate = db.query(StrategyTemplate).filter(StrategyTemplate.name == payload.name).first()
    if duplicate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template name already exists")

    strategy_template = StrategyTemplate(created_by=current_admin.id, **payload.model_dump())
    db.add(strategy_template)
    db.commit()
    db.refresh(strategy_template)

    create_audit_log(
        db,
        action="strategy_template_created",
        entity_type="strategy_template",
        entity_id=strategy_template.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": strategy_template.name, "type": strategy_template.strategy_type},
    )
    return strategy_template


@router.put("/{template_id}", response_model=StrategyTemplateResponse)
def update_strategy_template(
    template_id: str,
    payload: StrategyTemplateUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    strategy_template = db.query(StrategyTemplate).filter(StrategyTemplate.id == template_id).first()
    if strategy_template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    for key, value in payload.model_dump().items():
        setattr(strategy_template, key, value)

    db.commit()
    db.refresh(strategy_template)
    create_audit_log(
        db,
        action="strategy_template_updated",
        entity_type="strategy_template",
        entity_id=strategy_template.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"name": strategy_template.name},
    )
    return strategy_template