from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import engine


def run_seeded_benchmark(rows: int, output_path: str) -> dict:
    started = time.perf_counter()

    with engine.begin() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(sa.text("DROP TABLE IF EXISTS benchmark_audit_logs"))
        conn.execute(
            sa.text(
                """
                CREATE UNLOGGED TABLE benchmark_audit_logs (
                    id TEXT PRIMARY KEY,
                    actor_user_id TEXT,
                    actor_role TEXT,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    strategy_id TEXT,
                    symbol TEXT,
                    user_id TEXT,
                    event_type TEXT,
                    payload_text TEXT,
                    is_test_event BOOLEAN NOT NULL DEFAULT FALSE,
                    previous_event_hash TEXT,
                    event_hash TEXT,
                    signature_version TEXT NOT NULL DEFAULT 'v1',
                    details JSON NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        )

        insert_sql = sa.text(
            """
            INSERT INTO benchmark_audit_logs (
                id, actor_user_id, actor_role, action, entity_type, entity_id,
                severity, environment, strategy_id, symbol, user_id, event_type, payload_text, is_test_event, previous_event_hash,
                event_hash, signature_version, details, created_at
            )
            SELECT
                md5((gs::text || '-' || clock_timestamp()::text)),
                NULL,
                'system',
                CASE WHEN gs % 15 = 0 THEN 'EXECUTION_FAILED' ELSE 'REQUEST_RECEIVED' END,
                'trade_lifecycle',
                'bench-corr-' || (gs % 25000),
                CASE WHEN gs % 20 = 0 THEN 'CRITICAL' WHEN gs % 7 = 0 THEN 'ERROR' ELSE 'INFO' END,
                CASE
                    WHEN gs % 10 = 0 THEN 'staging'
                    WHEN gs % 13 = 0 THEN 'canary'
                    WHEN gs % 17 = 0 THEN 'test'
                    ELSE 'prod'
                END,
                'strat-' || (gs % 300),
                CASE WHEN gs % 2 = 0 THEN 'BTCUSDT' ELSE 'ETHUSDT' END,
                'user-' || (gs % 5000),
                CASE WHEN gs % 9 = 0 THEN 'execution' ELSE 'request' END,
                CASE WHEN gs % 20 = 0 THEN 'exchange timeout while placing order' ELSE 'ok event payload' END,
                CASE WHEN gs % 17 = 0 OR gs % 13 = 0 THEN TRUE ELSE FALSE END,
                NULL,
                md5((gs::text || '-hash')),
                'v1',
                json_build_object(
                    'correlation_id', 'bench-corr-' || (gs % 25000),
                    'strategy_id', 'strat-' || (gs % 300),
                    'symbol', CASE WHEN gs % 2 = 0 THEN 'BTCUSDT' ELSE 'ETHUSDT' END,
                    'user_id', 'user-' || (gs % 5000),
                    'event_type', CASE WHEN gs % 9 = 0 THEN 'execution' ELSE 'request' END,
                    'environment', CASE
                        WHEN gs % 10 = 0 THEN 'staging'
                        WHEN gs % 13 = 0 THEN 'canary'
                        WHEN gs % 17 = 0 THEN 'test'
                        ELSE 'prod'
                    END,
                    'reason_codes', CASE WHEN gs % 20 = 0 THEN json_build_array('exchange_timeout') ELSE json_build_array() END,
                    'payload_text', CASE WHEN gs % 20 = 0 THEN 'exchange timeout while placing order' ELSE 'ok event payload' END
                ),
                (NOW() - (gs || ' milliseconds')::interval)
            FROM generate_series(1, :rows) AS gs
            """
        )
        conn.execute(insert_sql, {"rows": rows})

        conn.execute(sa.text("CREATE INDEX ix_bench_audit_created_desc ON benchmark_audit_logs (created_at DESC)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_env ON benchmark_audit_logs (environment)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_severity ON benchmark_audit_logs (severity)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_test_flag ON benchmark_audit_logs (is_test_event)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_strategy ON benchmark_audit_logs (strategy_id)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_symbol ON benchmark_audit_logs (symbol)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_user ON benchmark_audit_logs (user_id)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_event_type ON benchmark_audit_logs (event_type)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_details_trgm ON benchmark_audit_logs USING GIN ((COALESCE(details::text, '')) gin_trgm_ops)"))
        conn.execute(sa.text("CREATE INDEX ix_bench_audit_payload_tsv ON benchmark_audit_logs USING GIN (to_tsvector('simple', COALESCE(payload_text, '')))"))

        samples = []
        for _ in range(5):
            q_start = time.perf_counter()
            conn.execute(
                sa.text(
                    """
                    SELECT details->>'correlation_id' AS correlation_id, MAX(created_at) AS ended_at
                    FROM benchmark_audit_logs
                    WHERE environment = 'prod'
                      AND is_test_event = false
                      AND severity IN ('ERROR','CRITICAL')
                      AND strategy_id = 'strat-42'
                      AND symbol = 'BTCUSDT'
                      AND event_type = 'execution'
                      AND to_tsvector('simple', COALESCE(payload_text, '')) @@ plainto_tsquery('simple', 'exchange timeout')
                    GROUP BY details->>'correlation_id'
                    ORDER BY ended_at DESC
                    LIMIT 50
                    """
                )
            ).fetchall()
            samples.append(round((time.perf_counter() - q_start) * 1000, 2))

        samples_sorted = sorted(samples)
        p50 = samples_sorted[len(samples_sorted) // 2]
        p95 = samples_sorted[-1]

        total_elapsed = round((time.perf_counter() - started) * 1000, 2)

    report = {
        "type": "seeded_benchmark",
        "rows_seeded": rows,
        "samples_ms": samples,
        "p50_ms": p50,
        "p95_ms": p95,
        "target_ms": 2000,
        "meets_target": p95 < 2000,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_runtime_ms": total_elapsed,
    }

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Seeded lifecycle query benchmark")
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--output", type=str, default="/app/test_reports/p1_seeded_benchmark_report.json")
    args = parser.parse_args()

    report = run_seeded_benchmark(rows=max(args.rows, 1000), output_path=args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
