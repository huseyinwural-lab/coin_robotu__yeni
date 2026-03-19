# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.observability.strategy_governance_audit import build_strategy_governance_audit_events


def test_governance_audit_schema_contains_required_fields():
    events = build_strategy_governance_audit_events(
        health_rows=[{"strategy": "trend_follow_v1", "strategy_health_score": 42}],
        decay_events=[{"strategy": "trend_follow_v1", "decay_reason_codes": ["PNL_DETERIORATION"]}],
        throttle_rows=[{"strategy": "trend_follow_v1", "throttle_level": "L2"}],
        disable_events=[],
        lifecycle_transitions=[{"strategy": "trend_follow_v1", "to": "THROTTLED", "reason": "THROTTLE_L2"}],
    )
    assert len(events) >= 2
    for event in events:
        assert "event" in event
        assert "strategy" in event
        assert "trigger_reason" in event
        assert "health_snapshot" in event
        assert "throttle_state" in event
        assert "lifecycle_state" in event
