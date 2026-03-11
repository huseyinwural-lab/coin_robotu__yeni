import hashlib
import json


def canonical_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_context_hash(context_payload: dict) -> str:
    canonical = canonical_payload(context_payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_decision_hash(decision_payload: dict) -> str:
    canonical = canonical_payload(decision_payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_decision_context(context_payload: dict) -> dict:
    context_hash = build_context_hash(context_payload)

    risk_state = context_payload.get("risk_state", {}) or {}
    features = context_payload.get("input_features", {}) or {}

    if bool(risk_state.get("blocked", False)):
        action = "REJECT"
        confidence = 0.0
        risk_score = 1.0
        reason_codes = ["risk_gate_blocked"]
        size = 0.0
    else:
        momentum = float(features.get("momentum", 0) or 0)
        volatility = float(features.get("volatility", 0) or 0)
        base_size = float(features.get("base_size", 0.001) or 0.001)

        if momentum > 0.1:
            action = "BUY"
            reason_codes = ["momentum_positive"]
        elif momentum < -0.1:
            action = "SELL"
            reason_codes = ["momentum_negative"]
        elif abs(momentum) < 0.02:
            action = "HOLD"
            reason_codes = ["momentum_neutral"]
        else:
            action = "CLOSE"
            reason_codes = ["momentum_decay"]

        confidence = round(min(1.0, max(0.0, abs(momentum) * 2)), 6)
        risk_score = round(min(1.0, max(0.0, volatility)), 6)
        size = round(base_size if action in {"BUY", "SELL"} else 0.0, 8)

    decision_payload = {
        "action": action,
        "size": size,
        "confidence": confidence,
        "risk_score": risk_score,
        "reason_codes": reason_codes,
        "strategy_version_id": context_payload.get("strategy_version_id"),
        "context_hash": context_hash,
        "order_intent": {"intent_type": action, "symbol": context_payload.get("symbol")},
        "price_reference": {"source": "market_snapshot", "value": context_payload.get("market_snapshot", {}).get("last_price")},
    }
    decision_payload["decision_hash"] = build_decision_hash(decision_payload)
    return decision_payload
