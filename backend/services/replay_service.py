import statistics
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from models import ReplayExecution, ReplayRun
from services.pipeline.position_sizing_engine import compute_position_sizing
from services.venue_service import check_user_venue_access, seed_binance_venue_registry

BINANCE_FUTURES_TESTNET_REST = "https://testnet.binancefuture.com"
SUPPORTED_INTERVALS = {"1m", "5m", "15m", "1h"}


def _fetch_futures_klines(symbol: str, timeframe: str, limit: int) -> list[dict]:
    if timeframe not in SUPPORTED_INTERVALS:
        raise ValueError("unsupported_timeframe")

    try:
        response = httpx.get(
            f"{BINANCE_FUTURES_TESTNET_REST}/fapi/v1/klines",
            params={"symbol": symbol.upper(), "interval": timeframe, "limit": limit},
            timeout=12,
        )
    except httpx.HTTPError as exc:
        raise ValueError("testnet_unreachable") from exc

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
    }
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
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
