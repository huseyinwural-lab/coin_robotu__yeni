import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.risk.capital.capital_risk_governor import enforce_capital_risk


def test_capital_risk_governor_generates_limit_events():
    allocation = [
        {
            "strategy_id": "trend_follow_v1",
            "strategy_capital_used": 2600,
            "strategy_capital_budget": 2000,
            "risk_state": "LIMIT_HIT",
        }
    ]
    payload = enforce_capital_risk(allocation, [])
    assert payload["capital_risk_actions"][0]["action"] == "REJECT_TRADE"
    assert payload["capital_limit_events"][0]["event"] == "CAPITAL_LIMIT_HIT"
