from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.user_exchange_health_loop as health_loop
from services.connection_reliability_service import (
    deterministic_jitter_seconds,
    load_connection_reliability_policy,
)


def test_reliability_policy_loads_with_valid_runtime_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    policy = load_connection_reliability_policy(force_refresh=True)
    assert policy["runtime_env"] == "staging"
    assert policy["policy_version"].startswith("connection_reliability_policy")
    assert int(policy["retry"]["max_retry_attempts"]) >= 1
    assert int(policy["health"]["signed_interval_seconds"]["testnet"]["idle"]) >= 1


def test_deterministic_jitter_is_stable_for_same_seed():
    one = deterministic_jitter_seconds(seed="conn-123", max_abs=3)
    two = deterministic_jitter_seconds(seed="conn-123", max_abs=3)
    assert one == two
    assert -3 <= one <= 3


def test_retry_schedule_respects_policy_limits():
    policy = {
        "retry": {
            "max_retry_attempts": 4,
            "initial_backoff_seconds": 2,
            "max_backoff_seconds": 9,
            "backoff_multiplier": 2.0,
        }
    }
    snapshot = {"retry_attempt": 3}
    next_attempt, backoff_seconds, next_retry_at = health_loop._retry_schedule(snapshot, policy=policy)
    assert next_attempt == 4
    assert backoff_seconds == 9
    parsed = datetime.fromisoformat(next_retry_at.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_signed_interval_uses_policy_and_jitter(monkeypatch):
    monkeypatch.setattr(
        health_loop,
        "get_connection_reliability_policy",
        lambda: {
            "health": {
                "signed_interval_seconds": {
                    "testnet": {"open_position": 10, "idle": 30},
                    "live": {"open_position": 20, "idle": 40},
                },
                "signed_interval_jitter_seconds": 2,
            }
        },
    )
    value = health_loop._signed_check_interval_seconds(
        environment="testnet",
        has_open_position=False,
        connection_id="conn-a",
    )
    assert 28 <= value <= 32


def test_health_history_deduplicates_same_transition(monkeypatch):
    calls = []

    def _fake_warning(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(health_loop.logger, "warning", _fake_warning)
    snapshot = {}

    health_loop._append_health_history(
        snapshot,
        health="degraded",
        reason="network_error",
        source="unit",
        validation_success=False,
        can_trade=False,
        user_id="u1",
        connection_id="c1",
    )
    health_loop._append_health_history(
        snapshot,
        health="degraded",
        reason="network_error",
        source="unit",
        validation_success=False,
        can_trade=False,
        user_id="u1",
        connection_id="c1",
    )

    history = snapshot.get("health_history") or []
    assert len(history) == 1
    assert len(calls) == 1


def test_health_history_records_state_change(monkeypatch):
    calls = []

    def _fake_warning(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(health_loop.logger, "warning", _fake_warning)
    snapshot = {}

    health_loop._append_health_history(
        snapshot,
        health="degraded",
        reason="network_error",
        source="unit",
        validation_success=False,
        can_trade=False,
        user_id="u1",
        connection_id="c1",
    )
    health_loop._append_health_history(
        snapshot,
        health="online",
        reason="none",
        source="unit",
        validation_success=True,
        can_trade=True,
        user_id="u1",
        connection_id="c1",
    )

    history = snapshot.get("health_history") or []
    assert len(history) == 2
    assert len(calls) == 2
    assert history[-1]["health"] == "online"
