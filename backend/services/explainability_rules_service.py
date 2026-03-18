from __future__ import annotations


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_nested(payload: dict, path: str):
    current = payload
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def _read_float(payload: dict, *paths: str) -> float | None:
    for path in paths:
        value = _safe_float(_extract_nested(payload, path))
        if value is not None:
            return value
    return None


def build_screener_explain(*, payload: dict | None, signal: str, signal_score: float | int | None) -> list[str]:
    snapshot = dict(payload or {})
    explain: list[str] = []

    rsi = _read_float(snapshot, "rsi", "rsi14", "indicator_snapshot.rsi14")
    if rsi is not None:
        if rsi <= 30:
            explain.append(f"RSI oversold ({int(round(rsi))})")
        elif rsi >= 70:
            explain.append(f"RSI overbought ({int(round(rsi))})")
        else:
            explain.append(f"RSI neutral ({int(round(rsi))})")

    volume_ratio = _read_float(
        snapshot,
        "volume_spike",
        "relative_volume",
        "volume_ratio",
        "indicator_snapshot.volume_spike",
        "indicator_snapshot.relative_volume",
    )
    if volume_ratio is not None:
        if volume_ratio >= 1.5:
            explain.append(f"Volume spike ({round(volume_ratio, 1)}x)")
        else:
            explain.append(f"Volume stable ({round(volume_ratio, 1)}x)")

    price = _read_float(snapshot, "price", "indicator_snapshot.price", "last_price")
    ma50 = _read_float(snapshot, "ma50", "ma_50", "indicator_snapshot.ma50", "indicator_snapshot.ma_50")
    if price is not None and ma50 is not None:
        explain.append("Above MA50" if price >= ma50 else "Below MA50")
    else:
        normalized_signal = str(signal or "none").strip().lower()
        if normalized_signal in {"long", "buy"}:
            explain.append("Trend up bias")
        elif normalized_signal in {"short", "sell"}:
            explain.append("Trend down bias")

    if not explain:
        try:
            score = int(round(float(signal_score or 0)))
        except (TypeError, ValueError):
            score = 0
        explain.append(f"Signal score context ({score})")

    return explain[:3]


def build_trade_explain(
    *,
    validation: dict | None,
    execution_mode: str,
    signal_score: float | int | None = None,
) -> list[str]:
    context = dict(validation or {})
    checks = dict(context.get("checks") or {})
    violations = list(context.get("violations") or [])

    explain: list[str] = []
    if signal_score is None:
        explain.append("Signal score: n/a")
    else:
        explain.append(f"Signal score: {int(round(float(signal_score)))}")

    explain.append("Risk check passed" if len(violations) == 0 else f"Risk check failed ({len(violations)} violations)")

    leverage_limit = _safe_float(checks.get("leverage_limit"))
    requested_leverage = _safe_float(checks.get("requested_leverage"))
    leverage_violation = any(str(item.get("code") or "") == "leverage_limit_exceeded" for item in violations if isinstance(item, dict))
    if leverage_violation:
        explain.append("Leverage exceeds limit")
    elif leverage_limit is not None and requested_leverage is not None:
        explain.append(f"Leverage within limit ({int(requested_leverage)}/{int(leverage_limit)})")
    else:
        explain.append("Leverage within limit")

    explain.append(f"Execution mode: {str(execution_mode or 'mocked').lower()}")
    return explain[:4]


def explain_consistency_ok(*, screener_explain: list[str], trade_explain: list[str]) -> bool:
    joined = " | ".join([*(screener_explain or []), *(trade_explain or [])]).lower()
    conflict_pairs = [
        ("rsi oversold", "rsi overbought"),
        ("above ma50", "below ma50"),
        ("trend up", "trend down"),
    ]
    for left, right in conflict_pairs:
        if left in joined and right in joined:
            return False
    return True
