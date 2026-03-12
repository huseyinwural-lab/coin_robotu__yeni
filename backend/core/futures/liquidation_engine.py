from core.futures.position_model import FuturesPosition


def calculate_margin_ratio(position: FuturesPosition) -> float:
    if position.initial_margin <= 0:
        return 999.0
    buffer = max(position.initial_margin + position.unrealized_pnl - position.maintenance_margin, 0.0)
    ratio = (buffer / position.initial_margin) * 100
    return round(ratio, 4)


def calculate_liquidation_price(position: FuturesPosition) -> float:
    notional = max(position.notional_value, 0.0001)
    maintenance_rate = position.maintenance_margin / notional
    margin_rate = position.initial_margin / notional
    gap = max(margin_rate - maintenance_rate, 0.0001)

    if position.side == "LONG":
        liq = position.entry_price * (1 - gap)
    else:
        liq = position.entry_price * (1 + gap)
    return round(max(liq, 0.0001), 6)


def calculate_distance_to_liquidation(position: FuturesPosition) -> float:
    liq_price = calculate_liquidation_price(position)
    distance = abs((position.mark_price - liq_price) / position.mark_price) * 100 if position.mark_price else 0.0
    return round(distance, 4)


def liquidation_risk_level(distance_to_liquidation: float) -> str:
    if distance_to_liquidation < 8:
        return "CRITICAL"
    if distance_to_liquidation <= 15:
        return "WARNING"
    return "SAFE"
