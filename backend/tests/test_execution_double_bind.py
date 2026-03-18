import inspect
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from routers import user_platform
from services import execution_intent_service


def test_execution_service_has_guard_and_precheck_calls():
    source = inspect.getsource(execution_intent_service.submit_execution_intent)
    assert "enforce_execution_guard_or_raise" in source
    assert "validate_order_precheck" in source


def test_user_trade_entry_path_has_double_bind_calls():
    source = inspect.getsource(user_platform._submit_trade_with_guard)
    assert "enforce_execution_guard_or_raise" in source
    assert "validate_order_precheck" in source
