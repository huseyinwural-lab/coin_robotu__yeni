import statistics
import uuid
from datetime import datetime, timezone
import math

import httpx
from sqlalchemy.orm import Session

from models import ReplayEquityPoint, ReplayExecution, ReplayRun, RiskPolicyAuditEvent
from services.artifact_service import write_signed_artifact
from services.pipeline.position_sizing_engine import compute_position_sizing
from services.venue_service import check_user_venue_access, seed_binance_venue_registry

BINANCE_FUTURES_LIVE_REST = "https://fapi.binance.com"
SUPPORTED_INTERVALS = {"1m", "5m", "15m", "1h"}


def _fetch_futures_klines(symbol: str, timeframe: str, limit: int) -> list[dict]:
    if timeframe not in SUPPORTED_INTERVALS:
        raise ValueError("unsupported_timeframe")

    try:
        response = httpx.get(
            f"{BINANCE_FUTURES_LIVE_REST}/fapi/v1/klines",
            params={"symbol": symbol.upper(), "interval": timeframe, "limit": limit},
            timeout=12,
        )
    except httpx.HTTPError as exc:
        raise ValueError("live_unreachable") from exc

    if response.status_code >= 400:
        raise ValueError("exchange_rejected")

    rows = response.json()
    candles: list[dict] = []
    for row in rows:
        ts = datetime.fromtimestamp(int(row[0]) / 1000, timezone.utc)
        candles.append(
            {
                "timestamp": ts.isoformat(),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        )
    return candles


def _rolling_signal(candles: list[dict], idx: int) -> tuple[str, str, float]:
    closes = [item["close"] for item in candles[idx - 20 : idx + 1]]
    sma_fast = statistics.fmean(closes[-5:])
    sma_slow = statistics.fmean(closes)
    confidence = min(0.95, max(0.35, abs(sma_fast - sma_slow) / max(sma_slow, 1e-8) * 120))

    if sma_fast > sma_slow * 1.0006:
        return "long", "BUY", confidence
    if sma_fast < sma_slow * 0.9994:
        return "short", "SELL", confidence
    return "none", "NONE", confidence


def run_replay_pipeline(
    db: Session,
    user_id: str,
    *,
    exchange: str,
    market_type: str,
    environment: str,
    symbol: str,
    timeframe: str,
    strategy_type: str,
    limit: int,
) -> ReplayRun:
    normalized_exchange = exchange.strip().lower()
    normalized_market_type = market_type.strip().lower()
    normalized_environment = environment.strip().lower()

    seed_binance_venue_registry(db)
    allowed, _, capability_match, reason_codes = check_user_venue_access(
        db,
        user_id,
        normalized_exchange,
        normalized_market_type,
        normalized_environment,
    )
    if not allowed:
        reason = (reason_codes or ["exchange_rejected"])[0]
        raise ValueError(reason)
    if not capability_match:
        raise ValueError("exchange_rejected")
    if normalized_exchange != "binance" or normalized_market_type != "futures":
        raise ValueError("exchange_rejected")

    candles = _fetch_futures_klines(symbol, timeframe, limit)
    if len(candles) < 60:
        raise ValueError("insufficient_history")


    run = ReplayRun(
        id=str(uuid.uuid4()),
        user_id=user_id,
        exchange=normalized_exchange,
        market_type=normalized_market_type,
        environment=normalized_environment,
        symbol=symbol.upper(),
        timeframe=timeframe,
        strategy_type=strategy_type,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    latency_samples: list[float] = []
    slippage_samples: list[float] = []
    filled_count = 0
    canceled_count = 0
    gross_pnl = 0.0
    execution_count = 0
    exposure_breach_count = 0
    running_equity = float(sizing["equity"]) if (sizing := compute_position_sizing(db, user_id, candles[30]["close"])) else 10000.0
    peak_equity = running_equity

    for idx in range(30, len(candles) - 1):
        candle = candles[idx]
        next_candle = candles[idx + 1]
        signal, direction, confidence = _rolling_signal(candles, idx)
        if signal == "none":
            continue

        market_price = candle["close"]
        spread_pct = abs(candle["high"] - candle["low"]) / max(market_price, 1e-8) * 100
        risk_tags: list[str] = []
        if spread_pct > 1.4:
            risk_tags.append("volatility_spike")
            exposure_breach_count += 1
        if confidence < 0.45:
            risk_tags.append("low_confidence")

        sizing = compute_position_sizing(db, user_id, market_price)
        qty = max(float(sizing["quantity"]), 0.0001)

        if risk_tags:
            lifecycle = ["SIM_NEW", "SIM_CANCELED"]
            status = "SIM_CANCELED"
            simulated_fill_price = None
            simulated_latency = None
            simulated_slippage = None
            pnl = 0.0
            canceled_count += 1
        else:
            simulated_slippage = round(min(0.25, spread_pct * 0.35), 6)
            if direction == "BUY":
                simulated_fill_price = round(market_price * (1 + simulated_slippage / 100), 6)
                pnl = (next_candle["close"] - simulated_fill_price) * qty
            else:
                simulated_fill_price = round(market_price * (1 - simulated_slippage / 100), 6)
                pnl = (simulated_fill_price - next_candle["close"]) * qty

            simulated_latency = round(70 + spread_pct * 180, 2)
            lifecycle = ["SIM_NEW", "SIM_FILLED"]
            status = "SIM_FILLED"
            slippage_samples.append(simulated_slippage)
            latency_samples.append(simulated_latency)
            filled_count += 1
            gross_pnl += pnl

        running_equity = max(running_equity + pnl, 0.01)
        peak_equity = max(peak_equity, running_equity)
        drawdown_pct = round(((peak_equity - running_equity) / max(peak_equity, 1e-8)) * 100, 6)

        execution_count += 1
        execution = ReplayExecution(
            id=str(uuid.uuid4()),
            replay_run_id=run.id,
            user_id=user_id,
            symbol=symbol.upper(),
            timeframe=timeframe,
            signal=signal,
            direction=direction,
            market_price=market_price,
            simulated_fill_price=simulated_fill_price,
            simulated_latency_ms=simulated_latency,
            simulated_slippage_pct=simulated_slippage,
            lifecycle=lifecycle,
            status=status,
            risk_tags=risk_tags,
            candle_timestamp=candle["timestamp"],
        )
        db.add(execution)
        db.add(
            ReplayEquityPoint(
                id=str(uuid.uuid4()),
                replay_run_id=run.id,
                user_id=user_id,
                point_timestamp=candle["timestamp"],
                equity=round(running_equity, 6),
                pnl_delta=round(pnl, 6),
                drawdown_pct=drawdown_pct,
            )
        )

    run.candles_processed = len(candles)
    run.executions_count = execution_count
    run.filled_count = filled_count
    run.canceled_count = canceled_count
    run.avg_simulated_latency_ms = round(statistics.fmean(latency_samples), 4) if latency_samples else 0
    run.avg_simulated_slippage_pct = round(statistics.fmean(slippage_samples), 6) if slippage_samples else 0
    run.metrics = {
        "gross_pnl": round(gross_pnl, 4),
        "win_rate_proxy_pct": round((filled_count / max(execution_count, 1)) * 100, 2),
        "pipeline": [
            "historical_data",
            "signal_engine",
            "risk_engine",
            "position_sizing",
            "simulated_execution",
            "metrics",
        ],
        "strategy_version": f"{strategy_type}-v1",
        "risk_reject_count": canceled_count,
        "exposure_breach_count": exposure_breach_count,
    }
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    _persist_risk_policy_audit_event(db, run)
    db.commit()
    db.refresh(run)
    return run


def get_replay_run_detail(db: Session, user_id: str, run_id: str) -> tuple[ReplayRun, list[ReplayExecution]]:
    run = db.query(ReplayRun).filter(ReplayRun.id == run_id, ReplayRun.user_id == user_id).first()
    if run is None:
        raise ValueError("replay_not_found")
    executions = (
        db.query(ReplayExecution)
        .filter(ReplayExecution.replay_run_id == run.id)
        .order_by(ReplayExecution.created_at.asc())
        .all()
    )
    return run, executions


def compute_replay_risk_summary(db: Session, user_id: str, run_id: str) -> dict:
    run = db.query(ReplayRun).filter(ReplayRun.id == run_id, ReplayRun.user_id == user_id).first()
    if run is None:
        raise ValueError("replay_not_found")

    executions = (
        db.query(ReplayExecution)
        .filter(ReplayExecution.replay_run_id == run.id, ReplayExecution.user_id == user_id)
        .order_by(ReplayExecution.created_at.asc())
        .all()
    )
    points = (
        db.query(ReplayEquityPoint)
        .filter(ReplayEquityPoint.replay_run_id == run.id, ReplayEquityPoint.user_id == user_id)
        .order_by(ReplayEquityPoint.created_at.asc())
        .all()
    )

    pnl_series = [float(item.pnl_delta or 0) for item in points]
    wins = [item for item in pnl_series if item > 0]
    losses = [item for item in pnl_series if item < 0]
    max_drawdown = max((float(item.drawdown_pct or 0) for item in points), default=0)

    mean = statistics.fmean(pnl_series) if pnl_series else 0
    std = statistics.pstdev(pnl_series) if len(pnl_series) > 1 else 0
    sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0
    win_rate = (len(wins) / max(len([v for v in pnl_series if v != 0]), 1)) * 100

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)

    slip_values = [float(item.simulated_slippage_pct or 0) for item in executions if item.simulated_slippage_pct is not None]
    avg_slippage_bps = (statistics.fmean(slip_values) * 100) if slip_values else 0

    high_vol_count = sum(1 for item in executions if "volatility_spike" in (item.risk_tags or []))
    low_conf_count = sum(1 for item in executions if "low_confidence" in (item.risk_tags or []))
    normal_count = max(len(executions) - high_vol_count - low_conf_count, 0)
    regime_distribution = {
        "high_volatility": high_vol_count,
        "low_confidence": low_conf_count,
        "normal": normal_count,
    }

    if max_drawdown >= 20:
        volatility_bucket = "extreme"
    elif max_drawdown >= 12:
        volatility_bucket = "high"
    elif max_drawdown >= 6:
        volatility_bucket = "medium"
    else:
        volatility_bucket = "low"

    risk_reject_count = sum(1 for item in executions if item.status == "SIM_CANCELED")
    exposure_breach_count = high_vol_count

    summary = {
        "schema_version": "replay-risk-summary-v1",
        "run_id": run.id,
        "strategy_version": str(run.metrics.get("strategy_version") or f"{run.strategy_type}-v1"),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": round(sharpe, 6),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 6),
        "avg_slippage_bps": round(avg_slippage_bps, 6),
        "volatility_bucket": volatility_bucket,
        "regime_bucket_distribution": regime_distribution,
        "exposure_breach_count": exposure_breach_count,
        "risk_reject_count": risk_reject_count,
        "evidence_type": "fallback_replay",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return summary


def export_replay_risk_summary(summary: dict) -> dict:
    signed = write_signed_artifact(
        summary,
        artifact_type="replay_risk_summary",
        filename_prefix=f"replay_risk_summary_{summary['run_id']}",
    )
    return {"path": str(signed["path"]), "artifact_id": signed["artifact_id"]}


def _persist_risk_policy_audit_event(db: Session, run: ReplayRun) -> None:
    existing = db.query(RiskPolicyAuditEvent).filter(RiskPolicyAuditEvent.replay_run_id == run.id).first()
    if existing is not None:
        return

    points = (
        db.query(ReplayEquityPoint)
        .filter(ReplayEquityPoint.replay_run_id == run.id, ReplayEquityPoint.user_id == run.user_id)
        .order_by(ReplayEquityPoint.created_at.asc())
        .all()
    )
    executions = (
        db.query(ReplayExecution)
        .filter(ReplayExecution.replay_run_id == run.id, ReplayExecution.user_id == run.user_id)
        .order_by(ReplayExecution.created_at.asc())
        .all()
    )
    max_drawdown = max((float(item.drawdown_pct or 0) for item in points), default=0)

    high_vol = sum(1 for item in executions if "volatility_spike" in (item.risk_tags or []))
    low_conf = sum(1 for item in executions if "low_confidence" in (item.risk_tags or []))
    normal = max(len(executions) - high_vol - low_conf, 0)
    regime_bucket = max(
        {
            "high_volatility": high_vol,
            "low_confidence": low_conf,
            "normal": normal,
        }.items(),
        key=lambda kv: kv[1],
    )[0]

    row = RiskPolicyAuditEvent(
        id=str(uuid.uuid4()),
        replay_run_id=run.id,
        user_id=run.user_id,
        strategy_version=str(run.metrics.get("strategy_version") or f"{run.strategy_type}-v1"),
        regime_bucket=regime_bucket,
        drawdown=round(max_drawdown, 6),
        exposure_breach=int(run.metrics.get("exposure_breach_count") or 0),
        reject_count=int(run.metrics.get("risk_reject_count") or 0),
    )
    db.add(row)

