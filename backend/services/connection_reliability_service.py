from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


POLICY_PATH = Path("/app/config/connection_reliability_policy.json")
_POLICY_CACHE: dict | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _ensure_positive_int(value, field: str):
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"invalid_policy_field:{field}")


def _ensure_positive_number(value, field: str):
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"invalid_policy_field:{field}")


def _validate_policy(policy: dict) -> dict:
    retry = policy.get("retry") or {}
    health = policy.get("health") or {}
    timeouts = policy.get("http_timeouts") or {}

    _ensure_positive_int(int(retry.get("max_retry_attempts") or 0), "retry.max_retry_attempts")
    _ensure_positive_int(int(retry.get("initial_backoff_seconds") or 0), "retry.initial_backoff_seconds")
    _ensure_positive_int(int(retry.get("max_backoff_seconds") or 0), "retry.max_backoff_seconds")
    _ensure_positive_number(float(retry.get("backoff_multiplier") or 0), "retry.backoff_multiplier")

    liveness = health.get("liveness_interval_seconds") or {}
    _ensure_positive_int(int(liveness.get("testnet") or 0), "health.liveness_interval_seconds.testnet")
    _ensure_positive_int(int(liveness.get("live") or 0), "health.liveness_interval_seconds.live")

    signed = health.get("signed_interval_seconds") or {}
    for env_name in ["testnet", "live"]:
        env_entry = signed.get(env_name) or {}
        _ensure_positive_int(int(env_entry.get("open_position") or 0), f"health.signed_interval_seconds.{env_name}.open_position")
        _ensure_positive_int(int(env_entry.get("idle") or 0), f"health.signed_interval_seconds.{env_name}.idle")

    jitter_seconds = int(health.get("signed_interval_jitter_seconds") or 0)
    if jitter_seconds < 0:
        raise ValueError("invalid_policy_field:health.signed_interval_jitter_seconds")

    _ensure_positive_int(int(health.get("transient_failures_before_reconnect") or 0), "health.transient_failures_before_reconnect")
    _ensure_positive_int(int(health.get("success_resets_failure_count") or 0), "health.success_resets_failure_count")

    for key in ["ping", "exchange_info", "signed_get", "signed_post", "signed_delete", "market_data"]:
        _ensure_positive_number(float(timeouts.get(key) or 0), f"http_timeouts.{key}")

    return policy


def _resolve_runtime_env(raw_payload: dict) -> str:
    selector = raw_payload.get("runtime_env_selector") or {}
    env_keys = selector.get("env_keys") or ["APP_ENV", "ENVIRONMENT"]
    default = str(selector.get("default") or "local").strip().lower()

    selected = ""
    for key in env_keys:
        candidate = str(os.environ.get(str(key), "")).strip().lower()
        if candidate:
            selected = candidate
            break

    normalized = selected or default
    if normalized in {"prod", "production"}:
        return "production"
    if normalized in {"stage", "staging", "preprod"}:
        return "staging"
    return "local"


def load_connection_reliability_policy(*, force_refresh: bool = False) -> dict:
    global _POLICY_CACHE
    if _POLICY_CACHE is not None and not force_refresh:
        return _POLICY_CACHE

    raw_payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    defaults = raw_payload.get("defaults") or {}
    profiles = raw_payload.get("profiles") or {}
    runtime_env = _resolve_runtime_env(raw_payload)
    profile_payload = profiles.get(runtime_env) or {}

    merged = _deep_merge(defaults, profile_payload)
    merged["runtime_env"] = runtime_env
    merged["policy_version"] = str(raw_payload.get("version") or "connection_reliability_policy_v1")
    _POLICY_CACHE = _validate_policy(merged)
    return _POLICY_CACHE


def get_connection_reliability_policy() -> dict:
    return load_connection_reliability_policy(force_refresh=False)


def deterministic_jitter_seconds(*, seed: str, max_abs: int) -> int:
    if max_abs <= 0:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return (value % (2 * max_abs + 1)) - max_abs
