from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user, require_admin
from models import User
from services.audit_service import create_audit_log
from services.pipeline.spot_dynamic_score_engine import run_dynamic_selection_cycle
from services.pipeline.runtime import pipeline_runtime
from services.pipeline.spot_strategy_service import (
    MIN_15M_CANDLES,
    bootstrap_market_data_store,
    generate_daily_strategy_report,
    get_spot_tradable_universe,
    refresh_spot_tradable_universe,
)
from services.strategy_observability_service import log_strategy_observability_events

router = APIRouter(prefix="/spot-strategy", tags=["spot_strategy"])


@router.get("/universe")
def get_universe(_: User = Depends(get_current_user)):
    return get_spot_tradable_universe(pipeline_runtime.cache)


@router.post("/universe/refresh")
def refresh_universe(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    universe_payload = refresh_spot_tradable_universe(pipeline_runtime.cache)
    symbols = universe_payload.get("symbols", [])
    bootstrap_payload = bootstrap_market_data_store(pipeline_runtime.cache, symbols, MIN_15M_CANDLES)
    create_audit_log(
        db,
        action="SPOT_UNIVERSE_REFRESHED",
        entity_type="spot_universe",
        entity_id=universe_payload.get("generated_at", "-"),
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"count": universe_payload.get("count", 0), "bootstrap": bootstrap_payload},
    )
    return {"universe": universe_payload, "bootstrap": bootstrap_payload}


@router.get("/indicators/{symbol}")
def get_symbol_indicators(symbol: str, _: User = Depends(get_current_user)):
    key = f"indicators:spot:{symbol.upper()}:15m"
    payload = pipeline_runtime.cache.get(key)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="indicator_not_found")
    import json

    return json.loads(payload)


@router.get("/market-data/{symbol}")
def get_market_data(symbol: str, limit: int = Query(default=500, ge=50, le=600), _: User = Depends(get_current_user)):
    import json

    raw = pipeline_runtime.cache.get(f"market_data_store:{symbol.upper()}:15m")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="market_data_not_found")
    candles = json.loads(raw)
    return {"symbol": symbol.upper(), "timeframe": "15m", "count": len(candles), "candles": candles[-limit:]}


@router.post("/report/daily/generate")
def run_daily_report(current_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    report = generate_daily_strategy_report(db, pipeline_runtime.cache)
    create_audit_log(
        db,
        action="DAILY_STRATEGY_REPORT_GENERATED",
        entity_type="strategy_report",
        entity_id=report["date"],
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={"daily_trades": report.get("daily_trades", 0), "win_rate": report.get("win_rate", 0)},
    )
    return report


@router.get("/report/daily")
def get_daily_report(_: User = Depends(get_current_user)):
    payload = pipeline_runtime.cache.get("spot_strategy:daily_report")
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="daily_report_not_found")
    import json

    return json.loads(payload)


@router.post("/scan/run")
def run_spot_scan(current_admin: User = Depends(require_admin), db: Session = Depends(get_db), top_n: int = Query(default=10, ge=1, le=50)):
    universe = get_spot_tradable_universe(pipeline_runtime.cache)
    symbols = [symbol.upper() for symbol in universe.get("symbols", [])]
    payload = run_dynamic_selection_cycle(
        pipeline_runtime.cache,
        symbols=symbols,
        open_symbols=set(),
        available_slots=top_n,
    )
    top_ranked = payload.get("ranked", [])[:20]
    selected = payload.get("selected", [])
    response_payload = {
        **payload,
        "symbol_count": payload.get("symbol_count", len(top_ranked)),
        "executable_count": len(selected),
        "top_ranked": [
            {
                "symbol": item.get("symbol"),
                "signal": item.get("signal"),
                "strategy_id": item.get("strategy_id"),
                "strategy_name": item.get("strategy_name"),
                "market_regime": item.get("market_regime"),
                "signal_score": item.get("adjusted_score", 0),
                "base_score": item.get("base_score", 0),
                "adjusted_score": item.get("adjusted_score", 0),
                "reason_codes": item.get("reason_codes", []),
            }
            for item in top_ranked
        ],
    }
    scan_audit = create_audit_log(
        db,
        action="SPOT_SCAN_COMPLETED",
        entity_type="spot_strategy_scan",
        entity_id=response_payload.get("generated_at", "-"),
        actor_user_id=current_admin.id,
        actor_role=current_admin.role.value,
        severity="info",
        details={
            "symbol_count": response_payload.get("symbol_count", 0),
            "executable_count": response_payload.get("executable_count", 0),
            "market_regime": response_payload.get("market_regime"),
            "multiplier_version": response_payload.get("multiplier_version"),
        },
    )

    cycle_id = f"manual-scan:{current_admin.id}:{response_payload.get('generated_at','-')}"
    log_strategy_observability_events(
        db,
        selection_cycle_id=cycle_id,
        audit_log_id=scan_audit.id,
        bot_profile_id=None,
        user_id=current_admin.id,
        strategy_id=response_payload.get("active_strategy_id", "spot_pullback_v1"),
        strategy_name=response_payload.get("active_strategy_name", "SPOT_TREND_PULLBACK"),
        market_regime=response_payload.get("market_regime", "RANGING"),
        multiplier_version=response_payload.get("multiplier_version", "v1"),
        multiplier_set=response_payload.get("multiplier_set", {}),
        ranked=response_payload.get("ranked", []),
        selected=response_payload.get("selected", []),
    )

    return response_payload


@router.get("/scan/latest")
def get_latest_scan(_: User = Depends(get_current_user)):
    payload = pipeline_runtime.cache.get("spot_strategy:last_scan")
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan_not_found")
    import json

    data = json.loads(payload)
    if "top_ranked" not in data and "ranked" in data:
        data["top_ranked"] = [
            {
                "symbol": item.get("symbol"),
                "signal": item.get("signal"),
                "strategy_id": item.get("strategy_id"),
                "strategy_name": item.get("strategy_name"),
                "market_regime": item.get("market_regime"),
                "signal_score": item.get("adjusted_score", 0),
                "base_score": item.get("base_score", 0),
                "adjusted_score": item.get("adjusted_score", 0),
                "reason_codes": item.get("reason_codes", []),
            }
            for item in data.get("ranked", [])[:20]
        ]
        data["executable_count"] = len(data.get("selected", []))
    return data
