from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.security import hash_password
from db import get_db
from deps import require_admin
from models import User, UserExchangeConnection, UserRole, UserVenueAssignment
from schemas import (
    AdminRetentionTrendResponse,
    AdminSegmentProfitabilityResponse,
    AdminUserEconomicsResponse,
    UserEconomicsSnapshotRunResponse,
    UserEconomicsSnapshotTrendResponse,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from services.audit_service import create_audit_log
from services.identity_control_service import create_approval_request, get_or_create_identity_profile
from services.password_policy_service import validate_password_policy
from services.user_economics_service import (
    export_user_economics,
    get_retention_trend,
    get_segment_profitability,
    get_user_economics_snapshot_trend,
    get_user_economics_summary,
    run_user_economics_snapshot,
)
from services.venue_service import ensure_user_venue_assignment

router = APIRouter(prefix="/admin/users", tags=["admin_users"])
ADMIN_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.OPS}


class LocalAdminUserCreateRequest(BaseModel):
    email: str
    password: str
    role: str = "admin"


class UserVenueRepairResponse(BaseModel):
    user_id: str
    exchange_code: str
    assignment_changed: bool
    spot_allowed: bool
    futures_allowed: bool
    live_allowed: bool


class UserVenueBulkRepairResponse(BaseModel):
    processed_users: int
    changed_assignments: int


class FuturesLivePathCheckItemResponse(BaseModel):
    user_id: str
    user_email: str
    status: str
    issues: list[str]
    assignment_present: bool
    futures_assignment_ok: bool
    environment_assignment_ok: bool
    futures_connection_count: int
    trade_ready_connection_count: int


class FuturesLivePathCheckSummaryResponse(BaseModel):
    generated_at: datetime
    total_users: int
    pass_count: int
    fail_count: int
    items: list[FuturesLivePathCheckItemResponse]


class ApprovalRequiredResponse(BaseModel):
    status: str
    request_id: str
    action_key: str
    user_id: str


def _ensure_can_modify(current_admin: User, target: User):
    if current_admin.role == UserRole.OPS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops_readonly")
    if target.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot_modify_self")
    if target.role == UserRole.SUPER_ADMIN and current_admin.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")


def _apply_sort(query, sort_by: str, sort_dir: str):
    sort_dir = sort_dir.lower()
    if sort_by == "email":
        column = User.email
    else:
        column = User.created_at
    if sort_dir == "desc":
        return query.order_by(column.desc())
    return query.order_by(column.asc())


@router.get("", response_model=list[UserResponse])
def list_users(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    search: str | None = None,
    role: str | None = None,
    scope: str | None = Query(default=None),
    status_filter: str = Query(default="all", alias="status"),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = 200,
):
    _ = current_admin
    query = db.query(User)
    if scope == "admin":
        query = query.filter(User.role.in_(ADMIN_ROLES))
    elif scope == "user":
        query = query.filter(User.role == UserRole.USER, User.approval_status == "approved")

    if search:
        query = query.filter(User.email.ilike(f"%{search}%"))
    if role:
        query = query.filter(User.role == role)
    if status_filter == "active":
        query = query.filter(User.is_active.is_(True))
    elif status_filter == "disabled":
        query = query.filter(User.is_active.is_(False))
    query = _apply_sort(query, sort_by, sort_dir)
    return query.limit(limit).all()


@router.get("/economics", response_model=AdminUserEconomicsResponse)
def get_users_economics(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="live"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_email: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    churn_inactive_days: int = Query(default=30, ge=1, le=365),
    cohort_month: str | None = Query(default=None),
    top_limit: int = Query(default=10, ge=1, le=100),
):
    _ = current_admin
    try:
        return AdminUserEconomicsResponse(
            **get_user_economics_summary(
                db,
                environment=environment,
                start_date=start_date,
                end_date=end_date,
                user_email=user_email,
                symbol=symbol,
                churn_inactive_days=churn_inactive_days,
                cohort_month=cohort_month,
                top_limit=top_limit,
            )
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "target_user_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/economics/retention-trend", response_model=AdminRetentionTrendResponse)
def get_users_economics_retention_trend(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="live"),
    granularity: str = Query(default="weekly"),
    lookback_periods: int = Query(default=12, ge=1, le=104),
):
    _ = current_admin
    try:
        return AdminRetentionTrendResponse(
            **get_retention_trend(
                db,
                environment=environment,
                granularity=granularity,
                lookback_periods=lookback_periods,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/economics/segment-profitability", response_model=AdminSegmentProfitabilityResponse)
def get_users_segment_profitability(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="live"),
    churn_inactive_days: int = Query(default=30, ge=1, le=365),
    top_limit: int = Query(default=20, ge=1, le=100),
):
    _ = current_admin
    try:
        return AdminSegmentProfitabilityResponse(
            **get_segment_profitability(
                db,
                environment=environment,
                churn_inactive_days=churn_inactive_days,
                top_limit=top_limit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/economics/export.csv")
def export_users_economics_csv(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="live"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_email: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    churn_inactive_days: int = Query(default=30, ge=1, le=365),
    cohort_month: str | None = Query(default=None),
    top_limit: int = Query(default=100, ge=1, le=200),
):
    _ = current_admin
    try:
        payload, media_type, filename = export_user_economics(
            db,
            environment=environment,
            start_date=start_date,
            end_date=end_date,
            user_email=user_email,
            symbol=symbol,
            churn_inactive_days=churn_inactive_days,
            cohort_month=cohort_month,
            top_limit=top_limit,
            output="csv",
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "target_user_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    return StreamingResponse(
        iter([payload]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/economics/export.xlsx")
def export_users_economics_xlsx(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="live"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_email: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    churn_inactive_days: int = Query(default=30, ge=1, le=365),
    cohort_month: str | None = Query(default=None),
    top_limit: int = Query(default=100, ge=1, le=200),
):
    _ = current_admin
    try:
        payload, media_type, filename = export_user_economics(
            db,
            environment=environment,
            start_date=start_date,
            end_date=end_date,
            user_email=user_email,
            symbol=symbol,
            churn_inactive_days=churn_inactive_days,
            cohort_month=cohort_month,
            top_limit=top_limit,
            output="xlsx",
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "target_user_not_found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=detail) from exc
    return StreamingResponse(
        iter([payload]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/economics/snapshots/run", response_model=UserEconomicsSnapshotRunResponse)
def run_users_economics_snapshot(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="live"),
    snapshot_type: str = Query(default="daily"),
    as_of_date: str | None = Query(default=None),
    churn_inactive_days: int = Query(default=30, ge=1, le=365),
):
    _ = current_admin
    try:
        return UserEconomicsSnapshotRunResponse(
            **run_user_economics_snapshot(
                db,
                environment=environment,
                snapshot_type=snapshot_type,
                as_of_date=as_of_date,
                churn_inactive_days=churn_inactive_days,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/economics/snapshots/trend", response_model=UserEconomicsSnapshotTrendResponse)
def get_users_economics_snapshot_trend(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    environment: str = Query(default="live"),
    snapshot_type: str = Query(default="daily"),
    limit: int = Query(default=30, ge=1, le=365),
):
    _ = current_admin
    try:
        return UserEconomicsSnapshotTrendResponse(
            **get_user_economics_snapshot_trend(
                db,
                environment=environment,
                snapshot_type=snapshot_type,
                limit=limit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/admin-create", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    payload: LocalAdminUserCreateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_admin.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")

    validate_password_policy(payload.password, minimum_length=10)

    role_value = payload.role.strip().lower()
    allowed_roles = {UserRole.ADMIN.value}

    if role_value not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden_target_role")

    normalized_email = payload.email.strip()
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_already_exists")

    now = datetime.now(timezone.utc)
    new_admin = User(
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role=UserRole(role_value),
        is_active=True,
        approval_status="approved",
        approval_requested_at=now,
        approved_at=now,
        disabled_at=None,
        updated_at=now,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    identity_profile = get_or_create_identity_profile(db, new_admin.id)
    identity_profile.password_changed_at = now
    identity_profile.password_expires_at = now + timedelta(days=90)
    db.commit()

    create_audit_log(
        db,
        action="USER_ADMIN_CREATED",
        entity_type="user",
        entity_id=new_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"email": new_admin.email, "role": new_admin.role.value},
    )
    return new_admin


@router.post("/{user_id}/role", response_model=dict)
def update_user_role_legacy(
    user_id: str,
    payload: UserRoleUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_role(user_id=user_id, payload=payload, current_admin=current_admin, db=db)


@router.patch("/{user_id}/role", response_model=dict)
def update_user_role(
    user_id: str,
    payload: UserRoleUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    _ensure_can_modify(current_admin, target)

    role_value = payload.role
    if role_value not in {role.value for role in UserRole}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_role")
    if role_value == UserRole.SUPER_ADMIN.value and current_admin.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin_only")

    previous_role = target.role.value
    role_rank = {
        UserRole.USER.value: 0,
        UserRole.OPS.value: 1,
        UserRole.ADMIN.value: 2,
        UserRole.SUPER_ADMIN.value: 3,
    }
    is_escalation = role_rank.get(role_value, 0) > role_rank.get(previous_role, 0)

    if is_escalation:
        row = create_approval_request(
            db,
            actor=current_admin,
            action_key="grant_privileged_role",
            target_user_id=target.id,
            payload={"role": role_value, "critical_confirmed": True},
            reason=f"legacy_role_change:{previous_role}->{role_value}",
        )
        create_audit_log(
            db,
            action="USER_ROLE_CHANGE_APPROVAL_REQUESTED",
            entity_type="approval_request",
            entity_id=row.id,
            actor_user_id=current_admin.id,
            actor_role=current_admin.role.value,
            severity="warning",
            details={"from": previous_role, "to": role_value, "user_id": target.id, "action_key": row.action_key},
        )
        return ApprovalRequiredResponse(
            status="approval_required",
            request_id=row.id,
            action_key=row.action_key,
            user_id=target.id,
        ).model_dump()

    target.role = UserRole(role_value)
    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)

    create_audit_log(
        db,
        action="USER_ROLE_CHANGED",
        entity_type="user",
        entity_id=target.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"from": previous_role, "to": role_value, "user_id": target.id},
    )
    return {
        "status": "updated",
        "user_id": target.id,
        "role": target.role.value,
        "approval_required": False,
    }


@router.post("/{user_id}/disable", response_model=dict)
def disable_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_status(
        user_id=user_id,
        payload=UserStatusUpdateRequest(status="disabled"),
        current_admin=current_admin,
        db=db,
    )


@router.post("/{user_id}/enable", response_model=dict)
def enable_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_status(
        user_id=user_id,
        payload=UserStatusUpdateRequest(status="active"),
        current_admin=current_admin,
        db=db,
    )


@router.patch("/{user_id}/status", response_model=dict)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    _ensure_can_modify(current_admin, target)

    if payload.status not in {"active", "disabled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_status")

    previous_status = target.status
    new_status = payload.status
    action_key = None
    if new_status == "disabled":
        action_key = "disable_admin" if target.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} else "disable_user"
    elif new_status == "active":
        action_key = "enable_user"

    if action_key is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_status")

    row = create_approval_request(
        db,
        actor=current_admin,
        action_key=action_key,
        target_user_id=target.id,
        payload={"status": new_status, "critical_confirmed": True},
        reason=f"legacy_status_change:{previous_status}->{new_status}",
    )

    create_audit_log(
        db,
        action="USER_STATUS_CHANGE_APPROVAL_REQUESTED",
        entity_type="approval_request",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"from": previous_status, "to": new_status, "user_id": target.id, "action_key": action_key},
    )
    return ApprovalRequiredResponse(
        status="approval_required",
        request_id=row.id,
        action_key=action_key,
        user_id=target.id,
    ).model_dump()


@router.post("/{user_id}/repair-venue-assignment", response_model=UserVenueRepairResponse)
def repair_user_venue_assignment(
    user_id: str,
    market_type: str = Query(default="futures"),
    environment: str = Query(default="live"),
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if target.role != UserRole.USER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only_user_role_supported")

    row, changed = ensure_user_venue_assignment(
        db,
        user_id=target.id,
        exchange_code="binance",
        market_type=market_type,
        environment=environment,
        commit=True,
    )
    create_audit_log(
        db,
        action="USER_VENUE_ASSIGNMENT_REPAIRED",
        entity_type="user_venue_assignment",
        entity_id=row.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={
            "user_id": target.id,
            "exchange_code": row.exchange_code,
            "market_type": market_type,
            "environment": environment,
            "assignment_changed": changed,
        },
    )
    return UserVenueRepairResponse(
        user_id=target.id,
        exchange_code=row.exchange_code,
        assignment_changed=changed,
        spot_allowed=bool(row.spot_allowed),
        futures_allowed=bool(row.futures_allowed),
        live_allowed=bool(row.live_allowed),
    )


@router.post("/repair-venue-assignments", response_model=UserVenueBulkRepairResponse)
def repair_all_user_venue_assignments(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_admin.role == UserRole.OPS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ops_readonly")

    users = db.query(User).filter(User.role == UserRole.USER, User.approval_status == "approved").all()
    changed_count = 0
    for target in users:
        _, changed = ensure_user_venue_assignment(
            db,
            user_id=target.id,
            exchange_code="binance",
            market_type="futures",
            environment="live",
            commit=False,
        )
        if changed:
            changed_count += 1

    db.commit()
    create_audit_log(
        db,
        action="USER_VENUE_ASSIGNMENT_BULK_REPAIRED",
        entity_type="user_venue_assignment",
        entity_id=current_admin.id,
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="warning",
        details={"processed_users": len(users), "changed_assignments": changed_count},
    )
    return UserVenueBulkRepairResponse(processed_users=len(users), changed_assignments=changed_count)


def _evaluate_futures_live_path(db: Session, user: User) -> FuturesLivePathCheckItemResponse:
    assignment = (
        db.query(UserVenueAssignment)
        .filter(UserVenueAssignment.user_id == user.id, UserVenueAssignment.exchange_code == "binance")
        .first()
    )
    futures_connections = (
        db.query(UserExchangeConnection)
        .filter(
            UserExchangeConnection.user_id == user.id,
            UserExchangeConnection.exchange == "binance",
            UserExchangeConnection.market_type == "futures",
        )
        .all()
    )

    assignment_present = assignment is not None
    futures_assignment_ok = bool(assignment and assignment.futures_allowed)
    environment_assignment_ok = bool(assignment and assignment.live_allowed)
    trade_ready_connection_count = 0
    for row in futures_connections:
        snapshot = row.readiness_snapshot or {}
        if bool(snapshot.get("validation_success")) and bool(snapshot.get("can_trade")):
            trade_ready_connection_count += 1

    issues: list[str] = []
    if not assignment_present:
        issues.append("assignment_missing")
    if assignment_present and not futures_assignment_ok:
        issues.append("futures_not_allowed")
    if assignment_present and not environment_assignment_ok:
        issues.append("environment_not_allowed")
    if len(futures_connections) == 0:
        issues.append("futures_connection_missing")
    if len(futures_connections) > 0 and trade_ready_connection_count == 0:
        issues.append("trade_ready_connection_missing")

    return FuturesLivePathCheckItemResponse(
        user_id=user.id,
        user_email=user.email,
        status="PASS" if len(issues) == 0 else "FAIL",
        issues=issues,
        assignment_present=assignment_present,
        futures_assignment_ok=futures_assignment_ok,
        environment_assignment_ok=environment_assignment_ok,
        futures_connection_count=len(futures_connections),
        trade_ready_connection_count=trade_ready_connection_count,
    )


@router.get("/futures-live-path-check", response_model=FuturesLivePathCheckSummaryResponse)
def futures_live_path_check(
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=300, ge=1, le=1000),
):
    _ = current_admin
    users = (
        db.query(User)
        .filter(User.role == UserRole.USER, User.approval_status == "approved")
        .order_by(User.created_at.desc())
        .limit(limit)
        .all()
    )
    items = [_evaluate_futures_live_path(db, user) for user in users]
    pass_count = sum(1 for row in items if row.status == "PASS")
    fail_count = len(items) - pass_count
    return FuturesLivePathCheckSummaryResponse(
        generated_at=datetime.now(timezone.utc),
        total_users=len(items),
        pass_count=pass_count,
        fail_count=fail_count,
        items=items,
    )


@router.get("/{user_id}/futures-live-path-check", response_model=FuturesLivePathCheckItemResponse)
def futures_live_path_check_for_user(
    user_id: str,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _ = current_admin
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    if user.role != UserRole.USER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only_user_role_supported")
    return _evaluate_futures_live_path(db, user)
