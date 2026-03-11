import hashlib
import json
import uuid

from models import RegimeSnapshot, StrategyRegimeBinding


REGIME_LABELS = [
    "trend_up",
    "trend_down",
    "range_low_vol",
    "range_high_vol",
    "breakout_transition",
    "panic_dislocation",
]


def _canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def classify_regime(context_payload: dict) -> dict:
    features = context_payload.get("input_features", {}) or {}
    market_snapshot = context_payload.get("market_snapshot", {}) or {}

    momentum = float(features.get("momentum", 0) or 0)
    volatility = float(features.get("volatility", 0) or 0)
    bid = float(market_snapshot.get("bid") or market_snapshot.get("last_price") or 0)
    ask = float(market_snapshot.get("ask") or market_snapshot.get("last_price") or 0)
    mid = ((bid + ask) / 2) if (bid > 0 and ask > 0) else float(market_snapshot.get("last_price") or 0)
    spread_bps = ((ask - bid) / mid * 10000) if mid > 0 else 0

    if volatility >= 0.85:
        volatility_regime = "extreme"
    elif volatility >= 0.45:
        volatility_regime = "high"
    elif volatility >= 0.2:
        volatility_regime = "medium"
    else:
        volatility_regime = "low"

    if momentum >= 0.12:
        trend_regime = "up"
    elif momentum <= -0.12:
        trend_regime = "down"
    else:
        trend_regime = "flat"

    if spread_bps >= 8:
        liquidity_regime = "thin"
    elif spread_bps >= 3:
        liquidity_regime = "normal"
    else:
        liquidity_regime = "deep"

    if volatility_regime == "extreme" and liquidity_regime == "thin":
        regime_label = "panic_dislocation"
    elif trend_regime == "up" and volatility_regime in {"low", "medium"}:
        regime_label = "trend_up"
    elif trend_regime == "down" and volatility_regime in {"low", "medium"}:
        regime_label = "trend_down"
    elif trend_regime == "flat" and volatility_regime in {"low", "medium"}:
        regime_label = "range_low_vol"
    elif trend_regime == "flat" and volatility_regime in {"high", "extreme"}:
        regime_label = "range_high_vol"
    else:
        regime_label = "breakout_transition"

    regime_score = round(min(1.0, max(0.0, abs(momentum) + volatility * 0.65 + (spread_bps / 1000))), 6)

    snapshot_payload = {
        "timestamp_utc": context_payload.get("timestamp_utc"),
        "symbol": context_payload.get("symbol"),
        "timeframe": context_payload.get("timeframe"),
        "volatility_regime": volatility_regime,
        "trend_regime": trend_regime,
        "liquidity_regime": liquidity_regime,
        "market_state_features": {
            "momentum": round(momentum, 8),
            "volatility": round(volatility, 8),
            "spread_bps": round(spread_bps, 8),
        },
        "feature_set_version": str(context_payload.get("feature_set_version") or "1.0"),
        "regime_score": regime_score,
        "regime_label": regime_label,
    }
    regime_hash = _hash(snapshot_payload)
    return {
        "regime_snapshot_id": str(uuid.uuid4()),
        **snapshot_payload,
        "regime_hash": regime_hash,
    }


def persist_regime_snapshot(*, strategy_version_id: str, snapshot_payload: dict) -> RegimeSnapshot:
    return RegimeSnapshot(
        regime_snapshot_id=snapshot_payload["regime_snapshot_id"],
        timestamp_utc=snapshot_payload["timestamp_utc"],
        symbol=snapshot_payload["symbol"],
        timeframe=snapshot_payload["timeframe"],
        strategy_version_id=strategy_version_id,
        volatility_regime=snapshot_payload["volatility_regime"],
        trend_regime=snapshot_payload["trend_regime"],
        liquidity_regime=snapshot_payload["liquidity_regime"],
        market_state_features=snapshot_payload["market_state_features"],
        feature_set_version=snapshot_payload["feature_set_version"],
        regime_score=snapshot_payload["regime_score"],
        regime_label=snapshot_payload["regime_label"],
        regime_hash=snapshot_payload["regime_hash"],
    )


def is_regime_allowed(binding: StrategyRegimeBinding | None, regime_label: str) -> bool:
    if binding is None:
        return True

    allowed = {item for item in (binding.allowed_regimes or [])}
    blocked = {item for item in (binding.blocked_regimes or [])}
    if regime_label in blocked:
        return False
    if allowed and regime_label not in allowed:
        return False
    return True
