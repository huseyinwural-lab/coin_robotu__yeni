# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.futures_retry_policy import FuturesRetryPolicy


def test_retry_policy_timeout_is_retryable():
    policy = FuturesRetryPolicy()
    decision = policy.classify("TIMEOUT")
    assert decision["should_retry"] is True
    assert policy.next_backoff_seconds(2, "TIMEOUT") > 0


def test_retry_policy_duplicate_is_reconcile():
    policy = FuturesRetryPolicy()
    decision = policy.classify("DUPLICATE_CLIENT_ORDER")
    assert decision["action"] == "reconcile"
    assert policy.next_backoff_seconds(1, "DUPLICATE_CLIENT_ORDER") == 0
