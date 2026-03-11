from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import PaperPosition, PositionLedgerEvent, RiskExposureGroup
from services.pipeline.correlation_service import pair_correlation
from services.pipeline.position_sizing_engine import compute_position_sizing, daily_loss_usage

DEFAULT_CAPITAL_ALLOCATION = {
    "spot_pullback_v1": 0.45,
    "spot_range_reversion_v1": 0.35,
    "spot_volatility_breakout_v1": 0.20,
}
SLOT_WEIGHTS = [0.40, 0.35, 0.25]

MAX_STRATEGY_DRAWDOWN_PCT = 5.0
MAX_POSITIONS_PER_STRATEGY = 2
MAX_OPEN_RISK_PCT = 3.0
MAX_DAILY_LOSS_PCT = 3.0
MAX_PORTFOLIO_DRAWDOWN_PCT = 15.0
MAX_SECTOR_EXPOSURE_PCT = 30.0
MAX_CORRELATED_POSITIONS = 2


def _position_strategy_map(db: Session, user_id: str) -> dict[str, str]:
    rows = (
        db.query(PositionLedgerEvent)
        .join(PaperPosition, PaperPosition.id == PositionLedgerEvent.position_id)
        .filter(PaperPosition.user_id == user_id, PositionLedgerEvent.event_type == "trade_open")
        .all()
    )
    mapping: dict[str, str] = {}
    for row in rows:
        payload = row.payload or {}
        strategy_id = str(payload.get("strategy_id") or "spot_pullback_v1")
        mapping[row.position_id] = strategy_id
    return mapping


def _strategy_closed_positions(db: Session, user_id: str) -> list[PaperPosition]:
    return (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.closed_at.is_not(None))
        .order_by(PaperPosition.closed_at.asc())
        .all()
    )


def _strategy_drawdown_stats(db: Session, user_id: str) -> dict[str, dict]:
    mapping = _position_strategy_map(db, user_id)
    closed_rows = _strategy_closed_positions(db, user_id)
    cumulative_by_strategy: dict[str, float] = {}
    peak_by_strategy: dict[str, float] = {}
    drawdown_by_strategy: dict[str, float] = {}
    wins: dict[str, int] = {}
    losses: dict[str, int] = {}
    profit_sum: dict[str, float] = {}
    loss_sum: dict[str, float] = {}

    for row in closed_rows:
        strategy_id = mapping.get(row.id, "spot_pullback_v1")
        pnl = float(row.realized_pnl or 0.0)
        cumulative = cumulative_by_strategy.get(strategy_id, 0.0) + pnl
        cumulative_by_strategy[strategy_id] = cumulative
        peak = max(peak_by_strategy.get(strategy_id, 0.0), cumulative)
        peak_by_strategy[strategy_id] = peak
        drawdown = max(drawdown_by_strategy.get(strategy_id, 0.0), peak - cumulative)
        drawdown_by_strategy[strategy_id] = drawdown
        if pnl >= 0:
            wins[strategy_id] = wins.get(strategy_id, 0) + 1
            profit_sum[strategy_id] = profit_sum.get(strategy_id, 0.0) + pnl
        else:
            losses[strategy_id] = losses.get(strategy_id, 0) + 1
            loss_sum[strategy_id] = loss_sum.get(strategy_id, 0.0) + abs(pnl)

    summary: dict[str, dict] = {}
    for strategy_id in {*(cumulative_by_strategy.keys()), *DEFAULT_CAPITAL_ALLOCATION.keys()}:
        wins_count = wins.get(strategy_id, 0)
        losses_count = losses.get(strategy_id, 0)
        trades = wins_count + losses_count
        pf = (profit_sum.get(strategy_id, 0.0) / loss_sum.get(strategy_id, 1.0)) if losses_count > 0 else (2.0 if wins_count > 0 else 1.0)
        base_capital_reference = 10000.0
        drawdown_pct = (drawdown_by_strategy.get(strategy_id, 0.0) / base_capital_reference) * 100
        summary[strategy_id] = {
            "trades": trades,
            "profit_factor": round(float(pf), 4),
            "drawdown_pct": round(float(drawdown_pct), 4),
            "wins": wins_count,
            "losses": losses_count,
        }
    return summary


def resolve_capital_allocation(db: Session, user_id: str, strategy_id: str) -> dict:
    stats = _strategy_drawdown_stats(db, user_id)
    base = DEFAULT_CAPITAL_ALLOCATION.get(strategy_id, 0.33)
    pf = float((stats.get(strategy_id) or {}).get("profit_factor", 1.0))

    dynamic_shift = 0.0
    if pf > 1.5:
        dynamic_shift = 0.05
    elif pf < 1.0:
        dynamic_shift = -0.05

    effective = min(max(base + dynamic_shift, 0.1), 0.6)
    return {
        "strategy_id": strategy_id,
        "base_allocation": round(base, 4),
        "effective_allocation": round(effective, 4),
        "profit_factor": pf,
        "dynamic_shift": round(dynamic_shift, 4),
    }


def slot_weight_for_rank(selection_rank: int | None) -> float:
    if selection_rank is None or selection_rank <= 0:
        return SLOT_WEIGHTS[0]
    index = min(selection_rank - 1, len(SLOT_WEIGHTS) - 1)
    return SLOT_WEIGHTS[index]


def strategy_open_positions(db: Session, user_id: str) -> tuple[list[PaperPosition], dict[str, list[PaperPosition]]]:
    mapping = _position_strategy_map(db, user_id)
    open_rows = db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.status == "open").all()
    by_strategy: dict[str, list[PaperPosition]] = {}
    for row in open_rows:
        strategy_id = mapping.get(row.id, "spot_pullback_v1")
        by_strategy.setdefault(strategy_id, []).append(row)
    return open_rows, by_strategy


def compute_open_risk_pct(equity: float, open_positions: list[PaperPosition]) -> float:
    if equity <= 0:
        return 0.0
    open_risk = 0.0
    for position in open_positions:
        risk_unit = abs(float(position.entry_price) - float(position.stop_loss))
        open_risk += risk_unit * float(position.quantity)
    return (open_risk / equity) * 100


def portfolio_drawdown_pct(db: Session, user_id: str, equity: float) -> float:
    closed_rows = _strategy_closed_positions(db, user_id)
    if not closed_rows:
        return 0.0
    base_capital = 10000.0
    realized = sum(float(row.realized_pnl or 0.0) for row in closed_rows)
    peak_equity = max(base_capital, base_capital + max(realized, 0.0))
    current_equity = max(equity, 0.0)
    if peak_equity <= 0:
        return 0.0
    return max(((peak_equity - current_equity) / peak_equity) * 100, 0.0)


def sector_exposure_pct(db: Session, open_positions: list[PaperPosition], symbol: str, equity: float) -> float:
    if equity <= 0:
        return 0.0
    groups = db.query(RiskExposureGroup).all()
    target_group_symbols: set[str] = set()
    symbol_upper = symbol.upper()
    for group in groups:
        members = {item.upper() for item in (group.symbols or [])}
        if symbol_upper in members:
            target_group_symbols = members
            break

    if not target_group_symbols:
        return 0.0

    notional = 0.0
    for position in open_positions:
        if position.symbol.upper() in target_group_symbols:
            notional += float(position.entry_price) * float(position.quantity)
    return (notional / equity) * 100


def correlated_positions_count(cache, open_positions: list[PaperPosition], symbol: str, side: str) -> int:
    count = 0
    for row in open_positions:
        if row.side != side:
            continue
        corr = abs(pair_correlation(cache, symbol, row.symbol, window=200))
        if corr >= 0.8:
            count += 1
    return count


def risk_capital_snapshot(db: Session, cache, user_id: str) -> dict:
    ticker = (cache.get("market:ticker:BTCUSDT") or {}) if hasattr(cache, "get") else {}
    if isinstance(ticker, (bytes, str)):
        ticker = {}
    market_price = float((ticker or {}).get("last_price", 100.0))
    sizing = compute_position_sizing(db, user_id, market_price)
    equity = float(sizing["equity"])

    open_positions, by_strategy = strategy_open_positions(db, user_id)
    open_risk = compute_open_risk_pct(equity, open_positions)
    daily_loss = daily_loss_usage(db, user_id)
    drawdown_pct = portfolio_drawdown_pct(db, user_id, equity)
    stats = _strategy_drawdown_stats(db, user_id)

    return {
        "equity": round(equity, 4),
        "open_positions": len(open_positions),
        "open_risk_pct": round(open_risk, 4),
        "daily_loss": daily_loss,
        "portfolio_drawdown_pct": round(drawdown_pct, 4),
        "strategy_drawdown": {key: value.get("drawdown_pct", 0) for key, value in stats.items()},
        "strategy_open_positions": {key: len(value) for key, value in by_strategy.items()},
        "allocation": {
            strategy_id: resolve_capital_allocation(db, user_id, strategy_id)
            for strategy_id in DEFAULT_CAPITAL_ALLOCATION
        },
        "limits": {
            "max_open_risk_pct": MAX_OPEN_RISK_PCT,
            "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
            "max_portfolio_drawdown_pct": MAX_PORTFOLIO_DRAWDOWN_PCT,
            "max_strategy_drawdown_pct": MAX_STRATEGY_DRAWDOWN_PCT,
            "max_positions_per_strategy": MAX_POSITIONS_PER_STRATEGY,
            "max_sector_exposure_pct": MAX_SECTOR_EXPOSURE_PCT,
            "max_correlated_positions": MAX_CORRELATED_POSITIONS,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
