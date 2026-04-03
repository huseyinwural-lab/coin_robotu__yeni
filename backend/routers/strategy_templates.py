import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import StrategyTemplate, User
from schemas import (
    StrategyTemplateCloneVersionRequest,
    StrategyTemplateCreate,
    StrategyTemplateDetailResponse,
    StrategyTemplatePreviewImpactRequest,
    StrategyTemplateReasonRequest,
    StrategyTemplateResolvedConfigResponse,
    StrategyTemplateResponse,
    StrategyTemplateUpdate,
)
from services.audit_service import build_critical_action_details, create_audit_log
from services.strategy_template_resolution_service import build_strategy_template_detail, ensure_seed_strategy_templates, resolve_effective_strategy_config

router = APIRouter(prefix="/strategy-templates", tags=["strategy_templates"])


def _get_template_or_404(db: Session, template_id: str) -> StrategyTemplate:
    template = db.query(StrategyTemplate).filter(StrategyTemplate.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


def _set_active_template(db: Session, template: StrategyTemplate) -> None:
    peers = db.query(StrategyTemplate).filter(StrategyTemplate.version_group_id == template.version_group_id).all()
    for peer in peers:
        if peer.id == template.id:
            continue
        if peer.is_active and peer.lifecycle_state != "ROLLED_BACK":
            peer.lifecycle_state = "DEPRECATED"
        peer.is_active = False
    template.is_active = True
    template.lifecycle_state = "ACTIVE"
    template.last_validated_at = datetime.now(timezone.utc)


@router.get("", response_model=list[StrategyTemplateResponse])
def list_strategy_templates(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_seed_strategy_templates(db, created_by=current_user.id)
    return db.query(StrategyTemplate).order_by(StrategyTemplate.created_at.desc()).all()


@router.get("/{template_id}", response_model=StrategyTemplateDetailResponse)
def get_strategy_template_detail(template_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = build_strategy_template_detail(db, template_id=template_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return StrategyTemplateDetailResponse(**payload)


@router.post("", response_model=StrategyTemplateResponse)
def create_strategy_template(
    payload: StrategyTemplateCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    duplicate = db.query(StrategyTemplate).filter(StrategyTemplate.name == payload.name).first()
    if duplicate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template name already exists")

    payload_data = payload.model_dump(exclude={"template_code", "backtest_result_ref", "reason_note", "param_schema", "logic_schema", "indicator_schema"})
    strategy_template = StrategyTemplate(
        created_by=current_admin.id,
        template_code=payload.template_code or f"tpl_{uuid.uuid4().hex[:10]}",
        version_group_id=str(uuid.uuid4()),
        version_num=1,
        lifecycle_state="DRAFT",
        is_active=False,
        param_schema=payload.param_schema or {},
        logic_schema=payload.logic_schema or {},
        indicator_schema=payload.indicator_schema or {},
        backtest_result_ref=payload.backtest_result_ref,
        last_validated_at=datetime.now(timezone.utc),
        **payload_data,
    )
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
        details=build_critical_action_details(actor=current_admin.id, reason=payload.reason_note or "create", scope="strategy_template:create", before_state={}, after_state={"template_id": strategy_template.id, "version": 1}),
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

    for key, value in payload.model_dump(exclude={"reason_note"}).items():
        if key == "is_active":
            continue
        setattr(strategy_template, key, value)

    strategy_template.last_validated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(strategy_template)
    create_audit_log(
        db,
        action="strategy_template_updated",
        entity_type="strategy_template",
        entity_id=strategy_template.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=build_critical_action_details(actor=current_admin.id, reason=payload.reason_note or "update", scope="strategy_template:update", before_state={}, after_state={"template_id": strategy_template.id, "version": strategy_template.version_num}),
    )
    return strategy_template


@router.post("/{template_id}/clone-version", response_model=StrategyTemplateResponse)
def clone_strategy_template_version(template_id: str, payload: StrategyTemplateCloneVersionRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    template = db.query(StrategyTemplate).filter(StrategyTemplate.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    latest = (
        db.query(StrategyTemplate)
        .filter(StrategyTemplate.version_group_id == template.version_group_id)
        .order_by(StrategyTemplate.version_num.desc())
        .first()
    )
    cloned = StrategyTemplate(
        name=payload.name or f"{template.name} v{(latest.version_num if latest else template.version_num)+1}",
        template_code=template.template_code,
        version_group_id=template.version_group_id,
        version_num=(latest.version_num if latest else template.version_num) + 1,
        lifecycle_state="DRAFT",
        parent_template_id=template.id,
        rollback_from_template_id=None,
        strategy_type=template.strategy_type,
        parameters=template.parameters,
        param_schema=template.param_schema,
        logic_schema=template.logic_schema,
        indicator_schema=template.indicator_schema,
        backtest_result_ref=template.backtest_result_ref,
        last_validated_at=datetime.now(timezone.utc),
        is_active=False,
        created_by=current_admin.id,
    )
    db.add(cloned)
    db.commit()
    db.refresh(cloned)
    create_audit_log(
        db,
        action="strategy_template_version_cloned",
        entity_type="strategy_template",
        entity_id=cloned.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=build_critical_action_details(
            actor=current_admin.id,
            reason=payload.reason,
            scope="strategy_template:clone_version",
            before_state={"template_id": template.id, "version": template.version_num},
            after_state={"template_id": cloned.id, "version": cloned.version_num},
        ),
    )
    return cloned


@router.post("/{template_id}/activate", response_model=StrategyTemplateResponse)
def activate_strategy_template(template_id: str, payload: StrategyTemplateReasonRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    template = _get_template_or_404(db, template_id)
    _set_active_template(db, template)
    db.commit()
    db.refresh(template)
    create_audit_log(db, action="strategy_template_activated", entity_type="strategy_template", entity_id=template.id, actor_user_id=current_admin.id, actor_role=current_admin.role.value, details=build_critical_action_details(actor=current_admin.id, reason=payload.reason, scope="strategy_template:activate", before_state={}, after_state={"template_id": template.id, "version": template.version_num}))
    return template


@router.post("/{template_id}/validate", response_model=StrategyTemplateResponse)
def validate_strategy_template(template_id: str, payload: StrategyTemplateReasonRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    template = _get_template_or_404(db, template_id)
    current_state = str(template.lifecycle_state or "").upper()
    if current_state not in {"DRAFT", "VALIDATED"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_state_transition_for_validation")
    template.lifecycle_state = "VALIDATED"
    template.is_active = False
    template.last_validated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(template)
    create_audit_log(
        db,
        action="strategy_template_validated",
        entity_type="strategy_template",
        entity_id=template.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=build_critical_action_details(
            actor=current_admin.id,
            reason=payload.reason,
            scope="strategy_template:validate",
            before_state={"lifecycle_state": current_state},
            after_state={"lifecycle_state": template.lifecycle_state, "version": template.version_num},
        ),
    )
    return template


@router.post("/{template_id}/mark-backtest-passed", response_model=StrategyTemplateResponse)
def mark_backtest_passed_strategy_template(template_id: str, payload: StrategyTemplateReasonRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    template = _get_template_or_404(db, template_id)
    current_state = str(template.lifecycle_state or "").upper()
    if current_state not in {"VALIDATED", "BACKTEST_PASSED"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="validation_required_before_backtest_pass")
    template.lifecycle_state = "BACKTEST_PASSED"
    template.is_active = False
    template.last_validated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(template)
    create_audit_log(
        db,
        action="strategy_template_backtest_passed",
        entity_type="strategy_template",
        entity_id=template.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=build_critical_action_details(
            actor=current_admin.id,
            reason=payload.reason,
            scope="strategy_template:mark_backtest_passed",
            before_state={"lifecycle_state": current_state},
            after_state={"lifecycle_state": template.lifecycle_state, "version": template.version_num},
        ),
    )
    return template


@router.post("/{template_id}/promote-to-active", response_model=StrategyTemplateResponse)
def promote_strategy_template_to_active(template_id: str, payload: StrategyTemplateReasonRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    template = _get_template_or_404(db, template_id)
    current_state = str(template.lifecycle_state or "").upper()
    if current_state not in {"BACKTEST_PASSED", "ACTIVE"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="backtest_pass_required_before_promote")
    _set_active_template(db, template)
    db.commit()
    db.refresh(template)
    create_audit_log(
        db,
        action="strategy_template_promoted_active",
        entity_type="strategy_template",
        entity_id=template.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=build_critical_action_details(
            actor=current_admin.id,
            reason=payload.reason,
            scope="strategy_template:promote_active",
            before_state={"lifecycle_state": current_state},
            after_state={"lifecycle_state": template.lifecycle_state, "version": template.version_num},
        ),
    )
    return template


@router.post("/{template_id}/deprecate", response_model=StrategyTemplateResponse)
def deprecate_strategy_template(template_id: str, payload: StrategyTemplateReasonRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    template = _get_template_or_404(db, template_id)
    current_state = str(template.lifecycle_state or "").upper()
    if current_state == "ROLLED_BACK":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rolled_back_template_cannot_be_deprecated")
    template.is_active = False
    template.lifecycle_state = "DEPRECATED"
    template.last_validated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(template)
    create_audit_log(
        db,
        action="strategy_template_deprecated",
        entity_type="strategy_template",
        entity_id=template.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=build_critical_action_details(
            actor=current_admin.id,
            reason=payload.reason,
            scope="strategy_template:deprecate",
            before_state={"lifecycle_state": current_state},
            after_state={"lifecycle_state": template.lifecycle_state, "version": template.version_num},
        ),
    )
    return template


@router.post("/{template_id}/rollback", response_model=StrategyTemplateResponse)
def rollback_strategy_template(template_id: str, payload: StrategyTemplateReasonRequest, current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    current = _get_template_or_404(db, template_id)
    previous_state = str(current.lifecycle_state or "").upper()
    if not current.parent_template_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rollback_target_missing")
    target = db.query(StrategyTemplate).filter(StrategyTemplate.id == current.parent_template_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rollback_target_not_found")
    peers = db.query(StrategyTemplate).filter(StrategyTemplate.version_group_id == current.version_group_id).all()
    for peer in peers:
        peer.is_active = False
        if peer.id in {target.id, current.id}:
            continue
        if str(peer.lifecycle_state or "").upper() != "ROLLED_BACK":
            peer.lifecycle_state = "DEPRECATED"
    target.is_active = True
    target.lifecycle_state = "ACTIVE"
    current.lifecycle_state = "ROLLED_BACK"
    current.rollback_from_template_id = target.id
    db.commit()
    db.refresh(target)
    create_audit_log(
        db,
        action="strategy_template_rolled_back",
        entity_type="strategy_template",
        entity_id=current.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=build_critical_action_details(
            actor=current_admin.id,
            reason=payload.reason,
            scope="strategy_template:rollback",
            before_state={"lifecycle_state": previous_state},
            after_state={"lifecycle_state": current.lifecycle_state, "rollback_target": target.id},
        ),
    )
    return target


@router.get("/{template_id}/history")
def strategy_template_history(template_id: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    template = db.query(StrategyTemplate).filter(StrategyTemplate.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    rows = db.query(StrategyTemplate).filter(StrategyTemplate.version_group_id == template.version_group_id).order_by(StrategyTemplate.version_num.desc()).all()
    return {"items": rows}


@router.post("/{template_id}/resolve", response_model=StrategyTemplateResolvedConfigResponse)
def resolve_strategy_template_endpoint(template_id: str, payload: StrategyTemplatePreviewImpactRequest, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ = payload
    resolved = resolve_effective_strategy_config(db, template_id=template_id)
    if not resolved.get("template_id"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return StrategyTemplateResolvedConfigResponse(**resolved)