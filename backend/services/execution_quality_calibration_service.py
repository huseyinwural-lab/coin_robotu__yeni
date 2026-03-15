from __future__ import annotations

from datetime import datetime, timezone
from itertools import product

from models import ExecutionMetric, TestnetExecutionLog, UserExecutionIntent
from services.execution_quality_service import evaluate_execution_quality
from services.pipeline.cache_store import get_json, set_json


EXEC_QUALITY_CALIBRATION_CACHE_KEY = "risk:execution_quality:calibration:latest"


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rate_from_metrics(rows: list[ExecutionMetric]) -> tuple[float, float]:
    sample = max(len(rows), 1)
    partial_fill_count = sum(1 for item in rows if str(item.final_status or "").upper() in {"PARTIALLY_FILLED", "PARTIAL_FILL"})
    reject_count = sum(1 for item in rows if str(item.final_status or "").upper() in {"REJECTED", "FAILED", "CANCELED", "EXPIRED"})
    return partial_fill_count / sample, reject_count / sample


def _ground_truth_action(row: dict) -> str:
    quality_label = str(row.get("quality_label") or "normal")
    if quality_label == "severe":
        return "BLOCK"
    if quality_label == "medium":
        return "PASS"
    if quality_label == "mild":
        return "REDUCE_SIZE"
    return "ALLOW"


def _build_quality_label(*, slippage_pct: float, execution_latency_ms: float, final_status: str, reject_codes: list[str]) -> str:
    status = str(final_status or "").upper()
    if status in {"FAILED", "REJECTED"}:
        return "severe"
    if status in {"CANCELED", "EXPIRED"}:
        return "medium"
    if status in {"PARTIALLY_FILLED", "PARTIAL_FILL"}:
        return "mild"
    if slippage_pct >= 1.2 or execution_latency_ms >= 7000:
        return "severe"
    if slippage_pct >= 0.7 or execution_latency_ms >= 3500:
        return "medium"
    if reject_codes:
        return "mild"
    return "normal"


def build_execution_quality_replay_dataset(db, *, sample_size: int = 400) -> dict:
    execution_rows = (
        db.query(ExecutionMetric)
        .order_by(ExecutionMetric.created_at.desc())
        .limit(sample_size)
        .all()
    )
    intent_rows = (
        db.query(UserExecutionIntent)
        .order_by(UserExecutionIntent.created_at.desc())
        .limit(sample_size)
        .all()
    )
    fallback_rows = (
        db.query(TestnetExecutionLog)
        .order_by(TestnetExecutionLog.created_at.desc())
        .limit(max(20, min(sample_size, 200)))
        .all()
    )

    partial_fill_rate, reject_rate = _rate_from_metrics(execution_rows)
    samples: list[dict] = []
    for row in execution_rows:
        normalized_payload = {}
        bridge_context = {}
        fallback_reject_codes: list[str] = []
        symbol = str(row.symbol or "").upper().strip()
        for intent in intent_rows:
            if str(intent.symbol or "").upper().strip() == symbol:
                normalized_payload = intent.normalized_order_payload or {}
                bridge_context = normalized_payload.get("signal_bridge_context") or {}
                fallback_reject_codes = [str(item) for item in (intent.reject_reason_codes or []) if str(item).strip()]
                break

        snapshot_age_ms = _to_float(bridge_context.get("snapshot_age_ms"), 0.0)
        spread_bps = _to_float((bridge_context.get("spread") or {}).get("spread_bps"), 0.0)
        if spread_bps <= 0:
            spread_bps = _to_float(normalized_payload.get("spread_bps"), 0.0)
        slippage_pct = _to_float(row.slippage_pct, 0.0)
        execution_latency_ms = _to_float(row.execution_time_ms, 0.0)
        orderbook_depth = _to_float(bridge_context.get("orderbook_depth_score"), 1.0)
        status = str(row.final_status or row.status or "").upper()

        quality_label = _build_quality_label(
            slippage_pct=slippage_pct,
            execution_latency_ms=execution_latency_ms,
            final_status=status,
            reject_codes=fallback_reject_codes,
        )
        samples.append(
            {
                "snapshot_age_ms": snapshot_age_ms,
                "spread_bps": spread_bps,
                "slippage_pct": slippage_pct,
                "execution_latency_ms": execution_latency_ms,
                "orderbook_depth": orderbook_depth,
                "partial_fill_rate": partial_fill_rate,
                "reject_rate": reject_rate,
                "quality_label": quality_label,
                "status": status,
                "reject_reason_codes": fallback_reject_codes,
            }
        )

    if not samples:
        for row in fallback_rows:
            status = str(row.status or "").upper()
            slippage_pct = abs(_to_float(row.slippage, 0.0) / max(_to_float(row.expected_price, 1.0), 1e-6)) * 100.0
            execution_latency_ms = _to_float(row.execution_latency, 0.0)
            quality_label = _build_quality_label(
                slippage_pct=slippage_pct,
                execution_latency_ms=execution_latency_ms,
                final_status=status,
                reject_codes=[],
            )
            samples.append(
                {
                    "snapshot_age_ms": 0.0,
                    "spread_bps": 0.0,
                    "slippage_pct": slippage_pct,
                    "execution_latency_ms": execution_latency_ms,
                    "orderbook_depth": 1.0,
                    "partial_fill_rate": 0.0,
                    "reject_rate": 0.0,
                    "quality_label": quality_label,
                    "status": status,
                    "reject_reason_codes": [],
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(samples),
        "samples": samples,
        "data_sources": {
            "execution_logs": len(execution_rows),
            "decision_logs": len(intent_rows),
            "risk_veto_logs": sum(1 for item in intent_rows if str(item.gate_decision or "").upper() in {"PASS", "BLOCK"}),
            "fallback_execution_logs": len(fallback_rows),
        },
    }


def calibrate_execution_quality_thresholds(db, cache, *, sample_size: int = 400) -> dict:
    dataset = build_execution_quality_replay_dataset(db, sample_size=sample_size)
    samples = dataset.get("samples") or []

    if not samples:
        payload = {
            "status": "policy_documented_warning",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": dataset,
            "false_allow_rate": 0.0,
            "false_block_rate": 0.0,
            "false_reduce_rate": 0.0,
            "recommended_thresholds": {
                "execution_quality_threshold": 65.0,
                "spread_threshold_bps": 30.0,
                "stale_data_threshold_ms": 120_000,
            },
            "evaluation_notes": {
                "policy_reason": "insufficient_execution_logs",
                "policy_based_warning_ok": True,
            },
        }
        set_json(cache, EXEC_QUALITY_CALIBRATION_CACHE_KEY, payload)
        return payload

    threshold_grid = {
        "execution_quality_threshold": [55.0, 60.0, 65.0, 70.0, 75.0],
        "spread_threshold_bps": [20.0, 25.0, 30.0, 35.0, 40.0],
        "stale_data_threshold_ms": [60_000, 90_000, 120_000, 150_000],
    }

    best = None
    best_error = float("inf")
    comparisons = []
    for quality_threshold, spread_threshold, stale_threshold in product(
        threshold_grid["execution_quality_threshold"],
        threshold_grid["spread_threshold_bps"],
        threshold_grid["stale_data_threshold_ms"],
    ):
        false_allow = 0
        false_block = 0
        false_reduce = 0

        for row in samples:
            predicted = evaluate_execution_quality(
                snapshot_age_ms=_to_float(row.get("snapshot_age_ms"), 0.0),
                spread_bps=_to_float(row.get("spread_bps"), 0.0),
                slippage_pct=_to_float(row.get("slippage_pct"), 0.0),
                execution_latency_ms=_to_float(row.get("execution_latency_ms"), 0.0),
                orderbook_depth_score=_to_float(row.get("orderbook_depth"), 1.0),
                partial_fill_rate=_to_float(row.get("partial_fill_rate"), 0.0),
                reject_rate=_to_float(row.get("reject_rate"), 0.0),
                stale_threshold_ms=stale_threshold,
                spread_threshold_bps=spread_threshold,
                max_slippage_pct=0.8,
                execution_quality_threshold=quality_threshold,
            ).get("recommendation")
            expected = _ground_truth_action(row)

            if predicted == "ALLOW" and expected in {"PASS", "BLOCK"}:
                false_allow += 1
            if predicted == "BLOCK" and expected in {"ALLOW", "REDUCE_SIZE"}:
                false_block += 1
            if predicted == "REDUCE_SIZE" and expected == "ALLOW":
                false_reduce += 1

        sample = max(len(samples), 1)
        false_allow_rate = false_allow / sample
        false_block_rate = false_block / sample
        false_reduce_rate = false_reduce / sample
        weighted_error = false_allow_rate * 0.45 + false_block_rate * 0.35 + false_reduce_rate * 0.20

        candidate = {
            "execution_quality_threshold": quality_threshold,
            "spread_threshold_bps": spread_threshold,
            "stale_data_threshold_ms": stale_threshold,
            "false_allow_rate": round(false_allow_rate, 6),
            "false_block_rate": round(false_block_rate, 6),
            "false_reduce_rate": round(false_reduce_rate, 6),
            "weighted_error": round(weighted_error, 6),
        }
        comparisons.append(candidate)
        if weighted_error < best_error:
            best_error = weighted_error
            best = candidate

    best = best or {
        "execution_quality_threshold": 65.0,
        "spread_threshold_bps": 30.0,
        "stale_data_threshold_ms": 120_000,
        "false_allow_rate": 0.0,
        "false_block_rate": 0.0,
        "false_reduce_rate": 0.0,
        "weighted_error": 0.0,
    }
    payload = {
        "status": "calibrated",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "sample_size": len(samples),
            "data_sources": dataset.get("data_sources") or {},
        },
        "false_allow_rate": best["false_allow_rate"],
        "false_block_rate": best["false_block_rate"],
        "false_reduce_rate": best["false_reduce_rate"],
        "recommended_thresholds": {
            "execution_quality_threshold": best["execution_quality_threshold"],
            "spread_threshold_bps": best["spread_threshold_bps"],
            "stale_data_threshold_ms": best["stale_data_threshold_ms"],
        },
        "evaluation_notes": {
            "search_candidates": len(comparisons),
            "best_weighted_error": best["weighted_error"],
            "policy_based_warning_ok": best["false_allow_rate"] <= 0.10,
        },
        "top_candidates": sorted(comparisons, key=lambda item: float(item["weighted_error"]))[:5],
    }
    set_json(cache, EXEC_QUALITY_CALIBRATION_CACHE_KEY, payload)
    return payload


def get_latest_execution_quality_calibration(cache) -> dict:
    return get_json(cache, EXEC_QUALITY_CALIBRATION_CACHE_KEY) or {
        "status": "not_run",
        "generated_at": None,
        "recommended_thresholds": {},
    }
