from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import require_user
from models import User, UserScannerResult
from schemas import UserScannerResultResponse
from services.quote_asset_policy import extract_quote_asset

router = APIRouter(tags=["screener"])


def _read_float(payload: dict, *paths: str) -> float | None:
    for path in paths:
        current: object = payload
        for segment in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(segment)
        try:
            if current is None:
                continue
            return float(current)
        except (TypeError, ValueError):
            continue
    return None


def _read_timeframe(payload: dict) -> str:
    primary = str(payload.get("timeframe") or "").strip().lower()
    if primary:
        return primary
    nested = payload.get("indicator_snapshot") if isinstance(payload.get("indicator_snapshot"), dict) else {}
    nested_tf = str((nested or {}).get("timeframe") or "").strip().lower()
    return nested_tf or "1h"


def _parse_filters(filters_raw: str | None) -> dict:
    if not filters_raw:
        return {}
    try:
        payload = json.loads(filters_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_filters_payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_filters_payload")
    return payload


@router.get("/screener", response_model=list[UserScannerResultResponse])
def list_filtered_screener_results(
    filters: str | None = Query(default=None),
    rsi_min: float | None = Query(default=None),
    rsi_max: float | None = Query(default=None),
    volume_min: float | None = Query(default=None),
    market_cap_min: float | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    parsed_filters = _parse_filters(filters)

    effective_rsi_min = rsi_min if rsi_min is not None else parsed_filters.get("rsi_min")
    effective_rsi_max = rsi_max if rsi_max is not None else parsed_filters.get("rsi_max")
    effective_volume_min = volume_min if volume_min is not None else parsed_filters.get("volume_min")
    effective_market_cap_min = market_cap_min if market_cap_min is not None else parsed_filters.get("market_cap_min")
    effective_timeframe = str(timeframe if timeframe is not None else parsed_filters.get("timeframe") or "").strip().lower()

    rows = (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == current_user.id)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(limit)
        .all()
    )

    results: list[UserScannerResultResponse] = []
    for row in rows:
        payload = dict(row.payload or {})
        current_rsi = _read_float(payload, "rsi", "rsi14", "indicator_snapshot.rsi14")
        current_volume = _read_float(
            payload,
            "quote_volume",
            "volume",
            "indicator_snapshot.quote_volume",
            "indicator_snapshot.volume",
        )
        current_market_cap = _read_float(payload, "market_cap", "marketcap", "indicator_snapshot.market_cap")
        current_timeframe = _read_timeframe(payload)

        if effective_rsi_min is not None and (current_rsi is None or current_rsi < float(effective_rsi_min)):
            continue
        if effective_rsi_max is not None and (current_rsi is None or current_rsi > float(effective_rsi_max)):
            continue
        if effective_volume_min is not None and (current_volume is None or current_volume < float(effective_volume_min)):
            continue
        if effective_market_cap_min is not None and (
            current_market_cap is None or current_market_cap < float(effective_market_cap_min)
        ):
            continue
        if effective_timeframe and current_timeframe != effective_timeframe:
            continue

        results.append(
            UserScannerResultResponse(
                id=row.id,
                run_id=row.run_id,
                user_id=row.user_id,
                symbol=row.symbol,
                quote_asset=str((payload or {}).get("quote_asset") or extract_quote_asset(row.symbol) or "UNKNOWN"),
                strategy_code=row.strategy_code,
                signal=row.signal,
                confidence=float(row.confidence or 0),
                signal_score=float(row.signal_score or 0),
                reason_codes=list(row.reason_codes or []),
                payload=payload,
                generated_at=row.generated_at,
            )
        )

    return results
