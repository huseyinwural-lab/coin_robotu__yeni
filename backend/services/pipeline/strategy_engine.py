from services.pipeline.legacy import strategy_engine as legacy_strategy_engine

LEGACY_EXPLORER_MODULE = True

_exports = [name for name in dir(legacy_strategy_engine) if not name.startswith("__")]
globals().update({name: getattr(legacy_strategy_engine, name) for name in _exports})
