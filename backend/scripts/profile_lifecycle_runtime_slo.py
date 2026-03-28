from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import SessionLocal
from services.trading_lifecycle_debugger_service import get_lifecycle_chain, list_lifecycle_summaries


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(max(int(round((len(ordered) - 1) * q)), 0), len(ordered) - 1)
    return ordered[idx]


def run_runtime_profile(output_path: str = "/app/test_reports/p1_runtime_profile_report.json") -> dict:
    db = SessionLocal()
    try:
        list_samples: list[float] = []
        detail_samples: list[float] = []

        sample_correlation_id = None
        for _ in range(20):
            started = time.perf_counter()
            response = list_lifecycle_summaries(
                db,
                limit=100,
                environment="prod",
                include_test_events=False,
            )
            elapsed = (time.perf_counter() - started) * 1000
            list_samples.append(round(elapsed, 2))
            if not sample_correlation_id and response.get("items"):
                sample_correlation_id = response["items"][0].get("correlation_id")

        if sample_correlation_id:
            for _ in range(10):
                started = time.perf_counter()
                get_lifecycle_chain(db, sample_correlation_id, limit=1200, environment="prod")
                detail_samples.append(round((time.perf_counter() - started) * 1000, 2))

        report = {
            "type": "runtime_profile",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sample_correlation_id": sample_correlation_id,
            "list_lifecycle": {
                "samples_ms": list_samples,
                "p50_ms": round(_quantile(list_samples, 0.50), 2),
                "p95_ms": round(_quantile(list_samples, 0.95), 2),
                "avg_ms": round(statistics.mean(list_samples), 2) if list_samples else 0.0,
            },
            "lifecycle_detail": {
                "samples_ms": detail_samples,
                "p50_ms": round(_quantile(detail_samples, 0.50), 2),
                "p95_ms": round(_quantile(detail_samples, 0.95), 2),
                "avg_ms": round(statistics.mean(detail_samples), 2) if detail_samples else 0.0,
            },
            "slo_target_ms": 2000,
            "slo_pass": (_quantile(list_samples, 0.95) < 2000 and _quantile(detail_samples, 0.95) < 2000),
        }

        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)

        return report
    finally:
        db.close()


if __name__ == "__main__":
    print(json.dumps(run_runtime_profile(), ensure_ascii=False, indent=2))
