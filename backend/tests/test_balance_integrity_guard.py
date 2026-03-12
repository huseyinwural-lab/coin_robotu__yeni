import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.live.balance_integrity_guard import validate_balance_integrity


def test_balance_integrity_guard_emits_alert_on_mismatch():
    payload = validate_balance_integrity(
        {"wallet_balance": 10000, "available_balance": 8000, "used_margin": 2000},
        {"wallet_balance": 9800, "available_balance": 7900, "used_margin": 1900},
    )
    assert payload["balance_integrity_state"] == "ALERT"
    assert payload["event"]["event"] == "BALANCE_INTEGRITY_ALERT"
