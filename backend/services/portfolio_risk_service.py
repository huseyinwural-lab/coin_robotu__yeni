import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from models import BotProfile, PaperPosition, PortfolioExposureSnapshot, RiskCluster, UserRiskSetting

LIMITS_PATH = Path("/app/config/portfolio_risk_limits.json")

DEFAULT_LIMITS = {
    "max_portfolio_leverage": 3.0,
    "max_symbol_exposure": 35.0,
    "max_cluster_exposure": 50.0,
    "max_strategy_exposure": 40.0,
    "max_single_trade_risk": 10.0,
    "max_intraday_drawdown": 5.0,
    "max_total_drawdown": 15.0,
}

DEFAULT_CLUSTERS = [
    {
        "cluster_id": "L1",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "cluster_type": "crypto_market_beta",
        "correlation_score": 0.82,
        "risk_weight": 1.0,
    },
    {
        "cluster_id": "L2",
        "symbols": ["SOLUSDT", "AVAXUSDT", "LINKUSDT"],
        "cluster_type": "high_beta_alts",
        "correlation_score": 0.76,
        "risk_weight": 1.15,
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def load_portfolio_risk_limits() -> dict:
    if not LIMITS_PATH.exists():
        return dict(DEFAULT_LIMITS)
    try:
        payload = json.loads(LIMITS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_LIMITS)

    raw_limits = payload.get("limits") if isinstance(payload, dict) else {}
    merged = dict(DEFAULT_LIMITS)
    for key in merged:
        merged[key] = _safe_float(raw_limits.get(key), merged[key])
    return merged


def save_portfolio_risk_limits(payload: dict) -> dict:
    current = load_portfolio_risk_limits()
    for key in DEFAULT_LIMITS:
        if key in payload:
            current[key] = _safe_float(payload.get(key), current[key])

    LIMITS_PATH.write_text(
        json.dumps({"version": "portfolio_risk_limits_v1", "limits": current}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def seed_default_risk_clusters(db: Session) -> None:
    count = db.query(RiskCluster).count()
    if count > 0:
        return
    for item in DEFAULT_CLUSTERS:
        db.add(
            RiskCluster(
                cluster_id=item["cluster_id"],
                symbols=item["symbols"],
                cluster_type=item["cluster_type"],
                correlation_score=item["correlation_score"],
                risk_weight=item["risk_weight"],
            )
        )
    db.flush()


def list_risk_clusters(db: Session) -> list[RiskCluster]:
    seed_default_risk_clusters(db)
    return db.query(RiskCluster).order_by(RiskCluster.cluster_id.asc()).all()


def upsert_risk_cluster(db: Session, payload: dict) -> RiskCluster:
    cluster_id = str(payload.get("cluster_id") or "").strip().upper()
    if not cluster_id:
        raise ValueError("cluster_id_required")

    row = db.query(RiskCluster).filter(RiskCluster.cluster_id == cluster_id).first()
    if row is None:
        row = RiskCluster(cluster_id=cluster_id)
        db.add(row)

    row.symbols = [str(item).upper() for item in (payload.get("symbols") or []) if str(item).strip()]
    row.cluster_type = str(payload.get("cluster_type") or row.cluster_type or "custom")
    row.correlation_score = _safe_float(payload.get("correlation_score"), row.correlation_score or 0)
    row.risk_weight = max(_safe_float(payload.get("risk_weight"), row.risk_weight or 1), 0.1)
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def _resolve_cluster_id(symbol: str, clusters: list[RiskCluster]) -> str:
    symbol_upper = str(symbol or "").upper()
    for cluster in clusters:
        if symbol_upper in {str(item).upper() for item in (cluster.symbols or [])}:
            return cluster.cluster_id
    return "UNCLUSTERED"


def build_current_positions(db: Session, user_id: str) -> list[dict]:
    bot_map = {
        row.id: row.strategy_type
        for row in db.query(BotProfile).filter(BotProfile.user_id == user_id).all()
    }
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .all()
    )
    items: list[dict] = []
    for row in rows:
        notional = abs(_safe_float(row.quantity) * _safe_float(row.entry_price) * max(int(row.leverage or 1), 1))
        items.append(
            {
                "symbol": str(row.symbol).upper(),
                "notional": notional,
                "strategy_id": bot_map.get(row.bot_profile_id) or "unknown_strategy",
                "position_size": _safe_float(row.quantity),
            }
        )
    return items


def build_portfolio_state(db: Session, user_id: str) -> dict:
    risk_row = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
    base_capital = _safe_float(risk_row.base_capital if risk_row else 10000, 10000)

    open_rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .all()
    )
    closed_rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status != "open")
        .all()
    )
    realized_total = sum(_safe_float(row.realized_pnl) for row in closed_rows)
    unrealized_total = sum(_safe_float(row.unrealized_pnl) for row in open_rows)
    current_capital = max(base_capital + realized_total + unrealized_total, 1)
    intraday_loss = sum(
        abs(_safe_float(row.realized_pnl))
        for row in closed_rows
        if row.closed_at and row.closed_at.date() == _now().date() and _safe_float(row.realized_pnl) < 0
    )

    total_drawdown_pct = round(max(0.0, (-realized_total / base_capital) * 100), 4) if base_capital else 0.0
    intraday_drawdown_pct = round((intraday_loss / base_capital) * 100, 4) if base_capital else 0.0
    return {
        "base_capital": base_capital,
        "current_capital": current_capital,
        "intraday_drawdown_pct": intraday_drawdown_pct,
        "total_drawdown_pct": total_drawdown_pct,
    }


def snapshot_portfolio_exposure(
    db: Session,
    *,
    user_id: str,
    positions: list[dict],
    strategy_id: str,
    clusters: list[RiskCluster],
    portfolio_equity: float,
    projected_intent: dict | None = None,
) -> None:
    timestamp = _now()
    for position in positions:
        symbol = str(position.get("symbol") or "").upper()
        notional = _safe_float(position.get("notional"), 0)
        db.add(
            PortfolioExposureSnapshot(
                id=str(uuid.uuid4()),
                timestamp=timestamp,
                user_id=user_id,
                symbol=symbol,
                position_size=_safe_float(position.get("position_size"), 0),
                notional=notional,
                strategy_id=str(position.get("strategy_id") or "unknown_strategy"),
                cluster_id=_resolve_cluster_id(symbol, clusters),
                exposure_weight=round((notional / max(portfolio_equity, 1)) * 100, 4),
            )
        )

    if projected_intent is None:
        return

    projected_symbol = str(projected_intent.get("symbol") or "").upper()
    projected_notional = _safe_float(projected_intent.get("notional"), 0)
    db.add(
        PortfolioExposureSnapshot(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            user_id=user_id,
            symbol=projected_symbol,
            position_size=_safe_float(projected_intent.get("position_size"), 0),
            notional=projected_notional,
            strategy_id=str(strategy_id or "unknown_strategy"),
            cluster_id=_resolve_cluster_id(projected_symbol, clusters),
            exposure_weight=round((projected_notional / max(portfolio_equity, 1)) * 100, 4),
        )
    )


def evaluate_portfolio_risk(
    *,
    execution_intent: dict,
    current_positions: list[dict],
    portfolio_state: dict,
    strategy_context: dict,
    market_state: dict,
    limits: dict,
    clusters: list[RiskCluster],
) -> dict:
    symbol = str(execution_intent.get("symbol") or "").upper()
    requested_notional = max(_safe_float(execution_intent.get("notional"), 0), 0)
    strategy_id = str(strategy_context.get("strategy_id") or "unknown_strategy")
    equity = max(_safe_float(portfolio_state.get("current_capital"), 10000), 1)

    current_total_notional = sum(max(_safe_float(item.get("notional"), 0), 0) for item in current_positions)
    symbol_current_notional = sum(
        max(_safe_float(item.get("notional"), 0), 0)
        for item in current_positions
        if str(item.get("symbol") or "").upper() == symbol
    )
    strategy_current_notional = sum(
        max(_safe_float(item.get("notional"), 0), 0)
        for item in current_positions
        if str(item.get("strategy_id") or "") == strategy_id
    )

    cluster_id = _resolve_cluster_id(symbol, clusters)
    cluster_symbols: set[str] = set()
    cluster_weight = 1.0
    for cluster in clusters:
        if cluster.cluster_id == cluster_id:
            cluster_symbols = {str(item).upper() for item in (cluster.symbols or [])}
            cluster_weight = _safe_float(cluster.risk_weight, 1.0)
            break

    cluster_current_notional = sum(
        max(_safe_float(item.get("notional"), 0), 0)
        for item in current_positions
        if str(item.get("symbol") or "").upper() in cluster_symbols
    )

    projected_total_notional = current_total_notional + requested_notional
    projected_symbol_notional = symbol_current_notional + requested_notional
    projected_strategy_notional = strategy_current_notional + requested_notional
    projected_cluster_notional = cluster_current_notional + requested_notional

    current_portfolio_leverage = round(projected_total_notional / equity, 6)
    symbol_exposure_pct = round((projected_symbol_notional / equity) * 100, 4)
    strategy_exposure_pct = round((projected_strategy_notional / equity) * 100, 4)
    cluster_exposure_pct = round(((projected_cluster_notional / equity) * 100) * max(cluster_weight, 0.1), 4)
    single_trade_risk_pct = round((requested_notional / equity) * 100, 4)
    intraday_drawdown_pct = _safe_float(portfolio_state.get("intraday_drawdown_pct"), 0)
    total_drawdown_pct = _safe_float(portfolio_state.get("total_drawdown_pct"), 0)

    risk_flags: list[str] = []
    normalized_ratios: list[float] = []

    def _check_ratio(current_value: float, max_value: float, code: str):
        limit = max(_safe_float(max_value, 0.0001), 0.0001)
        ratio = max(current_value / limit, 0)
        normalized_ratios.append(ratio)
        if ratio > 1:
            risk_flags.append(code)

    _check_ratio(current_portfolio_leverage, limits.get("max_portfolio_leverage"), "max_portfolio_leverage_breach")
    _check_ratio(symbol_exposure_pct, limits.get("max_symbol_exposure"), "max_symbol_exposure_breach")
    _check_ratio(cluster_exposure_pct, limits.get("max_cluster_exposure"), "max_cluster_exposure_breach")
    _check_ratio(strategy_exposure_pct, limits.get("max_strategy_exposure"), "max_strategy_exposure_breach")
    _check_ratio(single_trade_risk_pct, limits.get("max_single_trade_risk"), "max_single_trade_risk_breach")
    _check_ratio(intraday_drawdown_pct, limits.get("max_intraday_drawdown"), "max_intraday_drawdown_breach")
    _check_ratio(total_drawdown_pct, limits.get("max_total_drawdown"), "max_total_drawdown_breach")

    market_volatility = _safe_float(market_state.get("volatility_pct"), 0)
    if market_volatility >= 7:
        risk_flags.append("high_market_volatility")
        normalized_ratios.append(1.2)

    risk_score = round(min(1.0, (sum(normalized_ratios) / max(len(normalized_ratios), 1)) / 1.5), 4)

    approval_required = False
    position_adjustment = {
        "applied": False,
        "requested_notional": round(requested_notional, 4),
        "adjusted_notional": round(requested_notional, 4),
        "adjustment_factor": 1.0,
    }
    decision = "ALLOW"

    hard_reject_flags = {
        "max_intraday_drawdown_breach",
        "max_total_drawdown_breach",
    }
    if any(flag in hard_reject_flags for flag in risk_flags):
        decision = "REJECT"
    elif any("breach" in flag for flag in risk_flags):
        if risk_score >= 0.85:
            decision = "REJECT"
        else:
            decision = "REQUIRE_APPROVAL"
            approval_required = True
    elif risk_score >= 0.65:
        decision = "ADJUST_POSITION"
        adjustment_factor = 0.65
        adjusted_notional = round(requested_notional * adjustment_factor, 4)
        position_adjustment = {
            "applied": True,
            "requested_notional": round(requested_notional, 4),
            "adjusted_notional": adjusted_notional,
            "adjustment_factor": adjustment_factor,
        }
    elif risk_score >= 0.45:
        approval_required = True
        decision = "REQUIRE_APPROVAL"

    return {
        "risk_score": risk_score,
        "risk_flags": sorted(set(risk_flags)),
        "approval_required": approval_required,
        "position_adjustment": position_adjustment,
        "decision": decision,
        "cluster_id": cluster_id,
        "current_portfolio_leverage": round(current_portfolio_leverage, 6),
        "symbol_exposure_pct": symbol_exposure_pct,
        "cluster_exposure_pct": cluster_exposure_pct,
        "strategy_exposure_pct": strategy_exposure_pct,
        "single_trade_risk_pct": single_trade_risk_pct,
        "portfolio_state": {
            "intraday_drawdown_pct": intraday_drawdown_pct,
            "total_drawdown_pct": total_drawdown_pct,
        },
    }


def portfolio_risk_check(
    db: Session,
    *,
    user_id: str,
    execution_intent: dict,
    strategy_context: dict,
    market_state: dict,
) -> dict:
    limits = load_portfolio_risk_limits()
    clusters = list_risk_clusters(db)
    current_positions = build_current_positions(db, user_id)
    portfolio_state = build_portfolio_state(db, user_id)

    result = evaluate_portfolio_risk(
        execution_intent=execution_intent,
        current_positions=current_positions,
        portfolio_state=portfolio_state,
        strategy_context=strategy_context,
        market_state=market_state,
        limits=limits,
        clusters=clusters,
    )

    snapshot_portfolio_exposure(
        db,
        user_id=user_id,
        positions=current_positions,
        strategy_id=strategy_context.get("strategy_id") or "unknown_strategy",
        clusters=clusters,
        portfolio_equity=max(_safe_float(portfolio_state.get("current_capital"), 1), 1),
        projected_intent={
            "symbol": execution_intent.get("symbol"),
            "notional": execution_intent.get("notional"),
            "position_size": execution_intent.get("position_size", 0),
        },
    )

    return {
        **result,
        "limits": limits,
        "portfolio_state": {
            **portfolio_state,
            **result.get("portfolio_state", {}),
        },
    }
