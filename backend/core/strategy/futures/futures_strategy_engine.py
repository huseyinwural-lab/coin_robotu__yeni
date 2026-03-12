from dataclasses import asdict

from core.futures.decision.decision_trace_model import build_decision_trace
from core.futures.position_model import FuturesPosition
from core.strategy.futures_paper_decision_flow import run_futures_paper_decision_flow
from core.strategy.futures.strategy_contract import FuturesStrategy


class FuturesStrategyEngine:
    def __init__(self, strategy_registry: dict[str, FuturesStrategy]):
        self.strategy_registry = strategy_registry

    def evaluate_symbol(self, *, strategy_id: str, market_state: dict, risk_snapshot: dict) -> dict:
        strategy = self.strategy_registry[strategy_id]
        raw_signal = strategy.generate_signal(market_state)
        if isinstance(raw_signal, dict):
            signal_payload = {
                "symbol": str(market_state.get("symbol") or "UNKNOWN"),
                "side": str(raw_signal.get("signal") or "NONE").upper(),
                "confidence": float(raw_signal.get("confidence") or 0.0),
                "regime": str(market_state.get("volatility_regime") or "UNKNOWN"),
                "reason": str((raw_signal.get("context") or {}).get("reason") or "STRATEGY_SIGNAL"),
                "strategy_type": str((raw_signal.get("context") or {}).get("strategy_type") or strategy_id),
                "strategy_context": raw_signal.get("context") or {},
                "strategy_signal_strength": float(raw_signal.get("confidence") or 0.0),
            }
        else:
            signal_payload = asdict(raw_signal)
            signal_payload["strategy_type"] = strategy_id
            signal_payload["strategy_context"] = {}
            signal_payload["strategy_signal_strength"] = float(signal_payload.get("confidence") or 0.0)

        signal_side = str(signal_payload.get("side") or "NONE").upper()

        if signal_side == "NONE":
            trace_model = build_decision_trace(
                symbol=str(signal_payload.get("symbol") or market_state.get("symbol") or "UNKNOWN"),
                strategy=strategy_id,
                side=signal_side,
                signal_confidence=float(signal_payload.get("confidence") or 0.0),
                regime=str(signal_payload.get("regime") or market_state.get("volatility_regime") or "UNKNOWN"),
                strategy_type=str(signal_payload.get("strategy_type") or strategy_id),
                strategy_signal_strength=float(signal_payload.get("strategy_signal_strength") or 0.0),
                strategy_context=signal_payload.get("strategy_context") or {},
                microstructure_result="PASS",
                risk_result="PASS",
                liquidation_result="PASS",
                adl_result="PASS",
                final_decision="REJECT",
                reason_code="SIGNAL_WEAK",
                decision_layer="STRATEGY",
            )
            return {
                "strategy_id": strategy_id,
                "symbol": str(signal_payload.get("symbol") or market_state.get("symbol") or "UNKNOWN"),
                "side": signal_side,
                "confidence": float(signal_payload.get("confidence") or 0.0),
                "regime": str(signal_payload.get("regime") or market_state.get("volatility_regime") or "UNKNOWN"),
                "decision": "REJECT",
                "reason_code": "SIGNAL_WEAK",
                "decision_layer": "STRATEGY",
                "trace": ["signal", "attribution", "decision_trace", "decision_reject"],
                "signal": signal_payload,
                "strategy_type": signal_payload.get("strategy_type", strategy_id),
                "strategy_context": signal_payload.get("strategy_context", {}),
                "decision_trace_model": trace_model,
            }

        latest_price = float(market_state.get("latest_price") or 0.0)
        position = FuturesPosition(
            symbol=str(signal_payload.get("symbol") or market_state.get("symbol") or "UNKNOWN"),
            side=signal_side,
            entry_price=max(latest_price, 0.01),
            mark_price=max(latest_price, 0.01),
            position_size=1.0,
            notional_value=max(latest_price, 0.01),
            leverage=float(risk_snapshot.get("policy_leverage_cap") or 3),
            initial_margin=max(latest_price / 3, 0.01),
            maintenance_margin=max(latest_price * 0.005, 0.01),
            unrealized_pnl=0.0,
            liquidation_price=max(latest_price * 0.9, 0.01),
            margin_ratio=float(risk_snapshot.get("margin_usage") or 0.0),
            distance_to_liquidation=float(risk_snapshot.get("avg_distance_to_liquidation") or 100.0),
        )

        microstructure_by_symbol = risk_snapshot.get("microstructure_by_symbol") or {}
        signal_symbol = str(signal_payload.get("symbol") or market_state.get("symbol") or "UNKNOWN")
        microstructure_result = microstructure_by_symbol.get(signal_symbol) or {
            "gate": {
                "gate_pass": str(market_state.get("spread_state") or "NORMAL").upper() != "SHOCK",
                "gate_reason": "MICROSTRUCTURE_SPREAD_SHOCK"
                if str(market_state.get("spread_state") or "NORMAL").upper() == "SHOCK"
                else "PASS",
                "all_reasons": [],
                "risk_score": 0.0,
            },
            "execution_suitability": {
                "execution_suitable": True,
                "severity": "LOW",
                "max_allowed_size_ratio": 1.0,
                "leverage_cap_override": 5,
                "side_risk": "NONE",
            },
        }

        decision_flow = run_futures_paper_decision_flow(
            signal=signal_payload,
            position=position,
            portfolio_state={
                "portfolio_leverage": float(risk_snapshot.get("portfolio_leverage") or 0.0),
                "margin_usage": float(risk_snapshot.get("margin_usage") or 0.0),
                "distance_to_liquidation": float(risk_snapshot.get("avg_distance_to_liquidation") or 100.0),
            },
            policy_state={
                "cascade_status": str(risk_snapshot.get("cascade_status") or "NONE"),
                "policy_action": str(risk_snapshot.get("policy_action") or "ALLOW"),
                "policy_state": str(risk_snapshot.get("policy_state") or "SAFE"),
                "adl_state": risk_snapshot.get("adl_state") or {},
            },
            funding_bias=market_state.get("funding_bias") or {},
            microstructure_result=microstructure_result,
            strategy_id=strategy_id,
        )

        response = {
            "strategy_id": strategy_id,
            "symbol": signal_symbol,
            "side": signal_side,
            "confidence": float(signal_payload.get("confidence") or 0.0),
            "regime": str(signal_payload.get("regime") or market_state.get("volatility_regime") or "UNKNOWN"),
            "decision": decision_flow["decision"],
            "reason_code": decision_flow["reason_code"],
            "decision_layer": decision_flow.get("decision_layer", "GATE"),
            "strategy_type": signal_payload.get("strategy_type", strategy_id),
            "strategy_context": signal_payload.get("strategy_context", {}),
            "trace": decision_flow["trace"],
            "risk_reason": decision_flow.get("risk", {}).get("risk_reason", []),
            "microstructure_gate": decision_flow.get("gate", {}),
            "liquidation_gate": decision_flow.get("liquidation_gate", {}),
            "adl_gate": decision_flow.get("adl_gate", {}),
            "execution_suitability": decision_flow.get("execution_suitability", {}),
            "leverage_decision": decision_flow.get("leverage_decision", {}),
            "leverage_trace_extension": decision_flow.get("leverage_trace_extension", {}),
            "reasons": decision_flow.get("reasons", []),
            "decision_trace_model": decision_flow.get("decision_trace_model", {}),
            "signal": signal_payload,
        }
        if response["decision"] == "REJECT" and response["reason_code"] == "ALLOW":
            response["reason_code"] = "REJECT_UNCLASSIFIED"
        return response

    def run_cycle(self, *, strategy_id: str, market_states: list[dict], risk_snapshot: dict) -> list[dict]:
        if strategy_id not in self.strategy_registry:
            raise ValueError("strategy_not_registered")
        return [
            self.evaluate_symbol(strategy_id=strategy_id, market_state=market_state, risk_snapshot=risk_snapshot)
            for market_state in market_states
        ]
