from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from deps import require_super_admin
from models import User
from schemas import (
    CommercialP0DataQualityResponse,
    CommercialP0IngestionRequest,
    CommercialP0IngestionResponse,
    CommercialP0LiveGateResponse,
    CommercialP0PnlResponse,
    CommercialP0ReconciliationRequest,
    CommercialP0ReconciliationResponse,
    CommercialP0WebsocketBootstrapRequest,
    CommercialP0WebsocketBootstrapResponse,
)
from services.commercial_ops_p0_service import (
    bootstrap_user_websocket_streams,
    compute_and_persist_pnl,
    export_standardized_trades_csv,
    get_data_quality_snapshot,
    get_live_transition_gate,
    run_exchange_reconciliation,
    run_rest_trade_ingestion,
)

router = APIRouter(prefix="/admin/commercial/p0", tags=["admin_commercial_p0"])


def _to_http_error(exc: Exception) -> HTTPException:
    message = str(exc)
    mapping = {
        "target_user_not_found": (status.HTTP_404_NOT_FOUND, "target_user_not_found"),
        "binance_connection_not_found": (status.HTTP_404_NOT_FOUND, "binance_connection_not_found"),
        "binance_credentials_missing": (status.HTTP_400_BAD_REQUEST, "binance_credentials_missing"),
        "spot_symbols_required": (status.HTTP_400_BAD_REQUEST, "spot_symbols_required"),
    }
    status_code, detail = mapping.get(message, (status.HTTP_400_BAD_REQUEST, message))
    return HTTPException(status_code=status_code, detail=detail)


@router.post("/ingestion/rest-run", response_model=CommercialP0IngestionResponse)
def run_rest_ingestion(
    payload: CommercialP0IngestionRequest,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return CommercialP0IngestionResponse(
            **run_rest_trade_ingestion(
                db,
                target_user_id=payload.target_user_id,
                target_user_email=payload.target_user_email,
                environment=payload.environment,
                market_types=payload.market_types,
                symbols=payload.symbols,
                start_ts=payload.start_ts,
                end_ts=payload.end_ts,
                limit_per_symbol=payload.limit_per_symbol,
                source="rest",
            )
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.get("/pnl/latest", response_model=CommercialP0PnlResponse)
def build_latest_pnl(
    target_user_id: str | None = Query(default=None),
    target_user_email: str | None = Query(default=None),
    environment: str = Query(default="testnet"),
    start_ts: str | None = Query(default=None),
    end_ts: str | None = Query(default=None),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return CommercialP0PnlResponse(
            **compute_and_persist_pnl(
                db,
                target_user_id=target_user_id,
                target_user_email=target_user_email,
                environment=environment,
                start_ts=start_ts,
                end_ts=end_ts,
            )
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/reconciliation/run", response_model=CommercialP0ReconciliationResponse)
def run_reconciliation(
    payload: CommercialP0ReconciliationRequest,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return CommercialP0ReconciliationResponse(
            **run_exchange_reconciliation(
                db,
                target_user_id=payload.target_user_id,
                target_user_email=payload.target_user_email,
                environment=payload.environment,
                market_types=payload.market_types,
                symbols=payload.symbols,
                start_ts=payload.start_ts,
                end_ts=payload.end_ts,
                limit_per_symbol=payload.limit_per_symbol,
                drift_tolerance_usd=payload.drift_tolerance_usd,
            )
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.get("/data-quality", response_model=CommercialP0DataQualityResponse)
def data_quality(
    target_user_id: str | None = Query(default=None),
    target_user_email: str | None = Query(default=None),
    environment: str = Query(default="testnet"),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return CommercialP0DataQualityResponse(
            **get_data_quality_snapshot(
                db,
                target_user_id=target_user_id,
                target_user_email=target_user_email,
                environment=environment,
            )
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.get("/live-gate", response_model=CommercialP0LiveGateResponse)
def live_gate(
    target_user_id: str | None = Query(default=None),
    target_user_email: str | None = Query(default=None),
    environment: str = Query(default="testnet"),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return CommercialP0LiveGateResponse(
            **get_live_transition_gate(
                db,
                target_user_id=target_user_id,
                target_user_email=target_user_email,
                environment=environment,
            )
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.post("/websocket/bootstrap", response_model=CommercialP0WebsocketBootstrapResponse)
def websocket_bootstrap(
    payload: CommercialP0WebsocketBootstrapRequest,
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        return CommercialP0WebsocketBootstrapResponse(
            **bootstrap_user_websocket_streams(
                db,
                target_user_id=payload.target_user_id,
                target_user_email=payload.target_user_email,
                environment=payload.environment,
                market_types=payload.market_types,
            )
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc


@router.get("/trades/export.csv")
def export_canonical_trades_csv(
    target_user_id: str | None = Query(default=None),
    target_user_email: str | None = Query(default=None),
    environment: str = Query(default="testnet"),
    market_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    start_ts: str | None = Query(default=None),
    end_ts: str | None = Query(default=None),
    _: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        payload, filename = export_standardized_trades_csv(
            db,
            target_user_id=target_user_id,
            target_user_email=target_user_email,
            environment=environment,
            market_type=market_type,
            symbol=symbol,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise _to_http_error(exc) from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([payload]), media_type="text/csv", headers=headers)
