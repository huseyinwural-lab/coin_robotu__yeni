from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import AllowedMarket, ExchangeCapability, ExchangeRegistry, User, UserVenueAssignment
from schemas import (
    AllowedMarketResponse,
    AllowedMarketToggle,
    ExchangeCapabilityResponse,
    ExchangeCapabilityUpdate,
    ExchangeRegistryResponse,
    ExchangeRegistryUpdate,
    UserVenueAssignmentResponse,
    UserVenueAssignmentUpdate,
    UserVenueOptionResponse,
    VenueHealthSummaryResponse,
)
from services.audit_service import create_audit_log
from services.venue_service import check_user_venue_access, seed_binance_venue_registry, user_allowed_venue_options, venue_health_summary

router = APIRouter(prefix="/venues", tags=["venues"])


@router.get("/admin/exchanges", response_model=list[ExchangeRegistryResponse])
def admin_list_exchanges(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return db.query(ExchangeRegistry).order_by(ExchangeRegistry.exchange_code.asc()).all()


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


@router.get("/admin/capabilities", response_model=list[ExchangeCapabilityResponse])
def admin_list_capabilities(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return (
        db.query(ExchangeCapability)
        .order_by(ExchangeCapability.exchange_code.asc(), ExchangeCapability.market_type.asc())
        .all()
    )


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


@router.get("/admin/allowed-markets", response_model=list[AllowedMarketResponse])
def admin_list_allowed_markets(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    seed_binance_venue_registry(db)
    return db.query(AllowedMarket).order_by(AllowedMarket.exchange_code.asc(), AllowedMarket.market_type.asc(), AllowedMarket.environment.asc()).all()


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


@router.get("/admin/health-summary", response_model=VenueHealthSummaryResponse)
def admin_health_summary(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return VenueHealthSummaryResponse(**venue_health_summary(db))


@router.get("/options", response_model=list[UserVenueOptionResponse])
def user_allowed_options(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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