from __future__ import annotations

import json
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = BACKEND_ROOT / "config"

POLICY_FILES = {
    "latency_config": CONFIG_ROOT / "latency_config.json",
    "timeout_policy": CONFIG_ROOT / "timeout_policy.json",
    "data_quality_config": CONFIG_ROOT / "readiness_data_quality_config.json",
    "exposure_policy": CONFIG_ROOT / "exposure_policy.json",
    "runbook_mapping": CONFIG_ROOT / "readiness_runbook_mapping.json",
}


def _read_json(path: Path, default: dict | list | None = None):
    fallback = default if default is not None else {}
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, (dict, list)):
                return payload
    except Exception:
        return fallback
    return fallback


def _merge_dict(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged.get(key) or {}, value)
        else:
            merged[key] = value
    return merged


def _write_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_readiness_policy() -> dict:
    return {key: _read_json(path, {}) for key, path in POLICY_FILES.items()}


def update_readiness_policy(patch_payload: dict) -> dict:
    if not isinstance(patch_payload, dict):
        raise ValueError("invalid_policy_payload")

    updated = {}
    for key, path in POLICY_FILES.items():
        if key not in patch_payload:
            updated[key] = _read_json(path, {})
            continue

        existing = _read_json(path, {})
        patch = patch_payload.get(key)
        if isinstance(existing, dict) and isinstance(patch, dict):
            merged = _merge_dict(existing, patch)
        else:
            merged = patch
        _write_json(path, merged)
        updated[key] = merged

    return updated
