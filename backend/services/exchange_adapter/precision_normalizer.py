from decimal import Decimal, ROUND_DOWN


PRECISION_RULES = {
    "binance": {"price": 2, "qty": 4, "max_leverage": 10},
    "bybit": {"price": 2, "qty": 4, "max_leverage": 10},
    "okx": {"price": 2, "qty": 4, "max_leverage": 10},
}


def _quantize(value: float, decimals: int) -> float:
    quant = Decimal("1") if decimals == 0 else Decimal(f"1e-{decimals}")
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_DOWN))


def normalize_order_values(exchange: str, *, price: float, qty: float, leverage: int) -> dict:
    rules = PRECISION_RULES.get(str(exchange or "").lower().strip(), PRECISION_RULES["binance"])
    return {
        "price": _quantize(float(price), int(rules["price"])),
        "qty": _quantize(float(qty), int(rules["qty"])),
        "leverage": min(max(int(leverage), 1), int(rules["max_leverage"])),
        "rules": rules,
    }
