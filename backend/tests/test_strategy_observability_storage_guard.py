# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.strategy_observability_service import (
    _resolve_max_events_per_cycle,
    log_strategy_observability_events,
)


class _FakeDB:
    def __init__(self):
        self.rows = []
        self.committed = False

    def add_all(self, rows):
        self.rows.extend(rows)

    def commit(self):
        self.committed = True


def _candidate(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "strategy_id": "spot_pullback_v1",
        "strategy_name": "SPOT_PULLBACK",
        "market_regime": "ranging",
        "multiplier_version": "v1",
        "multiplier_set": {"base": 1.0},
        "base_score": 60.0,
        "adjusted_score": 61.0,
        "score_delta": 1.0,
        "trend_strength": "medium",
        "relative_volume": 1.2,
        "hard_gate_pass": True,
        "threshold_pass": True,
        "reason_codes": [],
        "component_scores": {},
        "metadata": {},
    }


def test_resolve_max_events_per_cycle_clamps_value(monkeypatch):
    monkeypatch.setenv("STRATEGY_OBSERVABILITY_MAX_EVENTS_PER_CYCLE", "25")
    assert _resolve_max_events_per_cycle() == 50

    monkeypatch.setenv("STRATEGY_OBSERVABILITY_MAX_EVENTS_PER_CYCLE", "2500")
    assert _resolve_max_events_per_cycle() == 2000

    monkeypatch.setenv("STRATEGY_OBSERVABILITY_MAX_EVENTS_PER_CYCLE", "300")
    assert _resolve_max_events_per_cycle() == 300


def test_log_strategy_observability_events_keeps_selected_outside_cap(monkeypatch):
    monkeypatch.setenv("STRATEGY_OBSERVABILITY_MAX_EVENTS_PER_CYCLE", "50")
    db = _FakeDB()

    ranked = [_candidate(f"SYM{i}USDT") for i in range(1, 71)]
    selected = [{"symbol": "SYM70USDT", "selection_rank": 1}]

    log_strategy_observability_events(
        db,
        selection_cycle_id="cycle-1",
        audit_log_id="audit-1",
        bot_profile_id="bot-1",
        user_id="user-1",
        strategy_id="spot_pullback_v1",
        strategy_name="SPOT_PULLBACK",
        market_regime="ranging",
        multiplier_version="v1",
        multiplier_set={"base": 1.0},
        ranked=ranked,
        selected=selected,
    )

    symbols = {row.symbol for row in db.rows}
    assert db.committed is True
    assert len(db.rows) == 51
    assert "SYM70USDT" in symbols
    assert any((row.event_metadata or {}).get("sampling", {}).get("truncated") is True for row in db.rows)
