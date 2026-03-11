from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from deps import require_admin
from models import AdminControl, User
from schemas import (
    LiveActivationConfigResponse,
    LiveActivationConfigUpdate,
    LiveReadinessResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    TestnetConnectivityResponse,
)
from services.audit_service import create_audit_log
from services.live_mode_service import (
    adapter,
    apply_config_update,
    build_readiness_report,
    get_or_create_live_config,
    resolve_runtime_credentials,
    trigger_close_all_positions,
    trigger_stop_all_bots,
)

router = APIRouter(prefix="/phase4", tags=["phase4_live"])


@router.get("/live-config", response_model=LiveActivationConfigResponse)
def get_live_config(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_or_create_live_config(db)


@router.put("/live-config", response_model=LiveActivationConfigResponse)
def update_live_config(
    payload: LiveActivationConfigUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = get_or_create_live_config(db)
    updated = apply_config_update(db, config, payload.model_dump())
    create_audit_log(
        db,
        action="phase4_live_config_updated",
        entity_type="live_activation_config",
        entity_id=updated.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"symbol_whitelist": updated.symbol_whitelist, "max_position_pct": updated.max_position_pct},
    )
    return updated


@router.get("/readiness-check", response_model=LiveReadinessResponse)
def get_live_readiness(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    config = get_or_create_live_config(db)
    env_key, env_secret, _ = resolve_runtime_credentials(None, None)
    report = build_readiness_report(config, env_key, env_secret)
    return LiveReadinessResponse(
        mode=report["mode"],
        exchange=report["exchange"],
        market_type=report["market_type"],
        checks=report["checks"],
        safe_limits=report["safe_limits"],
        docs_references=report["docs_references"],
    )


@router.post("/permission-check", response_model=PermissionCheckResponse)
def permission_check(
    payload: PermissionCheckRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key, secret, source = resolve_runtime_credentials(payload.api_key, payload.api_secret)
    result = adapter.permission_check(key, secret)
    create_audit_log(
        db,
        action="phase4_permission_check",
        entity_type="phase4_live",
        entity_id="permission_check",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"status": result["status"], "masked_key": result["masked_key"], "source": source},
    )
    return PermissionCheckResponse(**result)


@router.get("/testnet-connectivity", response_model=TestnetConnectivityResponse)
def testnet_connectivity(_: User = Depends(require_admin)):
    return TestnetConnectivityResponse(**adapter.ping())


@router.post("/kill-switch/stop-all-bots")
def stop_all_bots(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    trigger_stop_all_bots(db)
    create_audit_log(
        db,
        action="phase4_kill_switch_stop_all_bots",
        entity_type="kill_switch",
        entity_id="stop_all_bots",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return {"status": "ok", "action": "stop_all_bots"}


@router.post("/kill-switch/close-all-positions")
def close_all_positions(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    trigger_close_all_positions(db)
    create_audit_log(
        db,
        action="phase4_kill_switch_close_all_positions",
        entity_type="kill_switch",
        entity_id="close_all_positions",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return {"status": "ok", "action": "close_all_positions"}


@router.post("/kill-switch/disable-futures")
def disable_futures(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    config = get_or_create_live_config(db)
    config.disable_futures = True

    control = db.query(AdminControl).filter(AdminControl.id == "global").first()
    if control:
        control.disable_futures = True

    db.commit()
    create_audit_log(
        db,
        action="phase4_kill_switch_disable_futures",
        entity_type="kill_switch",
        entity_id="disable_futures",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
    )
    return {"status": "ok", "action": "disable_futures"}
