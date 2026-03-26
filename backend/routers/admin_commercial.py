from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_super_admin
from models import User
from schemas import (
    AdminCommercialOverviewResponse,
    AdminCommercialTotalPnlResponse,
    CommercialExportManifestCreateRequest,
    CommercialExportManifestResponse,
    CommercialExportScheduleCreateRequest,
    CommercialExportScheduleResponse,
    CommercialOperationalControlResponse,
    CommercialOperationalControlUpdateRequest,
    CommercialUsageLogsResponse,
)
from services.admin_commercial_service import (
    build_admin_commercial_overview,
    build_total_pnl_bundle,
    build_usage_logs,
    create_commercial_export_manifest,
    create_commercial_export_schedule,
    export_monthly_pnl_excel,
    list_commercial_export_schedules,
    update_user_operational_controls,
)

router = APIRouter(prefix="/admin/commercial", tags=["admin_commercial"])


@router.get("/overview", response_model=AdminCommercialOverviewResponse)
def admin_commercial_overview(
    time_window: str = Query(default="last_30_days"),
    environment: str = Query(default="live"),
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return build_admin_commercial_overview(
            db,
            time_window=time_window,
            environment=environment,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    except ValueError as exc:
        if str(exc) == "target_user_not_found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/exports/request", response_model=CommercialExportManifestResponse)
def create_export_manifest(
    payload: CommercialExportManifestCreateRequest,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return create_commercial_export_manifest(
            db,
            actor_user=actor,
            export_type=payload.export_type,
            schema_version=payload.schema_version,
            filters_snapshot=payload.filters_snapshot,
            column_mapping=payload.column_mapping,
            output_format=payload.output_format,
            row_count=payload.row_count,
            reason_note=payload.reason_note,
        )
    except ValueError as exc:
        if str(exc) == "target_user_not_found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/exports/schedules", response_model=CommercialExportScheduleResponse)
def create_export_schedule(
    payload: CommercialExportScheduleCreateRequest,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return create_commercial_export_schedule(
            db,
            actor_user=actor,
            export_type=payload.export_type,
            schedule_period=payload.schedule_period,
            output_format=payload.output_format,
            filters_snapshot=payload.filters_snapshot,
        )
    except ValueError as exc:
        if str(exc) == "target_user_not_found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/exports/schedules", response_model=list[CommercialExportScheduleResponse])
def get_export_schedules(
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return list_commercial_export_schedules(db)


@router.post("/controls/{target_user_id}", response_model=CommercialOperationalControlResponse)
def set_user_operational_controls(
    target_user_id: str,
    payload: CommercialOperationalControlUpdateRequest,
    actor: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return update_user_operational_controls(
            db,
            actor_user=actor,
            target_user_id=target_user_id,
            trading_enabled=payload.trading_enabled,
            capital_frozen=payload.capital_frozen,
            withdraw_locked=payload.withdraw_locked,
            emergency_stop=payload.emergency_stop,
            reason_note=payload.reason_note,
        )
    except ValueError as exc:
        if str(exc) == "target_user_not_found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/usage-logs", response_model=CommercialUsageLogsResponse)
def admin_usage_logs(
    user_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    status_filter: str = Query(default="all", alias="status"),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return build_usage_logs(
        db,
        user_id=user_id,
        symbol=symbol,
        status_filter=status_filter,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )


@router.get("/total-pnl", response_model=AdminCommercialTotalPnlResponse)
def admin_total_pnl(
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return build_total_pnl_bundle(db)


@router.get("/monthly-pnl/export")
def admin_monthly_pnl_export(
    month: str | None = Query(default=None, description="YYYY-MM"),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    payload, filename = export_monthly_pnl_excel(db, month=month)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )