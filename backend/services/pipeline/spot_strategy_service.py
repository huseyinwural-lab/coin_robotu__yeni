from services.pipeline.legacy import spot_strategy_service as legacy_spot_strategy_service

LEGACY_EXPLORER_MODULE = True

_exports = [name for name in dir(legacy_spot_strategy_service) if not name.startswith("__")]
globals().update({name: getattr(legacy_spot_strategy_service, name) for name in _exports})
