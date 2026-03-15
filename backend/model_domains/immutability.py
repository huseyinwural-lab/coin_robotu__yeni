from sqlalchemy import event

from model_domains.risk_execution_positions import ExecutionIntent, ExecutionMetric
from model_domains.strategy_decision import StrategyRegimeBinding, StrategyVersion

@event.listens_for(ExecutionMetric, "before_update", propagate=True)
def _block_execution_metric_update(_, __, ___):
    raise ValueError("execution_metric_immutable")

@event.listens_for(StrategyVersion, "before_update", propagate=True)
def _block_strategy_version_update(_, __, ___):
    raise ValueError("strategy_version_immutable")

@event.listens_for(ExecutionIntent, "before_update", propagate=True)
def _block_execution_intent_update(_, __, ___):
    raise ValueError("execution_intent_immutable")

@event.listens_for(StrategyRegimeBinding, "before_update", propagate=True)
def _block_strategy_regime_binding_update(_, __, ___):
    raise ValueError("strategy_regime_binding_immutable")
