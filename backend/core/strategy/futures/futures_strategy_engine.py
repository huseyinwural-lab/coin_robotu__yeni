from dataclasses import asdict

from core.futures.adl.adl_gate import ADLGate
from core.futures.liquidation_protection.liquidation_gate import LiquidationGate
from core.futures.position_model import FuturesPosition
from core.risk.futures_risk_engine import evaluate_futures_risk
from core.strategy.futures.strategy_contract import FuturesStrategy


class FuturesStrategyEngine:
    def __init__(self, strategy_registry: dict[str, FuturesStrategy]):
        self.strategy_registry = strategy_registry
        self.liquidation_gate = LiquidationGate()
        self.adl_gate = ADLGate()

    def evaluate_symbol(self, *, strategy_id: str, market_state: dict, risk_snapshot: dict) -> dict:
        strategy = self.strategy_registry[strategy_id]
        signal = strategy.generate_signal(market_state)
        signal_payload = asdict(signal)

        if signal.side == "NONE":
            return {
                "strategy_id": strategy_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "regime": signal.regime,
                "decision": "REJECT",
                "reason_code": signal.reason,
                "trace": ["strategy_signal", "decision_reject"],
                "signal": signal_payload,
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

        microstructure_reject = str(market_state.get("spread_state") or "NORMAL").upper() == "SHOCK"
        if microstructure_reject:
            return {
                "strategy_id": strategy_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "regime": signal.regime,
                "decision": "REJECT",
                "reason_code": "MICROSTRUCTURE_SPREAD_SHOCK",
                "trace": ["strategy_signal", "microstructure_guard", "decision_reject"],
                "signal": signal_payload,
            }

        risk_result = evaluate_futures_risk(
            position,
            {
                "portfolio_leverage": float(risk_snapshot.get("portfolio_leverage") or 0.0),
                "margin_usage": float(risk_snapshot.get("margin_usage") or 0.0),
                "distance_to_liquidation": float(risk_snapshot.get("avg_distance_to_liquidation") or 100.0),
            },
        )
        if risk_result["risk_check_result"] == "reject":
            return {
                "strategy_id": strategy_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "regime": signal.regime,
                "decision": "REJECT",
                "reason_code": "RISK_ENGINE_REJECT",
                "risk_reason": risk_result.get("risk_reason", []),
                "trace": ["strategy_signal", "microstructure_guard", "risk_engine", "decision_reject"],
                "signal": signal_payload,
            }

        liquidation_gate = self.liquidation_gate.evaluate(
            distance_to_liquidation=float(risk_snapshot.get("avg_distance_to_liquidation") or 100.0),
            margin_usage=float(risk_snapshot.get("margin_usage") or 0.0),
            cascade_confirmed=str(risk_snapshot.get("cascade_status") or "NONE").upper() == "CASCADE_CONFIRMED",
            emergency_policy_active=str(risk_snapshot.get("policy_action") or "ALLOW").upper() in {"FREEZE", "FORCE_REDUCE"},
            leverage=float(risk_snapshot.get("policy_leverage_cap") or 3),
            leverage_cap=float(risk_snapshot.get("policy_leverage_cap") or 3),
        )
        if not liquidation_gate["gate_pass"]:
            return {
                "strategy_id": strategy_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "regime": signal.regime,
                "decision": "REJECT",
                "reason_code": liquidation_gate["gate_reason"],
                "trace": ["strategy_signal", "microstructure_guard", "risk_engine", "liquidation_gate", "decision_reject"],
                "signal": signal_payload,
            }

        adl_state = risk_snapshot.get("adl_state", {})
        adl_gate = self.adl_gate.evaluate(
            adl_risk_level=str(adl_state.get("risk_level") or "LOW"),
            adl_pressure_side=str(adl_state.get("dominant_side") or "NONE"),
            portfolio_adl_risk=float(adl_state.get("portfolio_adl_risk") or 0.0),
            trade_side=signal.side,
        )
        if not adl_gate["adl_gate_pass"]:
            return {
                "strategy_id": strategy_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "regime": signal.regime,
                "decision": "REJECT",
                "reason_code": adl_gate["reason"],
                "trace": [
                    "strategy_signal",
                    "microstructure_guard",
                    "risk_engine",
                    "liquidation_gate",
                    "adl_gate",
                    "decision_reject",
                ],
                "signal": signal_payload,
            }

        policy_state = str(risk_snapshot.get("policy_state") or "SAFE").upper()
        if policy_state in {"CRITICAL", "EMERGENCY"}:
            return {
                "strategy_id": strategy_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "regime": signal.regime,
                "decision": "REJECT",
                "reason_code": f"POLICY_{policy_state}",
                "trace": [
                    "strategy_signal",
                    "microstructure_guard",
                    "risk_engine",
                    "liquidation_gate",
                    "adl_gate",
                    "policy_engine",
                    "decision_reject",
                ],
                "signal": signal_payload,
            }

        return {
            "strategy_id": strategy_id,
            "symbol": signal.symbol,
            "side": signal.side,
            "confidence": signal.confidence,
            "regime": signal.regime,
            "decision": "ALLOW",
            "reason_code": "ALLOW",
            "trace": [
                "strategy_signal",
                "microstructure_guard",
                "risk_engine",
                "liquidation_gate",
                "adl_gate",
                "policy_engine",
                "paper_decision_allow",
            ],
            "signal": signal_payload,
        }

    def run_cycle(self, *, strategy_id: str, market_states: list[dict], risk_snapshot: dict) -> list[dict]:
        if strategy_id not in self.strategy_registry:
            raise ValueError("strategy_not_registered")
        return [
            self.evaluate_symbol(strategy_id=strategy_id, market_state=market_state, risk_snapshot=risk_snapshot)
            for market_state in market_states
        ]
