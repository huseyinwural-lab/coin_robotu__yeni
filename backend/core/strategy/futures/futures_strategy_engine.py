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
        signal = strategy.generate_signal(market_state)
        signal_payload = asdict(signal)

        if signal.side == "NONE":
            trace_model = build_decision_trace(
                symbol=signal.symbol,
                strategy=strategy_id,
                side=signal.side,
                signal_confidence=signal.confidence,
                regime=signal.regime,
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
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "regime": signal.regime,
                "decision": "REJECT",
                "reason_code": "SIGNAL_WEAK",
                "decision_layer": "STRATEGY",
                "trace": ["signal", "attribution", "decision_trace", "decision_reject"],
                "signal": signal_payload,
                "decision_trace_model": trace_model,
            }

        latest_price = float(market_state.get("latest_price") or 0.0)
        position = FuturesPosition(
            symbol=signal.symbol,
            side=signal.side,
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
        microstructure_result = microstructure_by_symbol.get(signal.symbol) or {
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
            "symbol": signal.symbol,
            "side": signal.side,
            "confidence": signal.confidence,
            "regime": signal.regime,
            "decision": decision_flow["decision"],
            "reason_code": decision_flow["reason_code"],
            "decision_layer": decision_flow.get("decision_layer", "GATE"),
            "trace": decision_flow["trace"],
            "risk_reason": decision_flow.get("risk", {}).get("risk_reason", []),
            "microstructure_gate": decision_flow.get("gate", {}),
            "liquidation_gate": decision_flow.get("liquidation_gate", {}),
            "adl_gate": decision_flow.get("adl_gate", {}),
            "execution_suitability": decision_flow.get("execution_suitability", {}),
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
