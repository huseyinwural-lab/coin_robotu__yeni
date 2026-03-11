from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user
from models import BacktestResultCard, User
from schemas import (
    BacktestResultCardResponse,
    ReplayExecutionItemResponse,
    ReplayRiskSummaryResponse,
    ReplayRunDetailResponse,
    ReplayRunRequest,
    ReplayRunResponse,
)
from services.replay_service import (
    compute_replay_risk_summary,
    export_replay_risk_summary,
    get_replay_run_detail,
    run_replay_pipeline,
)

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/cards", response_model=list[BacktestResultCardResponse])
def list_backtest_cards(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(BacktestResultCard).order_by(BacktestResultCard.updated_at.desc()).all()


@router.post("/replay/run", response_model=ReplayRunResponse, status_code=status.HTTP_201_CREATED)
def start_replay_run(
    payload: ReplayRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        run = run_replay_pipeline(
            db,
            current_user.id,
            exchange=payload.exchange,
            market_type=payload.market_type,
            environment=payload.environment,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            strategy_type=payload.strategy_type,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ReplayRunResponse(
        run_id=run.id,
        user_id=run.user_id,
        exchange=run.exchange,
        market_type=run.market_type,
        environment=run.environment,
        symbol=run.symbol,
        timeframe=run.timeframe,
        strategy_type=run.strategy_type,
        candles_processed=run.candles_processed,
        executions_count=run.executions_count,
        filled_count=run.filled_count,
        canceled_count=run.canceled_count,
        avg_simulated_latency_ms=run.avg_simulated_latency_ms,
        avg_simulated_slippage_pct=run.avg_simulated_slippage_pct,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/replay/run/{run_id}", response_model=ReplayRunDetailResponse)
def get_replay_run(run_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        run, executions = get_replay_run_detail(db, current_user.id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ReplayRunDetailResponse(
        run_id=run.id,
        user_id=run.user_id,
        exchange=run.exchange,
        market_type=run.market_type,
        environment=run.environment,
        symbol=run.symbol,
        timeframe=run.timeframe,
        strategy_type=run.strategy_type,
        candles_processed=run.candles_processed,
        executions_count=run.executions_count,
        filled_count=run.filled_count,
        canceled_count=run.canceled_count,
        avg_simulated_latency_ms=run.avg_simulated_latency_ms,
        avg_simulated_slippage_pct=run.avg_simulated_slippage_pct,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        metrics=run.metrics,
        executions=[
            ReplayExecutionItemResponse(
                symbol=item.symbol,
                timeframe=item.timeframe,
                signal=item.signal,
                direction=item.direction,
                market_price=item.market_price,
                simulated_fill_price=item.simulated_fill_price,
                simulated_latency_ms=item.simulated_latency_ms,
                simulated_slippage_pct=item.simulated_slippage_pct,
                lifecycle=item.lifecycle,
                status=item.status,
                risk_tags=item.risk_tags,
                candle_timestamp=item.candle_timestamp,
            )
            for item in executions
        ],
    )


@router.get("/replay/{run_id}/risk-summary", response_model=ReplayRiskSummaryResponse)
def replay_risk_summary(run_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        summary = compute_replay_risk_summary(db, current_user.id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    export_file = export_replay_risk_summary(summary)
    return ReplayRiskSummaryResponse(
        schema_version=summary["schema_version"],
        run_id=summary["run_id"],
        strategy_version=summary["strategy_version"],
        max_drawdown=summary["max_drawdown"],
        sharpe=summary["sharpe"],
        win_rate=summary["win_rate"],
        profit_factor=summary["profit_factor"],
        avg_slippage_bps=summary["avg_slippage_bps"],
        volatility_bucket=summary["volatility_bucket"],
        regime_bucket_distribution=summary["regime_bucket_distribution"],
        exposure_breach_count=summary["exposure_breach_count"],
        risk_reject_count=summary["risk_reject_count"],
        evidence_type=summary["evidence_type"],
        export_file=export_file,
        generated_at=summary["generated_at"],
    )
