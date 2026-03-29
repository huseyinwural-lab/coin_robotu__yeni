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
from services.futures_correlation_service import get_futures_cluster_risk
from services.futures_tail_risk_service import get_futures_tail_risk


RISK_SNAPSHOT_DIR = Path("/app/artifacts/risk_snapshots")
RISK_SNAPSHOT_MANIFEST = Path("/app/artifacts/manifests/unified_risk_snapshots.jsonl")

RULESETS: dict[str, dict[str, Any]] = {
    "binance": {
        "name": "binance",
        "maintenance_margin_base": 0.005,
        "maintenance_margin_step": 0.0005,
        "fee_buffer_pct": 0.0006,
        "safety_haircut_pct": 0.02,
        "warn_liquidation_buffer_pct": 8.0,
        "critical_liquidation_buffer_pct": 3.0,
        "max_leverage": 125,
    },
    "bybit": {
        "name": "bybit",
        "maintenance_margin_base": 0.0055,
        "maintenance_margin_step": 0.00055,
        "fee_buffer_pct": 0.0007,
        "safety_haircut_pct": 0.022,
        "warn_liquidation_buffer_pct": 7.5,
        "critical_liquidation_buffer_pct": 2.8,
        "max_leverage": 100,
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

    maintenance_rate = float(ruleset.get("maintenance_margin_base", 0.005)) + (
        max(leverage - 1, 0) * float(ruleset.get("maintenance_margin_step", 0.0005))
    )
    maintenance_rate = min(max(maintenance_rate, 0.003), 0.08)
    maintenance_margin = notional * maintenance_rate
    initial_margin = notional / leverage

    pnl_direction = 1.0 if side == "LONG" else -1.0
    unrealized_pnl = (mark_price - entry_price) * quantity * pnl_direction
    fee_buffer = notional * float(ruleset.get("fee_buffer_pct", 0.0006))
    safety_haircut = initial_margin * float(ruleset.get("safety_haircut_pct", 0.02))

    margin_mode = str(position.get("margin_mode") or "cross").lower()
    isolated_margin = max(_safe_float(position.get("isolated_margin"), 0.0), 0.0)
    collateral = isolated_margin if margin_mode == "isolated" and isolated_margin > 0 else cross_collateral_share
    collateral = max(collateral, initial_margin)

    effective_margin = collateral + unrealized_pnl - fee_buffer - safety_haircut
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
        "entry_price": round(entry_price, 6),
        "mark_price": round(mark_price, 6),
        "quantity": round(quantity, 6),
        "notional": round(notional, 6),
        "initial_margin": round(initial_margin, 6),
        "maintenance_margin": round(maintenance_margin, 6),
        "maintenance_margin_rate": round(maintenance_rate, 6),
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


def _cluster_tail_skeleton(db: Session | None, cache, user_id: str, replay_prices: list[float]) -> dict:
    rets = _returns(replay_prices)
    left_tail = sorted(rets)[: max(1, int(len(rets) * 0.05))] if rets else []
    var_95 = abs(_percentile(rets, 0.05)) if rets else 0.0
    cvar_95 = abs(sum(left_tail) / len(left_tail)) if left_tail else 0.0

    stress_scenarios = [
        {"name": "major_coin_shock", "shock_pct": -0.12},
        {"name": "alt_correlation_spike", "shock_pct": -0.18},
        {"name": "market_wide_drawdown", "shock_pct": -0.22},
        {"name": "liquidity_deterioration", "shock_pct": -0.09},
    ]

    cluster_payload = {"risk_state": "NORMAL", "cluster_exposures": [], "cluster_risk_alerts": []}
    tail_payload = {"tail_risk_score": 0.0, "risk_state": "NORMAL", "active_alerts": []}
    if db is not None and cache is not None:
        try:
            cluster_payload = get_futures_cluster_risk(db, cache, user_id, refresh=False)
        except Exception:
            cluster_payload = {"risk_state": "NORMAL", "cluster_exposures": [], "cluster_risk_alerts": []}
        try:
            tail_payload = get_futures_tail_risk(db, cache, user_id, refresh=False)
        except Exception:
            tail_payload = {"tail_risk_score": 0.0, "risk_state": "NORMAL", "active_alerts": []}

    return {
        "cluster": {
            "risk_state": str(cluster_payload.get("risk_state") or "NORMAL"),
            "cluster_exposures": cluster_payload.get("cluster_exposures") or [],
            "cluster_alerts": cluster_payload.get("cluster_risk_alerts") or [],
        },
        "tail": {
            "risk_state": str(tail_payload.get("risk_state") or "NORMAL"),
            "tail_risk_score": round(_safe_float(tail_payload.get("tail_risk_score"), 0.0), 6),
            "historical_var_95": round(var_95, 6),
            "historical_cvar_95": round(cvar_95, 6),
            "stress_scenarios": stress_scenarios,
            "active_alerts": tail_payload.get("active_alerts") or [],
        },
    }


def _risk_state_machine(*, min_liquidation_buffer_pct: float, margin_usage_pct: float, risk_budget_breaches: int, cluster_state: str, tail_score: float) -> tuple[str, list[str]]:
    triggers: list[str] = []
    state = "NORMAL"

    if min_liquidation_buffer_pct < 10:
        state = "WARN"
        triggers.append("liquidation_buffer_warn")
    if min_liquidation_buffer_pct < 5 or margin_usage_pct > 65 or risk_budget_breaches > 0:
        state = "HIGH"
        triggers.extend(["liquidation_buffer_high", "margin_usage_high" if margin_usage_pct > 65 else "", "risk_budget_breach" if risk_budget_breaches > 0 else ""])
    if min_liquidation_buffer_pct < 3 or margin_usage_pct > 80 or cluster_state in {"HIGH", "CRITICAL"} or tail_score > 75:
        state = "CRITICAL"
        triggers.extend(["liquidation_buffer_critical", "margin_usage_critical" if margin_usage_pct > 80 else "", "cluster_or_tail_critical"])
    if min_liquidation_buffer_pct < 1.5 or margin_usage_pct > 90 or tail_score > 90:
        state = "BLOCKED"
        triggers.extend(["kill_switch_threshold"])

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
        policy.update({"reduce_size_multiplier": 0.6, "reduce_leverage_to": 3, "decision": "REDUCE_RISK", "pause_strategy": True})
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
    cluster_tail = _cluster_tail_skeleton(db, cache, user_id, replay_prices)

    min_liq_buffer = min((row.get("liquidation_buffer_pct") or 999.0) for row in liquidation_rows) if liquidation_rows else 999.0
    state, triggers = _risk_state_machine(
        min_liquidation_buffer_pct=float(min_liq_buffer),
        margin_usage_pct=float(capital.get("margin_usage_pct") or 0.0),
        risk_budget_breaches=int(capital.get("risk_budget_breach_count") or 0),
        cluster_state=str(cluster_tail.get("cluster", {}).get("risk_state") or "NORMAL"),
        tail_score=float(cluster_tail.get("tail", {}).get("tail_risk_score") or 0.0),
    )
    execution_policy = _execution_policy_from_state(state)

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
        "cluster": cluster_tail.get("cluster") or {},
        "tail": cluster_tail.get("tail") or {},
        "global_risk_state": state,
        "state_machine": ["NORMAL", "WARN", "HIGH", "CRITICAL", "BLOCKED"],
        "execution_policy": execution_policy,
        "explainability": {
            "decision": execution_policy.get("decision"),
            "triggers": triggers,
            "input_summary": {
                "position_count": len(positions),
                "equity": account_state.get("equity"),
                "ruleset": selected_ruleset["name"],
                "snapshot_type": snapshot_type,
                "stage": stage,
            },
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
            "artifact": before_state.get("artifact"),
        },
        "after": {
            "global_risk_state": after_state.get("global_risk_state"),
            "execution_policy": after_state.get("execution_policy"),
            "liquidation": after_state.get("liquidation"),
            "portfolio": after_state.get("portfolio"),
            "capital": after_state.get("capital"),
            "artifact": after_state.get("artifact"),
        },
        "impact_delta": delta,
    }


def jira_epic_breakdown() -> dict:
    return {
        "epics": [
            {
                "epic": "URC-P0 Unified Risk Core",
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
                "epic": "URC-P2 Orchestrator Skeleton (Early)",
                "items": [
                    "URC-21 Single-entry risk_orchestrator contract",
                    "URC-22 Pre-trade simulation before/after impact",
                    "URC-23 Explainability payload + proof logs",
                    "URC-24 Kill-switch policy mapping",
                ],
            },
            {
                "epic": "URC-P1 Advanced Layer (Next Sprint)",
                "items": [
                    "URC-31 Rolling correlation cluster concentration",
                    "URC-32 Historical VaR/CVaR + stress scenario expansions",
                    "URC-33 Strategy risk budget throttle/pause",
                    "URC-34 Exchange rules abstraction hardening",
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
