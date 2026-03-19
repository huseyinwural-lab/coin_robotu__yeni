# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.audit.audit_events import AuditEvent
from services.audit_service import create_audit_log
from services.execution_precheck_service import validate_execution_payload


class _DummyDbSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def refresh(self, _item):
        return None


def test_audit_event_enum_contains_faz4_chain_events():
    expected = {
        "SCAN_RESULT",
        "RISK_RESULT",
        "EXECUTION_INTENT",
        "ORDER_PREFLIGHT",
        "EXCHANGE_ORDER",
        "SYMBOL_INTEGRITY_REJECT",
    }
    actual = {item.value for item in AuditEvent}
    assert expected.issubset(actual)


def test_execution_precheck_emits_order_preflight_event_code():
    payload = {
        "symbol": "ETHUSDT",
        "market_type": "spot",
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 20,
        "execution_mode": "manual",
    }
    result = validate_execution_payload(payload)
    assert result["preflight_event_code"] == AuditEvent.ORDER_PREFLIGHT.value


def test_create_audit_log_accepts_enum_action_value():
    db = _DummyDbSession()
    row = create_audit_log(
        db,
        action=AuditEvent.SCAN_RESULT,
        entity_type="scanner_runtime",
        entity_id="scan-1",
        actor_user_id="user-1",
        actor_role="user",
        details={"decision_count": 3},
    )
    assert row.action == AuditEvent.SCAN_RESULT.value
    assert db.committed is True
    assert isinstance(db.added[0], type(row))
