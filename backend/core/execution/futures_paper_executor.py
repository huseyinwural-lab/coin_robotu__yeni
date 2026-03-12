from datetime import datetime, timezone


class FuturesPaperExecutor:
    def simulate(self, *, strategy_signal: dict, market_state: dict) -> dict:
        side = str(strategy_signal.get("side") or "NONE").upper()
        if side not in {"LONG", "SHORT"}:
            return {
                "paper_position_opened": False,
                "paper_position_closed": False,
                "paper_pnl": 0.0,
                "reason": "NO_ACTION_SIGNAL",
                "events": [],
            }

        mark_price = max(float(market_state.get("latest_price") or 0.0), 0.01)
        spread_bps = float(market_state.get("spread_bps") or 0.0)
        trend_strength = float(market_state.get("trend_strength") or 0.0)
        confidence = float(strategy_signal.get("confidence") or 0.0)

        expected_slippage_bps = max(1.0, round(spread_bps * 0.35, 4))
        slippage_factor = expected_slippage_bps / 10_000
        synthetic_entry_price = mark_price * (1 + slippage_factor if side == "LONG" else 1 - slippage_factor)

        exit_reason = "stop_loss"
        exit_move = -0.003
        if trend_strength <= 0.0015:
            exit_reason = "trend_weaken"
            exit_move = -0.0015
        elif confidence >= 0.75:
            exit_reason = "profit_target"
            exit_move = 0.0045

        if side == "LONG":
            synthetic_exit_price = synthetic_entry_price * (1 + exit_move)
            paper_pnl = synthetic_exit_price - synthetic_entry_price
        else:
            synthetic_exit_price = synthetic_entry_price * (1 - exit_move)
            paper_pnl = synthetic_entry_price - synthetic_exit_price

        lifecycle = ["paper_position_opened", "paper_position_closed"]
        now = datetime.now(timezone.utc).isoformat()
        return {
            "paper_position_opened": True,
            "paper_position_closed": True,
            "paper_pnl": round(paper_pnl, 6),
            "entry_price": round(synthetic_entry_price, 6),
            "exit_price": round(synthetic_exit_price, 6),
            "expected_slippage_bps": expected_slippage_bps,
            "exit_reason": exit_reason,
            "lifecycle": lifecycle,
            "events": [
                {"event": "paper_position_opened", "ts": now, "price": round(synthetic_entry_price, 6)},
                {"event": "paper_position_closed", "ts": now, "price": round(synthetic_exit_price, 6)},
            ],
        }
