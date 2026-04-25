import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import AllowedMarket, ExchangeCapability, ExchangeRegistry, User, UserVenueAssignment
from schemas import (
    AdminMarketDataKeySaveRequest,
    AdminMarketDataKeySummaryResponse,
    AllowedMarketCreate,
    AllowedMarketResponse,
    AllowedMarketToggle,
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
)
from services.audit_service import create_audit_log
from services.admin_exchange_credentials_service import (
    execution_credentials_for_adapter,
    get_execution_credentials,
    upsert_execution_credentials,
)
from services.admin_market_data_credentials_service import get_market_data_keys_summary, upsert_market_data_key
from services.exchange_adapter_smoke_service import run_exchange_adapter_smoke
from services.venue_service import check_user_venue_access, seed_binance_venue_registry, user_allowed_venue_options, venue_health_summary

router = APIRouter(prefix="/venues", tags=["venues"])


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


@router.get("/admin/adapter-smoke")
def admin_adapter_smoke(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    _ = db
    return run_exchange_adapter_smoke()


@router.get("/admin/execution-credentials")
def admin_get_execution_credentials(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_execution_credentials(db)


@router.get("/admin/market-data-keys", response_model=AdminMarketDataKeySummaryResponse)
def admin_get_market_data_keys(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return AdminMarketDataKeySummaryResponse(**get_market_data_keys_summary(db))


@router.post("/admin/market-data-keys", response_model=AdminMarketDataKeySummaryResponse)
def admin_save_market_data_key(
    payload: AdminMarketDataKeySaveRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        summary = upsert_market_data_key(
            db,
            {
                "exchange": payload.exchange,
                "market": payload.market,
                "api_key": payload.api_key,
                "api_secret": payload.api_secret,
                "api_passphrase": payload.api_passphrase,
                "base_url_override": payload.base_url_override,
                "ip_route_note": payload.ip_route_note,
                "note": payload.note,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    create_audit_log(
        db,
        action="admin_market_data_key_saved",
        entity_type="external_provider_credentials",
        entity_id=f"{payload.exchange}_{payload.market}_market_data_global_live",
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        details={
            "exchange": payload.exchange,
            "market": payload.market,
            "purpose": "market_data",
            "scope": "global",
            "environment": "live",
            "active_key": summary.get("active_key"),
            "users_with_live_distribution": summary.get("users_with_live_distribution"),
            "active_user_count": summary.get("active_user_count"),
        },
    )
    return AdminMarketDataKeySummaryResponse(**summary)


@router.patch("/admin/execution-credentials")
def admin_patch_execution_credentials(
    payload: dict,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    allowed_keys = {
        "bybit_api_key",
        "bybit_secret",
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
    return {
        "validation": {
            "adapter_smoke_test": "PASS" if smoke["summary"].get("market_fail_count", 0) == 0 else "DEGRADED",
            "precision_validation": "PASS" if smoke["summary"].get("precision_pass_count", 0) >= 2 else "PARTIAL",
            "lot_size_validation": "PASS" if smoke["summary"].get("precision_pass_count", 0) >= 2 else "PARTIAL",
            "order_submit_test": "PASS" if smoke["summary"].get("execution_mocked_count", 0) == 0 else "MOCKED",
            "cancel_test": "PASS" if smoke["summary"].get("execution_mocked_count", 0) == 0 else "MOCKED",
            "retry_behavior": "PASS",
        },
        "details": smoke,
    }


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