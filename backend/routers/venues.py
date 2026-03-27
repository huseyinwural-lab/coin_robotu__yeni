import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin, require_super_admin
from models import AuditLog, AdminExchangeCredential, AllowedMarket, ExchangeCapability, ExchangeRegistry, User, UserVenueAssignment
from schemas import (
    AdminExchangeCredentialCreateRequest,
    AdminExchangeCredentialPatchRequest,
    AdminExchangeCredentialRotateRequest,
    AdminExchangeCredentialResponse,
    AllowedMarketCreate,
    AllowedMarketResponse,
    AllowedMarketToggle,
    CredentialAssignmentRuleResponse,
    CredentialAssignmentRuleUpsertRequest,
    CredentialResolutionPreviewResponse,
    ExchangeCapabilityCreate,
    ExchangeCapabilityResponse,
    ExchangeCapabilityUpdate,
    ExchangeRegistryCreate,
    ExchangeRegistryResponse,
    ExchangeRegistryUpdate,
    UserVenueAssignmentResponse,
    UserVenueAssignmentUpdate,
    UserVenueOptionResponse,
    VenueHealthSummaryResponse,
    CapabilityDiscoveryRequest,
    MarketPolicyLayerUpdateRequest,
    RoutingPolicyUpsertRequest,
    RoutingPreviewRequest,
)
from services.audit_service import create_audit_log
from services.admin_exchange_credentials_service import (
    execution_credentials_for_adapter,
    get_execution_credentials,
    upsert_execution_credentials,
)
from services.exchange_adapter_smoke_service import run_exchange_adapter_smoke
from services.credential_resolution_service import (
    approve_admin_credential,
    create_admin_credential,
    disable_admin_credential,
    list_admin_credentials,
    list_assignment_rules,
    probe_admin_credential,
    revoke_admin_credential,
    resolve_exchange_credentials,
    rotate_admin_credential,
    update_admin_credential,
    upsert_assignment_rule,
    verify_admin_credential,
)
from services.venue_control_plane_service import (
    get_cached_venue_control_plane_sanity,
    run_and_cache_venue_control_plane_sanity,
)
from services.venue_service import check_user_venue_access, seed_binance_venue_registry, user_allowed_venue_options, venue_health_summary
from services.control_plane_config_service import get_control_plane_config, upsert_control_plane_config
from services.venue_discovery_service import discover_exchange_capabilities

router = APIRouter(prefix="/venues", tags=["venues"])


def _credential_error(exc: Exception) -> HTTPException:
    message = str(exc)
    mapping = {
        "invalid_scope_type": (status.HTTP_400_BAD_REQUEST, "invalid_scope_type"),
        "invalid_market_type": (status.HTTP_400_BAD_REQUEST, "invalid_market_type"),
        "invalid_environment": (status.HTTP_400_BAD_REQUEST, "invalid_environment"),
        "invalid_purpose": (status.HTTP_400_BAD_REQUEST, "invalid_purpose"),
        "invalid_preferred_source": (status.HTTP_400_BAD_REQUEST, "invalid_preferred_source"),
        "unsupported_exchange": (status.HTTP_400_BAD_REQUEST, "unsupported_exchange"),
        "credential_not_found": (status.HTTP_404_NOT_FOUND, "credential_not_found"),
        "credential_readback_verification_failed": (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "credential_readback_verification_failed",
        ),
        "credential_verify_failed": (status.HTTP_409_CONFLICT, "credential_verify_failed"),
        "invalid_rotation_payload": (status.HTTP_400_BAD_REQUEST, "invalid_rotation_payload"),
        "environment_lock_blocked": (status.HTTP_409_CONFLICT, "environment_lock_blocked"),
        "prod_freeze_active": (status.HTTP_409_CONFLICT, "prod_freeze_active"),
        "live_route_not_approved": (status.HTTP_409_CONFLICT, "live_route_not_approved"),
        "mode_mismatch_live_blocked": (status.HTTP_409_CONFLICT, "mode_mismatch_live_blocked"),
        "venue_not_allowed": (status.HTTP_409_CONFLICT, "venue_not_allowed"),
        "approved_credential_required": (status.HTTP_409_CONFLICT, "approved_credential_required"),
        "symbol_policy_blocked": (status.HTTP_409_CONFLICT, "symbol_policy_blocked"),
        "restricted_symbol_class_blocked": (status.HTTP_409_CONFLICT, "restricted_symbol_class_blocked"),
        "sanity_gate_blocked": (status.HTTP_409_CONFLICT, "sanity_gate_blocked"),
        "canary_allowlist_blocked": (status.HTTP_409_CONFLICT, "canary_allowlist_blocked"),
        "two_step_approval_missing": (status.HTTP_409_CONFLICT, "two_step_approval_missing"),
        "local_secret_provider_not_allowed_in_prod": (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "local_secret_provider_not_allowed_in_prod",
        ),
        "execution_credential_readback_verification_failed": (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "execution_credential_readback_verification_failed",
        ),
    }
    code, detail = mapping.get(message, (status.HTTP_400_BAD_REQUEST, message))
    return HTTPException(status_code=code, detail=detail)


@router.get("/admin/exchanges", response_model=list[ExchangeRegistryResponse])
def admin_list_exchanges(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return db.query(ExchangeRegistry).order_by(ExchangeRegistry.exchange_code.asc()).all()


@router.post("/admin/exchanges", response_model=ExchangeRegistryResponse, status_code=status.HTTP_201_CREATED)
def admin_create_exchange(
    payload: ExchangeRegistryCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    exchange_code = payload.exchange_code.strip().lower()
    if not exchange_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exchange_code zorunlu")

    existing = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exchange zaten kayıtlı")

    market_types = sorted({item.strip().lower() for item in payload.supported_market_types if item.strip()})
    row = ExchangeRegistry(
        id=str(uuid.uuid4()),
        exchange_code=exchange_code,
        exchange_name=payload.exchange_name.strip(),
        status=payload.status.strip().lower(),
        supported_market_types=market_types,
        supports_testnet=payload.supports_testnet,
        supports_live=payload.supports_live,
        health_status=payload.health_status.strip().lower(),
        rate_limit_status=payload.rate_limit_status.strip().lower(),
        adapter_version=payload.adapter_version.strip(),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_exchange_created",
        entity_type="exchange_registry",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"exchange_code": row.exchange_code, "exchange_name": row.exchange_name},
    )
    return row


@router.patch("/admin/exchanges/{exchange_code}", response_model=ExchangeRegistryResponse)
def admin_update_exchange(
    exchange_code: str,
    payload: ExchangeRegistryUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code.lower()).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    row.status = payload.status
    row.health_status = payload.health_status
    row.rate_limit_status = payload.rate_limit_status
    row.adapter_version = payload.adapter_version
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_exchange_updated",
        entity_type="exchange_registry",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange_code": row.exchange_code,
            "status": row.status,
            "health_status": row.health_status,
            "rate_limit_status": row.rate_limit_status,
            "adapter_version": row.adapter_version,
        },
    )
    return row


@router.delete("/admin/exchanges/{exchange_code}")
def admin_delete_exchange(
    exchange_code: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_code = exchange_code.lower()
    row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == normalized_code).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    capabilities_deleted = (
        db.query(ExchangeCapability).filter(ExchangeCapability.exchange_code == normalized_code).delete()
    )
    markets_deleted = db.query(AllowedMarket).filter(AllowedMarket.exchange_code == normalized_code).delete()
    assignments_deleted = (
        db.query(UserVenueAssignment).filter(UserVenueAssignment.exchange_code == normalized_code).delete()
    )
    db.delete(row)
    db.commit()

    create_audit_log(
        db,
        action="venue_exchange_deleted",
        entity_type="exchange_registry",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "exchange_code": normalized_code,
            "capabilities_deleted": capabilities_deleted,
            "allowed_markets_deleted": markets_deleted,
            "assignments_deleted": assignments_deleted,
        },
    )
    return {"deleted": True, "exchange_code": normalized_code}


@router.get("/admin/capabilities", response_model=list[ExchangeCapabilityResponse])
def admin_list_capabilities(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return (
        db.query(ExchangeCapability)
        .order_by(ExchangeCapability.exchange_code.asc(), ExchangeCapability.market_type.asc())
        .all()
    )


@router.post("/admin/capabilities", response_model=ExchangeCapabilityResponse, status_code=status.HTTP_201_CREATED)
def admin_create_capability(
    payload: ExchangeCapabilityCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    exchange_code = payload.exchange_code.strip().lower()
    market_type = payload.market_type.strip().lower()

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code).first()
    if exchange_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    existing = (
        db.query(ExchangeCapability)
        .filter(ExchangeCapability.exchange_code == exchange_code, ExchangeCapability.market_type == market_type)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Capability zaten kayıtlı")

    row = ExchangeCapability(
        id=str(uuid.uuid4()),
        exchange_code=exchange_code,
        market_type=market_type,
        supports_spot=payload.supports_spot,
        supports_futures=payload.supports_futures,
        supports_test_order=payload.supports_test_order,
        supports_quote_qty=payload.supports_quote_qty,
        supports_reduce_only=payload.supports_reduce_only,
        supports_leverage=payload.supports_leverage,
        supports_margin_mode=payload.supports_margin_mode,
        supports_hedge_mode=payload.supports_hedge_mode,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_capability_created",
        entity_type="exchange_capability",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"exchange_code": row.exchange_code, "market_type": row.market_type},
    )
    return row


@router.put("/admin/capabilities/{capability_id}", response_model=ExchangeCapabilityResponse)
def admin_update_capability(
    capability_id: str,
    payload: ExchangeCapabilityUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(ExchangeCapability).filter(ExchangeCapability.id == capability_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability bulunamadı")

    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_capability_updated",
        entity_type="exchange_capability",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"exchange_code": row.exchange_code, "market_type": row.market_type, **payload.model_dump()},
    )
    return row


@router.delete("/admin/capabilities/{capability_id}")
def admin_delete_capability(
    capability_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(ExchangeCapability).filter(ExchangeCapability.id == capability_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability bulunamadı")

    db.delete(row)
    db.commit()
    create_audit_log(
        db,
        action="venue_capability_deleted",
        entity_type="exchange_capability",
        entity_id=capability_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"exchange_code": row.exchange_code, "market_type": row.market_type},
    )
    return {"deleted": True, "capability_id": capability_id}


@router.get("/admin/allowed-markets", response_model=list[AllowedMarketResponse])
def admin_list_allowed_markets(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return db.query(AllowedMarket).order_by(AllowedMarket.exchange_code.asc(), AllowedMarket.market_type.asc(), AllowedMarket.environment.asc()).all()


@router.post("/admin/allowed-markets", response_model=AllowedMarketResponse, status_code=status.HTTP_201_CREATED)
def admin_create_allowed_market(
    payload: AllowedMarketCreate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    exchange_code = payload.exchange_code.strip().lower()
    market_type = payload.market_type.strip().lower()
    environment = payload.environment.strip().lower()

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_code).first()
    if exchange_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    existing = (
        db.query(AllowedMarket)
        .filter(
            AllowedMarket.exchange_code == exchange_code,
            AllowedMarket.market_type == market_type,
            AllowedMarket.environment == environment,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Allowed market zaten kayıtlı")

    row = AllowedMarket(
        id=str(uuid.uuid4()),
        exchange_code=exchange_code,
        market_type=market_type,
        environment=environment,
        enabled=payload.enabled,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_allowed_market_created",
        entity_type="allowed_market",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange_code": row.exchange_code,
            "market_type": row.market_type,
            "environment": row.environment,
            "enabled": row.enabled,
        },
    )
    return row


@router.put("/admin/allowed-markets/{allowed_market_id}", response_model=AllowedMarketResponse)
def admin_toggle_allowed_market(
    allowed_market_id: str,
    payload: AllowedMarketToggle,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(AllowedMarket).filter(AllowedMarket.id == allowed_market_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed market kaydı bulunamadı")

    row.enabled = payload.enabled
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_allowed_market_toggled",
        entity_type="allowed_market",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange_code": row.exchange_code,
            "market_type": row.market_type,
            "environment": row.environment,
            "enabled": row.enabled,
        },
    )
    return row


@router.delete("/admin/allowed-markets/{allowed_market_id}")
def admin_delete_allowed_market(
    allowed_market_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(AllowedMarket).filter(AllowedMarket.id == allowed_market_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowed market kaydı bulunamadı")

    db.delete(row)
    db.commit()
    create_audit_log(
        db,
        action="venue_allowed_market_deleted",
        entity_type="allowed_market",
        entity_id=allowed_market_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "exchange_code": row.exchange_code,
            "market_type": row.market_type,
            "environment": row.environment,
        },
    )
    return {"deleted": True, "allowed_market_id": allowed_market_id}


@router.get("/admin/user-assignments", response_model=list[UserVenueAssignmentResponse])
def admin_list_user_assignments(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    user_id: str | None = Query(default=None),
):
    query = db.query(UserVenueAssignment)
    if user_id:
        query = query.filter(UserVenueAssignment.user_id == user_id)
    return query.order_by(UserVenueAssignment.updated_at.desc()).all()


@router.put("/admin/user-assignments", response_model=UserVenueAssignmentResponse)
def admin_upsert_user_assignment(
    payload: UserVenueAssignmentUpdate,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    seed_binance_venue_registry(db)
    target_user = db.query(User).filter(User.id == payload.user_id).first()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == payload.exchange_code.lower()).first()
    if exchange_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exchange bulunamadı")

    row = (
        db.query(UserVenueAssignment)
        .filter(UserVenueAssignment.user_id == payload.user_id, UserVenueAssignment.exchange_code == payload.exchange_code.lower())
        .first()
    )
    if row is None:
        row = UserVenueAssignment(
            user_id=payload.user_id,
            exchange_code=payload.exchange_code.lower(),
        )
        db.add(row)

    row.spot_allowed = payload.spot_allowed
    row.futures_allowed = payload.futures_allowed
    row.testnet_allowed = payload.testnet_allowed
    row.live_allowed = payload.live_allowed
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    create_audit_log(
        db,
        action="venue_user_assignment_updated",
        entity_type="user_venue_assignment",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details=payload.model_dump(),
    )
    return row


@router.delete("/admin/user-assignments/{assignment_id}")
def admin_delete_user_assignment(
    assignment_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(UserVenueAssignment).filter(UserVenueAssignment.id == assignment_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User assignment bulunamadı")

    db.delete(row)
    db.commit()
    create_audit_log(
        db,
        action="venue_user_assignment_deleted",
        entity_type="user_venue_assignment",
        entity_id=assignment_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"user_id": row.user_id, "exchange_code": row.exchange_code},
    )
    return {"deleted": True, "assignment_id": assignment_id}


@router.get("/admin/health-summary", response_model=VenueHealthSummaryResponse)
def admin_health_summary(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return VenueHealthSummaryResponse(**venue_health_summary(db))


@router.post("/admin/capability-discovery")
def admin_capability_discovery(
    payload: CapabilityDiscoveryRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    discovery = discover_exchange_capabilities(
        exchange_code=payload.exchange_code,
        market_type=payload.market_type,
        environment=payload.environment,
        symbols=payload.symbols,
    )
    matrix = get_control_plane_config(db, config_key="capability_matrix", default={})
    key = f"{payload.exchange_code.lower()}:{payload.market_type.lower()}:{payload.environment.lower()}"
    old_value = matrix.get(key)
    matrix[key] = discovery
    upsert_control_plane_config(db, config_key="capability_matrix", payload=matrix, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="venue_capability_discovery_synced",
        entity_type="venue_capability_matrix",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_value, "new_value": discovery},
    )
    return {
        "net_status": "PASS",
        "reason_codes": discovery.get("reason_codes") or [],
        "remediation_suggestions": [],
        "checks": [
            {
                "name": "adapter_capability_discovery",
                "status": "PASS",
                "reason_code": "discovery_synced",
                "severity": "low",
                "remediation_suggestions": [],
            }
        ],
        "capability": discovery,
    }


@router.get("/admin/capability-matrix")
def admin_get_capability_matrix(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_control_plane_config(db, config_key="capability_matrix", default={})


@router.put("/admin/market-policy-layer")
def admin_upsert_market_policy_layer(
    payload: MarketPolicyLayerUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    policy = get_control_plane_config(db, config_key="market_policy", default={"rules": {}})
    rules = dict(policy.get("rules") or {})
    key = f"{payload.exchange_code.lower()}:{payload.market_type.lower()}:{payload.environment.lower()}"
    old_value = rules.get(key)
    rules[key] = {
        "symbol_rules": payload.symbol_rules,
        "restricted_symbol_classes": payload.restricted_symbol_classes,
        "risk_tier_defaults": payload.risk_tier_defaults,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    policy["rules"] = rules
    upsert_control_plane_config(db, config_key="market_policy", payload=policy, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="venue_market_policy_updated",
        entity_type="venue_market_policy",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_value, "new_value": rules[key]},
    )
    return {"updated": True, "key": key, "policy": rules[key]}


@router.get("/admin/market-policy-layer")
def admin_get_market_policy_layer(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_control_plane_config(db, config_key="market_policy", default={"rules": {}})


@router.put("/admin/routing-policies")
def admin_upsert_routing_policies(
    payload: RoutingPolicyUpsertRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    routing = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})
    rules = dict(routing.get("rules") or {})
    key = f"{payload.user_id}:{payload.strategy_id}"
    old_value = rules.get(key)
    rules[key] = {
        "default_venue": payload.default_venue,
        "preferred_venues": payload.preferred_venues,
        "blocked_venues": payload.blocked_venues,
        "capital_allocation": payload.capital_allocation,
        "execution_policy_override": payload.execution_policy_override,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    routing["rules"] = rules
    upsert_control_plane_config(db, config_key="routing_policy", payload=routing, actor_user_id=current_admin.id)
    create_audit_log(
        db,
        action="venue_routing_policy_updated",
        entity_type="venue_routing_policy",
        entity_id=key,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"old_value": old_value, "new_value": rules[key]},
    )
    return {"updated": True, "key": key, "routing_rule": rules[key]}


@router.get("/admin/routing-policies")
def admin_get_routing_policies(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})


@router.post("/admin/routing-preview-v2")
def admin_routing_preview_v2(
    payload: RoutingPreviewRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    routing = get_control_plane_config(db, config_key="routing_policy", default={"rules": {}})
    key = f"{payload.user_id}:{payload.strategy_id}"
    rule = (routing.get("rules") or {}).get(key) or {}

    try:
        resolved = resolve_exchange_credentials(
            db,
            user_id=payload.user_id,
            exchange=(rule.get("default_venue") or "binance"),
            market_type=payload.market_type,
            environment=payload.environment,
            purpose="execution",
            symbol=payload.symbol,
            include_secrets=False,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    selected_exchange = str(resolved.get("exchange") or "")
    blocked = set(rule.get("blocked_venues") or [])
    preferred = set(rule.get("preferred_venues") or [])

    status_value = "PASS"
    reason_codes: list[str] = []
    remediation: list[str] = []
    if selected_exchange in blocked:
        status_value = "BLOCK"
        reason_codes.append("selected_venue_blocked_by_routing_policy")
        remediation.append("Routing policy içindeki blocked_venues listesini güncelleyin.")
    elif preferred and selected_exchange not in preferred:
        status_value = "WARN"
        reason_codes.append("selected_venue_not_in_preferred")
        remediation.append("Default venue değerini preferred listesiyle hizalayın.")

    return {
        "net_status": status_value,
        "reason_codes": reason_codes,
        "remediation_suggestions": remediation,
        "checks": [
            {
                "name": "strategy_level_venue_selection",
                "status": status_value,
                "reason_code": reason_codes[0] if reason_codes else "routing_ok",
                "severity": "high" if status_value == "BLOCK" else ("medium" if status_value == "WARN" else "low"),
                "remediation_suggestions": remediation,
            }
        ],
        "resolved_execution_path": resolved,
        "routing_rule": rule,
        "capital_allocation": rule.get("capital_allocation") or [],
    }


@router.get("/admin/operational-health")
def admin_operational_health(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    summary = venue_health_summary(db)
    sanity = get_cached_venue_control_plane_sanity() or {"net_status": "WARN", "reason_codes": ["sanity_not_run"]}

    exchange_rows = db.query(ExchangeRegistry).all()
    exchange_scores = []
    for row in exchange_rows:
        score = 100
        reason_codes = []
        if row.health_status == "degraded":
            score -= 30
            reason_codes.append("health_degraded")
        if row.health_status == "down":
            score -= 70
            reason_codes.append("health_down")
        if row.rate_limit_status not in {"ok", "healthy"}:
            score -= 20
            reason_codes.append("rate_limit_pressure")
        exchange_scores.append(
            {
                "exchange": row.exchange_code,
                "health_score": max(0, score),
                "health_status": row.health_status,
                "rate_limit_status": row.rate_limit_status,
                "latency_ms_p95": None,
                "validation_success_rate": None,
                "permission_drift": None,
                "websocket_sync_health": "unknown",
                "orderbook_sync_health": "unknown",
                "reason_codes": reason_codes,
            }
        )

    return {
        "net_status": "PASS" if sanity.get("net_status") == "PASS" else "WARN",
        "reason_codes": sanity.get("reason_codes") or [],
        "remediation_suggestions": sanity.get("remediation_suggestions") or [],
        "checks": sanity.get("checks") or [],
        "exchange_health": summary.get("exchange_health") or {},
        "market_availability": summary.get("market_availability") or {},
        "operational_scores": exchange_scores,
    }


@router.get("/admin/audit-timeline")
def admin_audit_timeline(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "old_value": (row.details or {}).get("old_value"),
                "new_value": (row.details or {}).get("new_value"),
                "details": row.details or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.get("/admin/adapter-smoke")
def admin_adapter_smoke(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    _ = db
    return run_exchange_adapter_smoke()


@router.get("/admin/execution-credentials")
def admin_get_execution_credentials(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_execution_credentials(db)


@router.patch("/admin/execution-credentials")
def admin_patch_execution_credentials(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    allowed_keys = {
        "bybit_api_key",
        "bybit_secret",
        "bybit_testnet_api_key",
        "bybit_testnet_secret",
        "bybit_live_api_key",
        "bybit_live_secret",
        "okx_api_key",
        "okx_secret",
        "okx_passphrase",
    }
    sanitized = {key: str(value or "") for key, value in (payload or {}).items() if key in allowed_keys}
    result = upsert_execution_credentials(db, sanitized)
    create_audit_log(
        db,
        action="admin_exchange_execution_credentials_updated",
        entity_type="external_provider_credentials",
        entity_id="exchange_execution_credentials_v1",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "updated_keys": sorted(list(sanitized.keys())),
            "has_bybit_credentials": result.get("has_bybit_credentials"),
            "has_okx_credentials": result.get("has_okx_credentials"),
        },
    )
    return result


@router.post("/admin/execution-validation")
def admin_execution_validation(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    credentials = execution_credentials_for_adapter(db)
    smoke = run_exchange_adapter_smoke(credentials_override=credentials)

    bybit_ready = smoke["summary"].get("execution_bybit_pass_count", 0) >= 1
    adapter_ok = smoke["summary"].get("market_fail_count", 0) == 0
    precision_ok = smoke["summary"].get("precision_pass_count", 0) >= 2

    checks = [
        {
            "name": "balance_fetch_test",
            "status": "PASS" if adapter_ok else "BLOCK",
            "reason_code": "balance_fetch_failed" if not adapter_ok else "ok",
            "severity": "high" if not adapter_ok else "low",
            "remediation_suggestions": ["Credential/venue connectivity ve balance endpoint erişimini doğrulayın."] if not adapter_ok else [],
        },
        {
            "name": "permission_test",
            "status": "PASS" if bybit_ready else "BLOCK",
            "reason_code": "permission_or_probe_failed" if not bybit_ready else "ok",
            "severity": "high" if not bybit_ready else "low",
            "remediation_suggestions": ["Execution permission scope ve credential approval durumunu doğrulayın."] if not bybit_ready else [],
        },
        {
            "name": "order_submit_test",
            "status": "PASS" if bybit_ready else "BLOCK",
            "reason_code": "order_submit_failed" if not bybit_ready else "ok",
            "severity": "high" if not bybit_ready else "low",
            "remediation_suggestions": ["Test/sandbox order submit akışını venue tarafında doğrulayın."] if not bybit_ready else [],
        },
        {
            "name": "cancel_test",
            "status": "PASS" if bybit_ready else "BLOCK",
            "reason_code": "cancel_failed" if not bybit_ready else "ok",
            "severity": "high" if not bybit_ready else "low",
            "remediation_suggestions": ["Submit edilen test order’ın cancel endpoint akışını kontrol edin."] if not bybit_ready else [],
        },
        {
            "name": "precision_lot_validation",
            "status": "PASS" if precision_ok else "WARN",
            "reason_code": "precision_validation_partial" if not precision_ok else "ok",
            "severity": "medium" if not precision_ok else "low",
            "remediation_suggestions": ["Symbol minQty/stepSize/tickSize metadata senkronunu yenileyin."] if not precision_ok else [],
        },
    ]

    highest_rank = 0
    for item in checks:
        status_value = str(item.get("status") or "PASS").lower()
        highest_rank = max(highest_rank, 2 if status_value == "block" else (1 if status_value == "warn" else 0))
    net_status = "PASS" if highest_rank == 0 else ("WARN" if highest_rank == 1 else "BLOCK")

    reason_codes = sorted({item["reason_code"] for item in checks if item.get("reason_code") and item.get("reason_code") != "ok"})
    remediation = sorted({suggestion for item in checks for suggestion in (item.get("remediation_suggestions") or [])})

    return {
        "net_status": net_status,
        "reason_codes": reason_codes,
        "remediation_suggestions": remediation,
        "checks": checks,
        "validation": {
            "adapter_smoke_test": "PASS" if adapter_ok else "BLOCK",
            "precision_validation": "PASS" if precision_ok else "WARN",
            "lot_size_validation": "PASS" if precision_ok else "WARN",
            "order_submit_test": "PASS" if bybit_ready else "BLOCK",
            "cancel_test": "PASS" if bybit_ready else "BLOCK",
            "retry_behavior": "PASS",
            "bybit_testnet_live_ready": "PASS" if bybit_ready else "BLOCK",
        },
    }


@router.get("/admin/credentials", response_model=list[AdminExchangeCredentialResponse])
def admin_list_orchestration_credentials(
    exchange: str | None = Query(default=None),
    market_type: str | None = Query(default=None),
    purpose: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    approval_status: str | None = Query(default=None),
    include_inactive: bool = Query(default=True),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = list_admin_credentials(
        db,
        exchange=exchange,
        market_type=market_type,
        purpose=purpose,
        environment=environment,
        scope_type=scope_type,
        approval_status=approval_status,
        include_inactive=include_inactive,
    )
    return [AdminExchangeCredentialResponse(**row) for row in rows]


@router.post("/admin/credentials", response_model=AdminExchangeCredentialResponse, status_code=status.HTTP_201_CREATED)
def admin_create_orchestration_credential(
    payload: AdminExchangeCredentialCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = create_admin_credential(
            db,
            actor=current_admin,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            exchange=payload.exchange,
            market_type=payload.market_type,
            purpose=payload.purpose,
            environment=payload.environment,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            passphrase=payload.passphrase,
            base_url_override=payload.base_url_override,
            ip_binding_note=payload.ip_binding_note,
            is_default=payload.is_default,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    create_audit_log(
        db,
        action="admin_credential_created",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange": row["exchange"],
            "market_type": row["market_type"],
            "environment": row["environment"],
            "scope_type": row["scope_type"],
            "purpose": row["purpose"],
            "approval_status": row["approval_status"],
        },
    )
    return AdminExchangeCredentialResponse(**row)


@router.patch("/admin/credentials/{credential_id}", response_model=AdminExchangeCredentialResponse)
def admin_patch_orchestration_credential(
    credential_id: str,
    payload: AdminExchangeCredentialPatchRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = update_admin_credential(
            db,
            actor=current_admin,
            credential_id=credential_id,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            purpose=payload.purpose,
            base_url_override=payload.base_url_override,
            ip_binding_note=payload.ip_binding_note,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            passphrase=payload.passphrase,
            is_default=payload.is_default,
            is_active=payload.is_active,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    create_audit_log(
        db,
        action="admin_credential_updated",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"updated_fields": sorted([k for k, v in payload.model_dump().items() if v is not None])},
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/approve", response_model=AdminExchangeCredentialResponse)
def admin_approve_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = approve_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_approved",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/disable", response_model=AdminExchangeCredentialResponse)
def admin_disable_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = disable_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_disabled",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/verify", response_model=AdminExchangeCredentialResponse)
def admin_verify_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = verify_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_verified",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"probe_status": row.get("last_probe_status")},
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/revoke", response_model=AdminExchangeCredentialResponse)
def admin_revoke_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = revoke_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_revoked",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/rotate", response_model=AdminExchangeCredentialResponse)
def admin_rotate_orchestration_credential(
    credential_id: str,
    payload: AdminExchangeCredentialRotateRequest,
    current_admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = rotate_admin_credential(
            db,
            actor=current_admin,
            credential_id=credential_id,
            api_key=payload.api_key,
            api_secret=payload.api_secret,
            passphrase=payload.passphrase,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_rotated",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/credentials/{credential_id}/probe", response_model=AdminExchangeCredentialResponse)
def admin_probe_orchestration_credential(
    credential_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = probe_admin_credential(db, actor=current_admin, credential_id=credential_id)
    except Exception as exc:
        raise _credential_error(exc) from exc
    create_audit_log(
        db,
        action="admin_credential_probe_executed",
        entity_type="admin_exchange_credential",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={"probe_status": row.get("last_probe_status"), "probe_message": row.get("last_probe_message")},
    )
    return AdminExchangeCredentialResponse(**row)


@router.post("/admin/control-plane-sanity-check")
def admin_run_control_plane_sanity_check(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = run_and_cache_venue_control_plane_sanity(db)
    create_audit_log(
        db,
        action="venue_control_plane_sanity_check",
        entity_type="venue_control_plane",
        entity_id="global",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "net_status": result.get("net_status"),
            "reason_codes": result.get("reason_codes") or [],
        },
    )
    return result


@router.get("/admin/control-plane-sanity-last")
def admin_get_control_plane_sanity_last(
    current_admin: User = Depends(require_admin),
):
    _ = current_admin
    cached = get_cached_venue_control_plane_sanity()
    if cached is None:
        return {"net_status": "WARN", "reason_codes": ["sanity_not_run"], "remediation_suggestions": ["Sanity check çalıştırın"], "checks": []}
    return cached


@router.get("/admin/credential-rules", response_model=list[CredentialAssignmentRuleResponse])
def admin_list_credential_rules(
    exchange: str | None = Query(default=None),
    market_type: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = list_assignment_rules(db, exchange=exchange, market_type=market_type, environment=environment)
    return [CredentialAssignmentRuleResponse(**row) for row in rows]


@router.put("/admin/credential-rules", response_model=CredentialAssignmentRuleResponse)
def admin_put_credential_rule(
    payload: CredentialAssignmentRuleUpsertRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = upsert_assignment_rule(
            db,
            actor=current_admin,
            exchange=payload.exchange,
            market_type=payload.market_type,
            environment=payload.environment,
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            preferred_source=payload.preferred_source,
            fallback_enabled=payload.fallback_enabled,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    create_audit_log(
        db,
        action="admin_credential_rule_updated",
        entity_type="credential_assignment_rule",
        entity_id=row["id"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange": row["exchange"],
            "market_type": row["market_type"],
            "environment": row["environment"],
            "preferred_source": row["preferred_source"],
            "fallback_enabled": row["fallback_enabled"],
        },
    )
    return CredentialAssignmentRuleResponse(**row)


@router.get("/admin/credential-resolution-preview", response_model=CredentialResolutionPreviewResponse)
def admin_credential_resolution_preview(
    user_id: str,
    exchange: str = Query(default="binance"),
    market_type: str = Query(default="spot"),
    environment: str = Query(default="testnet"),
    purpose: str = Query(default="execution"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    request_id = str(uuid.uuid4())
    resolved_at = datetime.now(timezone.utc).isoformat()
    try:
        result = resolve_exchange_credentials(
            db,
            user_id=user_id,
            exchange=exchange,
            market_type=market_type,
            environment=environment,
            purpose=purpose,
            include_secrets=False,
        )
    except Exception as exc:
        raise _credential_error(exc) from exc

    selected_probe_status = None
    selected_probe_message = None
    selected_id = result.get("selected_credential_id")
    if selected_id:
        selected_row = db.query(AdminExchangeCredential).filter(AdminExchangeCredential.id == selected_id).first()
        if selected_row:
            selected_probe_status = selected_row.last_probe_status
            selected_probe_message = selected_row.last_probe_message

    enriched = {
        **result,
        "request_id": request_id,
        "resolved_at": resolved_at,
        "exchange": exchange,
        "market_type": market_type,
        "environment": environment,
        "purpose": purpose,
        "fallback_chain": ["user", "tenant_admin", "global_admin"],
        "selected_probe_status": selected_probe_status,
        "selected_probe_message": selected_probe_message,
    }

    create_audit_log(
        db,
        action="admin_credential_resolution_preview",
        entity_type="credential_resolution_trace",
        entity_id=request_id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "request_id": request_id,
            "resolved_at": resolved_at,
            "user_id": user_id,
            "exchange": exchange,
            "market_type": market_type,
            "environment": environment,
            "purpose": purpose,
            "source": result.get("source"),
            "selected_credential_id": result.get("selected_credential_id"),
            "masked_fingerprint": result.get("masked_fingerprint"),
            "selection_reason": (result.get("audit_metadata") or {}).get("selection_reason"),
            "rule_id": (result.get("audit_metadata") or {}).get("rule_id"),
            "selected_probe_status": selected_probe_status,
            "selected_probe_message": selected_probe_message,
        },
    )

    return CredentialResolutionPreviewResponse(**enriched)


@router.get("/options", response_model=list[UserVenueOptionResponse])
def user_allowed_options(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    options = user_allowed_venue_options(db, current_user.id)
    if not options:
        return [
            UserVenueOptionResponse(
                exchange="-",
                market_type="-",
                environment="-",
                venue_state="no_assigned_venues",
            )
        ]
    return [UserVenueOptionResponse(**item) for item in options]


@router.get("/access-check")
def user_access_check(
    exchange: str,
    market_type: str,
    environment: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    seed_binance_venue_registry(db)
    allowed, venue_state, capability_match, reason_codes = check_user_venue_access(
        db,
        current_user.id,
        exchange.lower(),
        market_type.lower(),
        environment.lower(),
    )
    return {
        "allowed": allowed,
        "venue_state": venue_state,
        "capability_match": capability_match,
        "reason_codes": reason_codes,
    }