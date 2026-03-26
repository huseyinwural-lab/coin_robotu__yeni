import json
import os
from pathlib import Path


CONFIG_PATH = Path("/app/backend/config/runtime_alert_thresholds.json")

DEFAULTS = {
    "net_pnl_drop_pct": 5.0,
    "failed_orders_window": 20,
    "failed_orders_threshold": 4,
    "queue_depth_threshold": 30,
    "smoke_degraded_repeat_threshold": 2,
    "execution_latency_ms_threshold": 1200,
}

ENV_KEYS = {
    "net_pnl_drop_pct": "RUNTIME_THRESHOLD_NET_PNL_DROP_PCT",
    "failed_orders_window": "RUNTIME_THRESHOLD_FAILED_ORDERS_WINDOW",
    "failed_orders_threshold": "RUNTIME_THRESHOLD_FAILED_ORDERS_THRESHOLD",
    "queue_depth_threshold": "RUNTIME_THRESHOLD_QUEUE_DEPTH",
    "smoke_degraded_repeat_threshold": "RUNTIME_THRESHOLD_SMOKE_DEGRADED_REPEAT",
    "execution_latency_ms_threshold": "RUNTIME_THRESHOLD_EXECUTION_LATENCY_MS",
}


def _cast_value(key: str, value):
    if key in {"net_pnl_drop_pct"}:
        return float(value)
    return int(value)


def get_runtime_alert_thresholds() -> dict:
    merged = dict(DEFAULTS)

    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            for key, value in payload.items():
                if key in merged and value is not None:
                    merged[key] = _cast_value(key, value)

    for key, env_key in ENV_KEYS.items():
        raw = os.environ.get(env_key)
        if raw is not None and str(raw).strip() != "":
            merged[key] = _cast_value(key, raw)

    return merged
