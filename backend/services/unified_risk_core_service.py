from __future__ import annotations

import json
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models import PaperPosition, UserExecutionIntent, UserRiskSetting
from services.audit_service import create_audit_log


RISK_SNAPSHOT_DIR = Path("/app/artifacts/risk_snapshots")
RISK_SNAPSHOT_MANIFEST = Path("/app/artifacts/manifests/unified_risk_snapshots.jsonl")

RULESETS: dict[str, dict[str, Any]] = {
    "binance": {
        "name": "binance",
        "maintenance_margin_base": 0.005,
        "fee_buffer_pct": 0.0006,
        "safety_haircut_pct": 0.02,
        "warn_liquidation_buffer_pct": 8.0,
        "critical_liquidation_buffer_pct": 3.0,
        "max_leverage": 125,
        "symbol_rules": {
            "BTCUSDT": {
                "max_leverage": 125,
                "collateral_haircut": 0.98,
                "margin_tiers": [
                    {"max_notional": 50000, "maintenance_margin_rate": 0.0045},
                    {"max_notional": 250000, "maintenance_margin_rate": 0.005},
                    {"max_notional": 1000000, "maintenance_margin_rate": 0.0075},
                    {"max_notional": 999999999, "maintenance_margin_rate": 0.01},
                ],
            },
            "ETHUSDT": {
                "max_leverage": 100,
                "collateral_haircut": 0.975,
                "margin_tiers": [
                    {"max_notional": 30000, "maintenance_margin_rate": 0.005},
                    {"max_notional": 150000, "maintenance_margin_rate": 0.006},
                    {"max_notional": 800000, "maintenance_margin_rate": 0.009},
                    {"max_notional": 999999999, "maintenance_margin_rate": 0.012},
                ],
            },
        },
    },
    "bybit": {
        "name": "bybit",
        "maintenance_margin_base": 0.0055,
        "fee_buffer_pct": 0.0007,
        "safety_haircut_pct": 0.022,
        "warn_liquidation_buffer_pct": 7.5,
        "critical_liquidation_buffer_pct": 2.8,
        "max_leverage": 100,
        "symbol_rules": {
            "BTCUSDT": {
                "max_leverage": 100,
                "collateral_haircut": 0.975,
                "margin_tiers": [
                    {"max_notional": 40000, "maintenance_margin_rate": 0.005},
                    {"max_notional": 200000, "maintenance_margin_rate": 0.006},
                    {"max_notional": 900000, "maintenance_margin_rate": 0.0085},
                    {"max_notional": 999999999, "maintenance_margin_rate": 0.0115},
                ],
            },
            "ETHUSDT": {
                "max_leverage": 80,
                "collateral_haircut": 0.97,
                "margin_tiers": [
                    {"max_notional": 25000, "maintenance_margin_rate": 0.0055},
                    {"max_notional": 120000, "maintenance_margin_rate": 0.0065},
                    {"max_notional": 600000, "maintenance_margin_rate": 0.0095},
                    {"max_notional": 999999999, "maintenance_margin_rate": 0.013},
                ],
            },
        },
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    ts = value or _now()
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_rulesets() -> dict:
    return {
        "default": "binance",
        "available": list(RULESETS.keys()),
        "rulesets": RULESETS,
    }


def _get_ruleset(ruleset: str | None) -> dict:
    normalized = str(ruleset or "binance").strip().lower()
    return RULESETS.get(normalized, RULESETS["binance"])


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _read_execution_manifest_prices(limit: int = 500) -> list[float]:
    manifest = Path("/app/artifacts/manifests/execution_safety_gate_manifest.jsonl")
    if not manifest.exists():
        return []
    prices: list[float] = []
    try:
        with manifest.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                payload = row.get("payload") or {}
                market = payload.get("market") or {}
                mark_price = _safe_float(market.get("mark_price"), 0.0)
                if mark_price > 0:
                    prices.append(mark_price)
    except Exception:
        return []
    return prices[-limit:]


def _returns(prices: list[float]) -> list[float]:
    output: list[float] = []
    for idx in range(1, len(prices)):
        prev = prices[idx - 1]
        curr = prices[idx]
        if prev <= 0:
            continue
        output.append((curr - prev) / prev)
    return output


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * q))))
    return ordered[pos]


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3 or len(y) < 3:
        return 0.0
    size = min(len(x), len(y))
    x = x[-size:]
    y = y[-size:]
    mx = sum(x) / size
    my = sum(y) / size
    numerator = sum((x[idx] - mx) * (y[idx] - my) for idx in range(size))
    denom_x = sum((value - mx) ** 2 for value in x)
    denom_y = sum((value - my) ** 2 for value in y)
    if denom_x <= 0 or denom_y <= 0:
        return 0.0
    return max(min(numerator / ((denom_x ** 0.5) * (denom_y ** 0.5)), 1.0), -1.0)


def _symbol_base(symbol: str) -> str:
    value = str(symbol or "").upper()
    return value[:-4] if value.endswith("USDT") else value


def _sector_group(symbol: str) -> str:
    base = _symbol_base(symbol)
    if base in {"BTC", "ETH"}:
        return "majors"
    if base in {"SOL", "AVAX", "ARB", "OP", "MATIC"}:
        return "alts_l1_l2"
    if base in {"LINK", "UNI", "AAVE"}:
        return "defi_beta"
    return "others"


def _resolve_symbol_rule(ruleset: dict, symbol: str, notional: float) -> dict:
    symbol_rules = dict(ruleset.get("symbol_rules") or {})
    default_rule = {
        "max_leverage": int(ruleset.get("max_leverage") or 50),
        "collateral_haircut": 1.0 - float(ruleset.get("safety_haircut_pct") or 0.02),
        "margin_tiers": [
            {"max_notional": 50000, "maintenance_margin_rate": float(ruleset.get("maintenance_margin_base") or 0.005)},
            {"max_notional": 999999999, "maintenance_margin_rate": float(ruleset.get("maintenance_margin_base") or 0.005) * 1.4},
        ],
    }
    rule = dict(symbol_rules.get(str(symbol).upper()) or default_rule)
    tiers = list(rule.get("margin_tiers") or default_rule["margin_tiers"])
    selected_rate = float(ruleset.get("maintenance_margin_base") or 0.005)
    for tier in tiers:
        if notional <= float(tier.get("max_notional") or 0):
            selected_rate = float(tier.get("maintenance_margin_rate") or selected_rate)
            break
    return {
        "max_leverage": max(_safe_int(rule.get("max_leverage"), int(ruleset.get("max_leverage") or 50)), 1),
        "collateral_haircut": max(min(_safe_float(rule.get("collateral_haircut"), 0.98), 1.0), 0.8),
        "maintenance_margin_rate": max(selected_rate, 0.001),
    }


def _strategy_breach_history_from_manifest(strategy_id: str, lookback: int = 200) -> int:
    if not RISK_SNAPSHOT_MANIFEST.exists():
        return 0
    count = 0
    rows = 0
    with RISK_SNAPSHOT_MANIFEST.open("r", encoding="utf-8") as handle:
        for raw in reversed(handle.readlines()):
            if rows >= lookback:
                break
            rows += 1
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            artifact_path = Path(str(row.get("artifact_path") or ""))
            if not artifact_path.exists():
                continue
            try:
                artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            strategy_rows = (
                ((artifact_payload.get("payload") or {}).get("capital") or {}).get("strategy_allocation")
                or []
            )
            matched = [item for item in strategy_rows if str(item.get("strategy_id") or "") == strategy_id and bool(item.get("breach"))]
            if matched:
                count += 1
    return count


def _default_position_from_input(raw: dict, mark_price_fallback: float) -> dict:
    symbol = str(raw.get("symbol") or "BTCUSDT").upper()
    side = str(raw.get("side") or "LONG").upper()
    quantity = max(_safe_float(raw.get("quantity"), 0.0), 0.0)
    entry_price = max(_safe_float(raw.get("entry_price"), mark_price_fallback or 0.0), 0.0001)
    mark_price = max(_safe_float(raw.get("mark_price"), entry_price), 0.0001)
    leverage = max(_safe_int(raw.get("leverage"), 1), 1)
    margin_mode = str(raw.get("margin_mode") or "cross").lower()
    strategy_id = str(raw.get("strategy_id") or "default")
    isolated_margin = _safe_float(raw.get("isolated_margin"), 0.0)
    return {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry_price": entry_price,
        "mark_price": mark_price,
        "leverage": leverage,
        "margin_mode": margin_mode,
        "strategy_id": strategy_id,
        "isolated_margin": isolated_margin,
    }


def _load_positions(db: Session | None, user_id: str, input_state: dict | None, mark_price_fallback: float) -> list[dict]:
    provided_positions = list((input_state or {}).get("positions") or [])
    if provided_positions:
        return [_default_position_from_input(row, mark_price_fallback) for row in provided_positions]

    if db is None:
        return []

    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.user_id == user_id, PaperPosition.status == "open")
        .all()
    )
    positions: list[dict] = []
    for row in rows:
        side = str(row.side or "LONG").upper()
        mark_price = max(_safe_float(row.entry_price, mark_price_fallback), 0.0001)
        positions.append(
            {
                "symbol": str(row.symbol or "BTCUSDT").upper(),
                "side": "LONG" if side in {"BUY", "LONG"} else "SHORT",
                "quantity": max(_safe_float(row.quantity, 0.0), 0.0),
                "entry_price": max(_safe_float(row.entry_price, mark_price), 0.0001),
                "mark_price": mark_price,
                "leverage": max(_safe_int(row.leverage, 1), 1),
                "margin_mode": "cross",
                "strategy_id": "default",
                "isolated_margin": 0.0,
            }
        )
    return positions


def _resolve_account_state(db: Session | None, user_id: str, input_state: dict | None) -> dict:
    account = dict((input_state or {}).get("account") or {})
    if db is not None and not account:
        settings = db.query(UserRiskSetting).filter(UserRiskSetting.user_id == user_id).first()
        if settings:
            account = {
                "equity": _safe_float(settings.base_capital, 10000.0),
                "free_collateral": _safe_float(settings.base_capital, 10000.0),
                "used_margin": 0.0,
                "portfolio_id": str(settings.id),
            }

    equity = max(_safe_float(account.get("equity"), 10000.0), 1.0)
    used_margin = max(_safe_float(account.get("used_margin"), 0.0), 0.0)
    free_collateral = _safe_float(account.get("free_collateral"), equity - used_margin)
    free_collateral = max(free_collateral, 0.0)
    return {
        "equity": round(equity, 6),
        "used_margin": round(used_margin, 6),
        "free_collateral": round(free_collateral, 6),
        "portfolio_id": str(account.get("portfolio_id") or "simulated-portfolio"),
    }


def _compute_liquidation(position: dict, *, cross_collateral_share: float, ruleset: dict) -> dict:
    quantity = max(_safe_float(position.get("quantity"), 0.0), 0.0)
    mark_price = max(_safe_float(position.get("mark_price"), 0.0001), 0.0001)
    entry_price = max(_safe_float(position.get("entry_price"), mark_price), 0.0001)
    leverage = max(_safe_int(position.get("leverage"), 1), 1)
    side = str(position.get("side") or "LONG").upper()
    notional = max(abs(quantity * mark_price), 0.0001)

    symbol_rule = _resolve_symbol_rule(ruleset, str(position.get("symbol") or ""), notional)
    capped_leverage = min(leverage, int(symbol_rule.get("max_leverage") or leverage))
    maintenance_rate = float(symbol_rule.get("maintenance_margin_rate") or ruleset.get("maintenance_margin_base", 0.005))
    maintenance_margin = notional * maintenance_rate
    initial_margin = notional / max(capped_leverage, 1)

    pnl_direction = 1.0 if side == "LONG" else -1.0
    unrealized_pnl = (mark_price - entry_price) * quantity * pnl_direction
    fee_buffer = notional * float(ruleset.get("fee_buffer_pct", 0.0006))
    safety_haircut = initial_margin * float(ruleset.get("safety_haircut_pct", 0.02))

    margin_mode = str(position.get("margin_mode") or "cross").lower()
    isolated_margin = max(_safe_float(position.get("isolated_margin"), 0.0), 0.0)
    collateral = isolated_margin if margin_mode == "isolated" and isolated_margin > 0 else cross_collateral_share
    collateral = max(collateral, initial_margin)
    usable_collateral = collateral * float(symbol_rule.get("collateral_haircut") or 0.98)

    effective_margin = usable_collateral + unrealized_pnl - fee_buffer - safety_haircut
    margin_ratio = (effective_margin / maintenance_margin) if maintenance_margin > 0 else 999.0

    distance_price = (effective_margin - maintenance_margin) / max(quantity, 0.0001)
    if side == "LONG":
        liquidation_price = mark_price - distance_price
    else:
        liquidation_price = mark_price + distance_price
    liquidation_price = max(liquidation_price, 0.0001)

    liquidation_buffer_pct = abs((mark_price - liquidation_price) / mark_price) * 100 if mark_price > 0 else 0.0

    return {
        "symbol": position.get("symbol"),
        "side": side,
        "margin_mode": margin_mode,
        "leverage": leverage,
        "effective_leverage": capped_leverage,
        "entry_price": round(entry_price, 6),
        "mark_price": round(mark_price, 6),
        "quantity": round(quantity, 6),
        "notional": round(notional, 6),
        "initial_margin": round(initial_margin, 6),
        "maintenance_margin": round(maintenance_margin, 6),
        "maintenance_margin_rate": round(maintenance_rate, 6),
        "collateral_haircut": round(float(symbol_rule.get("collateral_haircut") or 0.98), 6),
        "unrealized_pnl": round(unrealized_pnl, 6),
        "margin_ratio": round(margin_ratio, 6),
        "liquidation_price": round(liquidation_price, 6),
        "liquidation_buffer_pct": round(liquidation_buffer_pct, 6),
    }


def _portfolio_metrics(positions: list[dict], liquidation_rows: list[dict], equity: float) -> dict:
    long_notional = sum(item["notional"] for item in liquidation_rows if item["side"] == "LONG")
    short_notional = sum(item["notional"] for item in liquidation_rows if item["side"] == "SHORT")
    gross_exposure = long_notional + short_notional
    net_exposure = long_notional - short_notional
    hedged_notional = min(long_notional, short_notional)
    effective_leverage = gross_exposure / max(equity, 1.0)

    symbol_map: dict[str, float] = {}
    strategy_map: dict[str, float] = {}
    for item in liquidation_rows:
        symbol = str(item.get("symbol") or "UNKNOWN")
        symbol_map[symbol] = symbol_map.get(symbol, 0.0) + float(item.get("notional") or 0.0)

    for row in positions:
        strategy = str(row.get("strategy_id") or "default")
        row_notional = abs(_safe_float(row.get("quantity"), 0.0) * _safe_float(row.get("mark_price"), 0.0))
        strategy_map[strategy] = strategy_map.get(strategy, 0.0) + row_notional

    return {
        "gross_exposure": round(gross_exposure, 6),
        "net_exposure": round(net_exposure, 6),
        "directional_exposure": {
            "long": round(long_notional, 6),
            "short": round(short_notional, 6),
            "hedged_notional": round(hedged_notional, 6),
            "hedged_ratio": round((hedged_notional / gross_exposure) if gross_exposure > 0 else 0.0, 6),
        },
        "effective_leverage": round(effective_leverage, 6),
        "symbol_exposure": [
            {"symbol": key, "notional": round(value, 6)}
            for key, value in sorted(symbol_map.items(), key=lambda item: item[1], reverse=True)
        ],
        "strategy_exposure": [
            {"strategy_id": key, "notional": round(value, 6)}
            for key, value in sorted(strategy_map.items(), key=lambda item: item[1], reverse=True)
        ],
    }


def _capital_governance(account: dict, portfolio: dict, liquidation_rows: list[dict], input_state: dict | None) -> dict:
    equity = max(float(account.get("equity") or 1.0), 1.0)
    used_margin = sum(float(item.get("initial_margin") or 0.0) for item in liquidation_rows)
    free_collateral = max(equity - used_margin, 0.0)
    margin_usage_pct = (used_margin / equity) * 100

    strategy_budgets = dict((input_state or {}).get("strategy_risk_budgets") or {})
    strategy_rows: list[dict] = []
    for row in portfolio.get("strategy_exposure") or []:
        strategy_id = str(row.get("strategy_id") or "default")
        exposure = float(row.get("notional") or 0.0)
        capital_share = (exposure / equity) * 100
        configured_budget = _safe_float(strategy_budgets.get(strategy_id), 25.0)
        breach = capital_share > configured_budget
        strategy_rows.append(
            {
                "strategy_id": strategy_id,
                "capital_share_pct": round(capital_share, 6),
                "risk_budget_pct": round(configured_budget, 6),
                "breach": breach,
            }
        )

    return {
        "equity": round(equity, 6),
        "used_margin": round(used_margin, 6),
        "free_collateral": round(free_collateral, 6),
        "margin_usage_pct": round(margin_usage_pct, 6),
        "strategy_allocation": strategy_rows,
        "risk_budget_breach_count": len([row for row in strategy_rows if row.get("breach")]),
    }


def _build_symbol_series(positions: list[dict], replay_prices: list[float], input_state: dict | None) -> dict[str, list[float]]:
    base_prices = replay_prices[-240:] if replay_prices else [100.0 + idx * 0.2 for idx in range(240)]
    base_returns = _returns(base_prices)
    series: dict[str, list[float]] = {}
    provided = dict((input_state or {}).get("symbol_price_series") or {})

    for idx, position in enumerate(positions):
        symbol = str(position.get("symbol") or "UNKNOWN").upper()
        if symbol in provided and isinstance(provided[symbol], list) and len(provided[symbol]) >= 30:
            series[symbol] = [max(_safe_float(item, 0.0), 0.0001) for item in provided[symbol][-240:]]
            continue

        seed_price = max(_safe_float(position.get("mark_price"), 100.0), 0.0001)
        symbol_returns = [
            float(ret) * max(0.4, 1 - (idx * 0.08))
            for ret in base_returns
        ]
        prices = [seed_price]
        for ret in symbol_returns[-180:]:
            prices.append(max(prices[-1] * (1 + ret), 0.0001))
        series[symbol] = prices[-180:]
    return series


def _build_cluster_risk(positions: list[dict], series: dict[str, list[float]], gross_exposure: float, input_state: dict | None) -> dict:
    windows = [30, 60, 120]
    symbols = sorted(set(series.keys()))
    matrix_by_window: dict[str, dict[str, float]] = {}
    for window in windows:
        matrix: dict[str, float] = {}
        for left_idx, left in enumerate(symbols):
            left_returns = _returns(series.get(left, [])[-(window + 1) :])
            for right in symbols[left_idx + 1 :]:
                right_returns = _returns(series.get(right, [])[-(window + 1) :])
                key = f"{left}:{right}"
                matrix[key] = round(_pearson(left_returns, right_returns), 6)
        matrix_by_window[str(window)] = matrix

    cluster_map: dict[str, dict] = {}
    symbol_notional = {
        str(item.get("symbol") or "UNKNOWN").upper(): abs(_safe_float(item.get("quantity"), 0.0) * _safe_float(item.get("mark_price"), 0.0))
        for item in positions
    }
    direction_map: dict[str, float] = {}
    for item in positions:
        symbol = str(item.get("symbol") or "UNKNOWN").upper()
        direction_sign = 1 if str(item.get("side") or "LONG").upper() == "LONG" else -1
        direction_map[symbol] = direction_map.get(symbol, 0.0) + direction_sign * symbol_notional.get(symbol, 0.0)

    matrix_120 = matrix_by_window.get("120", {})
    for symbol in symbols:
        base_cluster = _symbol_base(symbol)
        sector_cluster = _sector_group(symbol)
        for cluster_id in [f"base:{base_cluster}", f"sector:{sector_cluster}"]:
            bucket = cluster_map.setdefault(cluster_id, {"symbols": set(), "exposure": 0.0, "directional": 0.0, "corr_weights": []})
            bucket["symbols"].add(symbol)
            bucket["exposure"] += symbol_notional.get(symbol, 0.0)
            bucket["directional"] += direction_map.get(symbol, 0.0)

    for cluster_id, payload in cluster_map.items():
        cluster_symbols = sorted(payload["symbols"])
        for left_idx, left in enumerate(cluster_symbols):
            for right in cluster_symbols[left_idx + 1 :]:
                pair_key = f"{left}:{right}"
                reverse_key = f"{right}:{left}"
                corr = matrix_120.get(pair_key, matrix_120.get(reverse_key, 0.0))
                payload["corr_weights"].append(abs(corr))

    clusters = []
    for cluster_id, payload in cluster_map.items():
        exposure = float(payload["exposure"])
        concentration = (exposure / max(gross_exposure, 1e-6)) if gross_exposure > 0 else 0.0
        avg_corr = statistics.mean(payload["corr_weights"]) if payload["corr_weights"] else 0.0
        directional_bias = abs(float(payload["directional"])) / max(exposure, 1e-6) if exposure > 0 else 0.0
        concentration_score = min(concentration * 0.6 + avg_corr * 0.25 + directional_bias * 0.15, 1.0)
        clusters.append(
            {
                "cluster_id": cluster_id,
                "symbols": sorted(payload["symbols"]),
                "cluster_exposure": round(exposure, 6),
                "concentration_ratio": round(concentration, 6),
                "avg_correlation": round(avg_corr, 6),
                "directional_bias": round(directional_bias, 6),
                "concentration_score": round(concentration_score, 6),
            }
        )

    clusters.sort(key=lambda item: item["concentration_score"], reverse=True)
    dominant = clusters[0] if clusters else None
    concentration_score = float(dominant.get("concentration_score") or 0.0) if dominant else 0.0

    override = dict((input_state or {}).get("cluster_override") or {})
    if bool(override.get("correlation_spike")):
        concentration_score = max(concentration_score, 0.92)

    risk_flag = "LOW"
    if concentration_score >= 0.8:
        risk_flag = "HIGH"
    elif concentration_score >= 0.6:
        risk_flag = "WARN"

    return {
        "windows": windows,
        "correlation_matrix": matrix_by_window,
        "clusters": clusters,
        "concentration_score": round(concentration_score, 6),
        "dominant_cluster": dominant,
        "risk_flag": risk_flag,
    }


def _tail_scenario_loss(positions: list[dict], scenario: dict) -> float:
    name = scenario.get("name")
    loss = 0.0
    for position in positions:
        symbol = str(position.get("symbol") or "UNKNOWN").upper()
        base = _symbol_base(symbol)
        side_sign = 1 if str(position.get("side") or "LONG").upper() == "LONG" else -1
        notional = abs(_safe_float(position.get("quantity"), 0.0) * _safe_float(position.get("mark_price"), 0.0))
        shock = _safe_float(scenario.get("all"), 0.0)
        if name == "btc_-20" and base == "BTC":
            shock = -0.20
        elif name == "altcoin_correlation_spike":
            shock = -0.18 if base not in {"BTC", "ETH"} else -0.09
        elif name == "market_wide_drawdown":
            shock = -0.15
        elif name == "liquidity_drop":
            shock = -0.08
        pnl = notional * shock * side_sign
        loss += -min(pnl, 0.0)
    return round(loss, 6)


def _build_tail_risk(positions: list[dict], series: dict[str, list[float]], liquidation_rows: list[dict], input_state: dict | None) -> dict:
    weighted_returns: list[float] = []
    symbol_weights = {
        str(item.get("symbol") or "UNKNOWN").upper(): abs(_safe_float(item.get("quantity"), 0.0) * _safe_float(item.get("mark_price"), 0.0))
        for item in positions
    }
    total_weight = sum(symbol_weights.values())
    for symbol, prices in series.items():
        rets = _returns(prices)
        weight = symbol_weights.get(symbol, 0.0) / max(total_weight, 1e-6) if total_weight > 0 else 0.0
        weighted_returns.extend([ret * weight for ret in rets[-240:]])

    override = dict((input_state or {}).get("tail_override") or {})
    if isinstance(override.get("returns"), list) and override.get("returns"):
        weighted_returns = [float(item) for item in override.get("returns")]

    var_95 = abs(_percentile(weighted_returns, 0.05)) if weighted_returns else 0.0
    left_tail = sorted(weighted_returns)[: max(1, int(len(weighted_returns) * 0.05))] if weighted_returns else []
    cvar_95 = abs(sum(left_tail) / len(left_tail)) if left_tail else 0.0

    scenarios = [
        {"name": "btc_-20"},
        {"name": "altcoin_correlation_spike"},
        {"name": "market_wide_drawdown"},
        {"name": "liquidity_drop"},
    ]
    scenario_rows = []
    for scenario in scenarios:
        stress_loss = _tail_scenario_loss(positions, scenario)
        scenario_rows.append({
            "name": scenario["name"],
            "portfolio_loss": stress_loss,
        })

    scenario_rows.sort(key=lambda item: item["portfolio_loss"], reverse=True)
    worst = scenario_rows[0] if scenario_rows else {"name": None, "portfolio_loss": 0.0}
    current_min_buffer = min([float(item.get("liquidation_buffer_pct") or 999.0) for item in liquidation_rows], default=999.0)
    liquidation_proximity_change = min(current_min_buffer, current_min_buffer * (1 - min(worst.get("portfolio_loss", 0.0) / max(total_weight, 1e-6), 0.9)))

    risk_flag = "LOW"
    if var_95 >= 0.08 or cvar_95 >= 0.12 or worst.get("portfolio_loss", 0.0) > max(total_weight, 1.0) * 0.18:
        risk_flag = "HIGH"
    elif var_95 >= 0.05 or cvar_95 >= 0.08:
        risk_flag = "WARN"

    return {
        "var": round(var_95, 6),
        "cvar": round(cvar_95, 6),
        "stress_loss": round(float(worst.get("portfolio_loss") or 0.0), 6),
        "worst_scenario": worst.get("name"),
        "risk_flag": risk_flag,
        "stress_scenarios": scenario_rows,
        "liquidation_proximity_change": round(liquidation_proximity_change, 6),
    }


def _strategy_risk_governance(strategy_allocation: list[dict]) -> dict:
    strategies = []
    breached = []
    actions: list[dict] = []
    for row in strategy_allocation:
        strategy_id = str(row.get("strategy_id") or "default")
        usage = (float(row.get("capital_share_pct") or 0.0) / max(float(row.get("risk_budget_pct") or 1.0), 1e-6)) * 100
        repeated_breach_count = _strategy_breach_history_from_manifest(strategy_id)
        action = "NORMAL"
        if usage > 100:
            action = "PAUSE"
        elif usage > 80:
            action = "THROTTLE"
        if repeated_breach_count >= 3 and usage > 100:
            action = "BLOCK"

        strategy_row = {
            "strategy_id": strategy_id,
            "usage_pct": round(usage, 6),
            "risk_budget_pct": row.get("risk_budget_pct"),
            "capital_share_pct": row.get("capital_share_pct"),
            "repeated_breach_count": repeated_breach_count,
            "action": action,
            "breach": bool(row.get("breach")) or usage > 100,
        }
        strategies.append(strategy_row)
        if strategy_row["breach"]:
            breached.append(strategy_row)
        if action in {"THROTTLE", "PAUSE", "BLOCK"}:
            actions.append({"strategy_id": strategy_id, "action": action})

    return {
        "strategies": strategies,
        "breached_strategies": breached,
        "actions": actions,
    }


def _risk_state_machine(
    *,
    min_liquidation_buffer_pct: float,
    margin_usage_pct: float,
    risk_budget_breaches: int,
    cluster_score: float,
    tail_var: float,
    tail_cvar: float,
    strategy_actions: list[dict],
) -> tuple[str, list[str]]:
    triggers: list[str] = []
    state = "NORMAL"

    if min_liquidation_buffer_pct < 10:
        state = "WARN"
        triggers.append("liquidation_buffer_warn")
    if min_liquidation_buffer_pct < 5 or margin_usage_pct > 65 or risk_budget_breaches > 0 or cluster_score >= 0.6 or tail_var >= 0.05:
        state = "HIGH"
        triggers.extend(
            [
                "liquidation_buffer_high",
                "margin_usage_high" if margin_usage_pct > 65 else "",
                "risk_budget_breach" if risk_budget_breaches > 0 else "",
                "cluster_concentration_high" if cluster_score >= 0.6 else "",
                "tail_var_breach" if tail_var >= 0.05 else "",
            ]
        )
    if min_liquidation_buffer_pct < 3 or margin_usage_pct > 80 or cluster_score >= 0.8 or tail_cvar >= 0.1 or any(item.get("action") == "PAUSE" for item in strategy_actions):
        state = "CRITICAL"
        triggers.extend(
            [
                "liquidation_buffer_critical",
                "margin_usage_critical" if margin_usage_pct > 80 else "",
                "cluster_concentration_critical" if cluster_score >= 0.8 else "",
                "tail_cvar_breach" if tail_cvar >= 0.1 else "",
                "strategy_pause_triggered" if any(item.get("action") == "PAUSE" for item in strategy_actions) else "",
            ]
        )
    if min_liquidation_buffer_pct < 1.5 or margin_usage_pct > 90 or tail_cvar >= 0.16 or any(item.get("action") == "BLOCK" for item in strategy_actions):
        state = "BLOCKED"
        triggers.extend(["kill_switch_threshold", "strategy_block_triggered" if any(item.get("action") == "BLOCK" for item in strategy_actions) else ""])

    triggers = [item for item in triggers if item]
    return state, sorted(set(triggers))


def _execution_policy_from_state(state: str) -> dict:
    policy = {
        "state": state,
        "block_new_orders": False,
        "reduce_size_multiplier": 1.0,
        "reduce_leverage_to": None,
        "pause_strategy": False,
        "kill_switch_triggered": False,
        "decision": "ALLOW",
    }
    if state == "WARN":
        policy.update({"reduce_size_multiplier": 0.85, "decision": "ALLOW_WITH_REDUCE"})
    elif state == "HIGH":
        policy.update({"reduce_size_multiplier": 0.6, "reduce_leverage_to": 3, "decision": "REDUCE_RISK", "pause_strategy": False})
    elif state == "CRITICAL":
        policy.update({"block_new_orders": True, "reduce_size_multiplier": 0.0, "reduce_leverage_to": 2, "pause_strategy": True, "decision": "BLOCK_NEW_ORDERS"})
    elif state == "BLOCKED":
        policy.update({"block_new_orders": True, "reduce_size_multiplier": 0.0, "reduce_leverage_to": 1, "pause_strategy": True, "kill_switch_triggered": True, "decision": "KILL_SWITCH"})
    return policy


def _write_snapshot_artifact(payload: dict, *, snapshot_type: str, stage: str) -> dict:
    now = _now()
    folder = RISK_SNAPSHOT_DIR / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    artifact_id = f"risk-snapshot-{stage}-{uuid.uuid4().hex[:12]}"
    artifact_path = folder / f"{artifact_id}.json"
    artifact_payload = {
        "artifact_id": artifact_id,
        "generated_at": _iso(now),
        "snapshot_type": snapshot_type,
        "stage": stage,
        "payload": payload,
    }
    artifact_path.write_text(json.dumps(artifact_payload, indent=2), encoding="utf-8")

    manifest_row = {
        "artifact_id": artifact_id,
        "generated_at": _iso(now),
        "snapshot_type": snapshot_type,
        "stage": stage,
        "artifact_path": str(artifact_path),
        "risk_state": payload.get("global_risk_state"),
        "execution_policy": payload.get("execution_policy", {}).get("decision"),
    }
    RISK_SNAPSHOT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with RISK_SNAPSHOT_MANIFEST.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest_row, ensure_ascii=False) + "\n")

    return {
        "artifact_id": artifact_id,
        "artifact_path": str(artifact_path),
        "manifest_row": manifest_row,
    }


def list_risk_snapshot_manifest(limit: int = 100) -> dict:
    if not RISK_SNAPSHOT_MANIFEST.exists():
        return {"items": []}
    rows: list[dict] = []
    with RISK_SNAPSHOT_MANIFEST.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return {"items": list(reversed(rows[-max(1, min(limit, 500)) :]))}


def run_unified_risk_orchestrator(
    *,
    db: Session | None,
    cache,
    user_id: str,
    ruleset: str = "binance",
    input_state: dict | None = None,
    snapshot_type: str = "portfolio-level",
    stage: str = "pre-trade",
    actor_id: str | None = None,
    persist_artifact: bool = True,
) -> dict:
    selected_ruleset = _get_ruleset(ruleset)
    replay_prices = _read_execution_manifest_prices(limit=800)
    mark_price_fallback = replay_prices[-1] if replay_prices else 100.0

    account_state = _resolve_account_state(db, user_id, input_state)
    positions = _load_positions(db, user_id, input_state, mark_price_fallback)

    cross_positions = [row for row in positions if str(row.get("margin_mode") or "cross").lower() != "isolated"]
    total_cross_notional = sum(abs(_safe_float(row.get("quantity"), 0.0) * _safe_float(row.get("mark_price"), 0.0)) for row in cross_positions)
    cross_collateral = float(account_state.get("free_collateral") or 0.0)

    liquidation_rows: list[dict] = []
    for row in positions:
        row_notional = abs(_safe_float(row.get("quantity"), 0.0) * _safe_float(row.get("mark_price"), 0.0))
        cross_share = 0.0
        if str(row.get("margin_mode") or "cross").lower() != "isolated":
            cross_share = cross_collateral * (row_notional / max(total_cross_notional, 1e-6))
        liquidation_rows.append(_compute_liquidation(row, cross_collateral_share=cross_share, ruleset=selected_ruleset))

    portfolio = _portfolio_metrics(positions, liquidation_rows, float(account_state.get("equity") or 1.0))
    capital = _capital_governance(account_state, portfolio, liquidation_rows, input_state)
    symbol_series = _build_symbol_series(positions, replay_prices, input_state)
    cluster_risk = _build_cluster_risk(positions, symbol_series, float(portfolio.get("gross_exposure") or 0.0), input_state)
    tail_risk = _build_tail_risk(positions, symbol_series, liquidation_rows, input_state)
    strategy_risk = _strategy_risk_governance(capital.get("strategy_allocation") or [])

    min_liq_buffer = min((row.get("liquidation_buffer_pct") or 999.0) for row in liquidation_rows) if liquidation_rows else 999.0
    state, triggers = _risk_state_machine(
        min_liquidation_buffer_pct=float(min_liq_buffer),
        margin_usage_pct=float(capital.get("margin_usage_pct") or 0.0),
        risk_budget_breaches=int(capital.get("risk_budget_breach_count") or 0),
        cluster_score=float(cluster_risk.get("concentration_score") or 0.0),
        tail_var=float(tail_risk.get("var") or 0.0),
        tail_cvar=float(tail_risk.get("cvar") or 0.0),
        strategy_actions=strategy_risk.get("actions") or [],
    )
    execution_policy = _execution_policy_from_state(state)
    if any(item.get("action") == "THROTTLE" for item in (strategy_risk.get("actions") or [])) and execution_policy.get("reduce_size_multiplier", 1.0) > 0.7:
        execution_policy["reduce_size_multiplier"] = 0.7
        execution_policy["decision"] = "REDUCE_RISK"
    if any(item.get("action") == "PAUSE" for item in (strategy_risk.get("actions") or [])):
        execution_policy["pause_strategy"] = True
        execution_policy["decision"] = "PAUSE_STRATEGY"
    if any(item.get("action") == "BLOCK" for item in (strategy_risk.get("actions") or [])):
        execution_policy["block_new_orders"] = True
        execution_policy["kill_switch_triggered"] = True
        execution_policy["decision"] = "KILL_SWITCH"
        state = "BLOCKED"
        triggers.append("strategy_block_triggered")

    canonical_state = {
        "user_id": user_id,
        "generated_at": _iso(),
        "ruleset": selected_ruleset["name"],
        "account": account_state,
        "positions": positions,
        "liquidation": {
            "positions": liquidation_rows,
            "min_liquidation_buffer_pct": round(float(min_liq_buffer), 6),
            "avg_margin_ratio": round(statistics.mean([float(row.get("margin_ratio") or 0.0) for row in liquidation_rows]) if liquidation_rows else 0.0, 6),
        },
        "portfolio": portfolio,
        "capital": capital,
        "cluster_risk": cluster_risk,
        "tail_risk": tail_risk,
        "strategy_risk": strategy_risk,
        "cluster": cluster_risk,
        "tail": tail_risk,
        "global_risk_state": state,
        "state_machine": ["NORMAL", "WARN", "HIGH", "CRITICAL", "BLOCKED"],
        "execution_policy": execution_policy,
        "explainability": {
            "decision": execution_policy.get("decision"),
            "triggers": sorted(set(triggers)),
            "reason": sorted(set(triggers)),
            "metrics": {
                "cluster_score": cluster_risk.get("concentration_score"),
                "tail_var": tail_risk.get("var"),
                "tail_cvar": tail_risk.get("cvar"),
                "margin_usage_pct": capital.get("margin_usage_pct"),
                "strategy_actions": strategy_risk.get("actions"),
                "min_liquidation_buffer_pct": min_liq_buffer,
            },
            "input_summary": {
                "position_count": len(positions),
                "equity": account_state.get("equity"),
                "ruleset": selected_ruleset["name"],
                "snapshot_type": snapshot_type,
                "stage": stage,
            },
            "policy_result": execution_policy,
            "timestamp": _iso(),
        },
        "orchestrator_contract": {
            "single_entry": "risk_orchestrator",
            "hard_rule": "no_module_can_emit_execution_policy_directly",
        },
    }

    artifact = None
    if persist_artifact:
        artifact = _write_snapshot_artifact(canonical_state, snapshot_type=snapshot_type, stage=stage)
        canonical_state["artifact"] = artifact

    if db is not None and actor_id:
        try:
            create_audit_log(
                db,
                action="unified_risk_orchestrator_evaluated",
                entity_type="unified_risk_core",
                entity_id=user_id,
                actor_user_id=actor_id,
                actor_role="admin",
                details={
                    "global_risk_state": state,
                    "execution_decision": execution_policy.get("decision"),
                    "ruleset": selected_ruleset["name"],
                    "trigger_count": len(triggers),
                    "artifact_id": (artifact or {}).get("artifact_id"),
                },
                severity="info",
            )
        except Exception:
            pass

    return canonical_state


def simulate_pre_trade_risk(
    *,
    db: Session | None,
    cache,
    user_id: str,
    proposed_order: dict,
    ruleset: str = "binance",
    actor_id: str | None = None,
) -> dict:
    before_state = run_unified_risk_orchestrator(
        db=db,
        cache=cache,
        user_id=user_id,
        ruleset=ruleset,
        input_state=None,
        snapshot_type="pre-trade",
        stage="pre-trade-before",
        actor_id=actor_id,
        persist_artifact=True,
    )

    before_positions = list(before_state.get("positions") or [])
    order_position = _default_position_from_input(
        {
            "symbol": proposed_order.get("symbol"),
            "side": proposed_order.get("side"),
            "quantity": proposed_order.get("quantity"),
            "entry_price": proposed_order.get("price") or proposed_order.get("entry_price"),
            "mark_price": proposed_order.get("price") or proposed_order.get("mark_price"),
            "leverage": proposed_order.get("leverage") or 1,
            "margin_mode": proposed_order.get("margin_mode") or "cross",
            "strategy_id": proposed_order.get("strategy_id") or "simulated",
        },
        mark_price_fallback=_safe_float((before_state.get("liquidation", {}).get("positions") or [{}])[0].get("mark_price"), 100.0),
    )
    before_positions.append(order_position)

    after_input_state = {
        "account": before_state.get("account") or {},
        "positions": before_positions,
        "strategy_risk_budgets": {
            row.get("strategy_id"): row.get("risk_budget_pct")
            for row in (before_state.get("capital", {}).get("strategy_allocation") or [])
        },
    }
    after_state = run_unified_risk_orchestrator(
        db=db,
        cache=cache,
        user_id=user_id,
        ruleset=ruleset,
        input_state=after_input_state,
        snapshot_type="post-trade",
        stage="pre-trade-after",
        actor_id=actor_id,
        persist_artifact=True,
    )

    before_portfolio = before_state.get("portfolio") or {}
    after_portfolio = after_state.get("portfolio") or {}
    before_capital = before_state.get("capital") or {}
    after_capital = after_state.get("capital") or {}

    delta = {
        "gross_exposure_delta": round(
            _safe_float(after_portfolio.get("gross_exposure"), 0.0)
            - _safe_float(before_portfolio.get("gross_exposure"), 0.0),
            6,
        ),
        "margin_usage_delta_pct": round(
            _safe_float(after_capital.get("margin_usage_pct"), 0.0)
            - _safe_float(before_capital.get("margin_usage_pct"), 0.0),
            6,
        ),
        "min_liquidation_buffer_delta_pct": round(
            _safe_float((after_state.get("liquidation") or {}).get("min_liquidation_buffer_pct"), 0.0)
            - _safe_float((before_state.get("liquidation") or {}).get("min_liquidation_buffer_pct"), 0.0),
            6,
        ),
        "state_transition": {
            "before": before_state.get("global_risk_state"),
            "after": after_state.get("global_risk_state"),
        },
        "stress_sensitivity_delta": {
            "var_delta": round(
                _safe_float((after_state.get("tail_risk") or {}).get("var"), 0.0)
                - _safe_float((before_state.get("tail_risk") or {}).get("var"), 0.0),
                6,
            ),
            "cvar_delta": round(
                _safe_float((after_state.get("tail_risk") or {}).get("cvar"), 0.0)
                - _safe_float((before_state.get("tail_risk") or {}).get("cvar"), 0.0),
                6,
            ),
        },
    }

    return {
        "ruleset": ruleset,
        "proposed_order": proposed_order,
        "before": {
            "global_risk_state": before_state.get("global_risk_state"),
            "execution_policy": before_state.get("execution_policy"),
            "liquidation": before_state.get("liquidation"),
            "portfolio": before_state.get("portfolio"),
            "capital": before_state.get("capital"),
            "cluster_risk": before_state.get("cluster_risk"),
            "tail_risk": before_state.get("tail_risk"),
            "strategy_risk": before_state.get("strategy_risk"),
            "artifact": before_state.get("artifact"),
        },
        "after": {
            "global_risk_state": after_state.get("global_risk_state"),
            "execution_policy": after_state.get("execution_policy"),
            "liquidation": after_state.get("liquidation"),
            "portfolio": after_state.get("portfolio"),
            "capital": after_state.get("capital"),
            "cluster_risk": after_state.get("cluster_risk"),
            "tail_risk": after_state.get("tail_risk"),
            "strategy_risk": after_state.get("strategy_risk"),
            "artifact": after_state.get("artifact"),
        },
        "impact_delta": delta,
    }


def jira_epic_breakdown() -> dict:
    return {
        "epics": [
            {
                "epic": "URC-P0 Unified Risk Core",
                "status": "done",
                "items": [
                    "URC-01 Canonical unified risk data model",
                    "URC-02 Position-level liquidation engine (cross/isolated)",
                    "URC-03 Portfolio exposure + effective leverage engine",
                    "URC-04 Capital governance with equity/margin/free collateral",
                    "URC-05 Unified risk state machine NORMAL→BLOCKED",
                    "URC-06 Risk→Execution policy decision object",
                    "URC-07 Snapshot artifact pipeline (pre/post/portfolio)",
                ],
            },
            {
                "epic": "URC-P1 Advanced Risk Layer",
                "status": "done_in_sprint_2",
                "items": [
                    "URC-31 Rolling correlation windows (30/60/120) + cluster concentration",
                    "URC-32 Tail risk engine: VaR/CVaR + stress scenarios",
                    "URC-33 Strategy risk budget governance (throttle/pause/block)",
                    "URC-34 Ruleset deepening (tier-based margin + leverage brackets + collateral haircuts)",
                    "URC-35 P1 metrics integrated into unified state + execution policy",
                    "URC-36 Explainability expansion (reason + metrics + policy result)",
                ],
            },
            {
                "epic": "URC-P2 Orchestrator Skeleton (Early)",
                "status": "done",
                "items": [
                    "URC-21 Single-entry risk_orchestrator contract",
                    "URC-22 Pre-trade simulation before/after impact",
                    "URC-23 Explainability payload + proof logs",
                    "URC-24 Kill-switch policy mapping",
                ],
            },
        ],
        "hard_constraints": {
            "single_entry": "risk_orchestrator",
            "no_direct_execution_binding": True,
            "live_exchange_required": False,
            "mode": "simulation/replay",
        },
    }
