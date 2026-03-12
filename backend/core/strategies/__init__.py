def build_strategy_registry():
    from core.portfolio.strategy_registry import build_strategy_registry as _build_strategy_registry

    return _build_strategy_registry()


__all__ = ["build_strategy_registry"]
