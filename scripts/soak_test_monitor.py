#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests


@dataclass
class EndpointResult:
    path: str
    ok: bool
    status_code: int | None
    latency_ms: float
    error: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="24 saatlik soak test + zombie proses izleme")
    parser.add_argument("--base-url", required=True, help="Örn: https://<preview-domain>")
    parser.add_argument("--admin-email", default=os.environ.get("SOAK_ADMIN_EMAIL", "review.user@platform.local"))
    parser.add_argument("--admin-password", default=os.environ.get("SOAK_ADMIN_PASSWORD", "ReviewUser123!"))
    parser.add_argument("--duration-hours", type=float, default=24.0)
    parser.add_argument("--interval-seconds", type=int, default=30)
    parser.add_argument("--burst", type=int, default=3, help="Her turda endpoint başına istek adedi")
    parser.add_argument("--output-dir", default="/app/artifacts/soak")
    parser.add_argument("--stop-on-zombie", action="store_true")
    return parser.parse_args()


def login_admin(base_url: str, email: str, password: str) -> str:
    url = f"{base_url.rstrip('/')}/api/auth/login/admin"
    response = requests.post(url, json={"email": email, "password": password}, timeout=25)
    response.raise_for_status()
    payload = response.json() if response.content else {}
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("admin_login_no_access_token")
    return token


def fetch_endpoint(base_url: str, token: str, path: str) -> EndpointResult:
    started = time.perf_counter()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Session-ID": "soak-session",
        "X-Session-Device": "soak-device-000000000000000000000001",
        "X-Request-ID": f"soak-{int(time.time() * 1000)}",
    }
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api{path}", headers=headers, timeout=25)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return EndpointResult(
            path=path,
            ok=response.status_code < 500,
            status_code=response.status_code,
            latency_ms=round(latency_ms, 2),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        return EndpointResult(
            path=path,
            ok=False,
            status_code=None,
            latency_ms=round(latency_ms, 2),
            error=str(exc)[:240],
        )


def collect_zombies() -> dict:
    completed = subprocess.run(
        ["ps", "-eo", "pid,ppid,state,comm,args"],
        capture_output=True,
        text=True,
        check=False,
    )
    rows = (completed.stdout or "").splitlines()
    zombies = []
    for row in rows[1:]:
        parts = row.strip().split(maxsplit=4)
        if len(parts) < 5:
            continue
        pid, ppid, state, comm, args = parts
        if "Z" not in state:
            continue
        zombies.append(
            {
                "pid": pid,
                "ppid": ppid,
                "state": state,
                "comm": comm,
                "args": args,
            }
        )
    return {
        "zombie_count": len(zombies),
        "zombies": zombies[:30],
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "soak_samples.jsonl"
    summary_path = output_dir / "soak_summary.json"

    token = login_admin(args.base_url, args.admin_email, args.admin_password)
    endpoints = [
        "/health/live",
        "/health/ready",
        "/runtime/ws/health",
        "/runtime/ws/execution-timeline?limit=80",
        "/runtime/alerts?limit=20",
    ]

    duration_seconds = int(max(1.0, args.duration_hours) * 3600)
    interval_seconds = max(5, int(args.interval_seconds))
    burst = max(1, int(args.burst))
    started_at = time.time()

    total_samples = 0
    max_zombie_count = 0
    total_endpoint_errors = 0
    first_zombie_seen_at = None

    print(f"[soak] started={utc_now_iso()} duration_hours={args.duration_hours} interval={interval_seconds}s burst={burst}")
    print(f"[soak] samples={samples_path}")

    with samples_path.open("a", encoding="utf-8") as stream:
        while True:
            elapsed = int(time.time() - started_at)
            if elapsed >= duration_seconds:
                break

            endpoint_runs = []
            for _ in range(burst):
                for path in endpoints:
                    endpoint_runs.append(fetch_endpoint(args.base_url, token, path))

            zombie_state = collect_zombies()
            zombie_count = int(zombie_state["zombie_count"])
            max_zombie_count = max(max_zombie_count, zombie_count)
            if zombie_count > 0 and first_zombie_seen_at is None:
                first_zombie_seen_at = utc_now_iso()

            endpoint_errors = [
                {
                    "path": item.path,
                    "status_code": item.status_code,
                    "error": item.error,
                }
                for item in endpoint_runs
                if not item.ok
            ]
            total_endpoint_errors += len(endpoint_errors)

            sample = {
                "timestamp": utc_now_iso(),
                "elapsed_seconds": elapsed,
                "zombie": zombie_state,
                "request_stats": {
                    "total": len(endpoint_runs),
                    "failed": len(endpoint_errors),
                    "avg_latency_ms": round(
                        sum(item.latency_ms for item in endpoint_runs) / max(1, len(endpoint_runs)),
                        2,
                    ),
                    "errors": endpoint_errors[:20],
                },
            }
            stream.write(json.dumps(sample, ensure_ascii=False) + "\n")
            stream.flush()

            total_samples += 1
            print(
                f"[soak] t={elapsed}s samples={total_samples} zombie={zombie_count} "
                f"errors={len(endpoint_errors)} avg_ms={sample['request_stats']['avg_latency_ms']}"
            )

            if args.stop_on_zombie and zombie_count > 0:
                print("[soak] zombie detected, stopping due to --stop-on-zombie")
                break

            time.sleep(interval_seconds)

    summary = {
        "started_at": datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat(),
        "finished_at": utc_now_iso(),
        "duration_hours_requested": args.duration_hours,
        "interval_seconds": interval_seconds,
        "burst": burst,
        "total_samples": total_samples,
        "max_zombie_count": max_zombie_count,
        "first_zombie_seen_at": first_zombie_seen_at,
        "total_endpoint_errors": total_endpoint_errors,
        "status": "PASS" if max_zombie_count == 0 else "FAIL",
        "samples_file": str(samples_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[soak] summary={summary_path}")
    print(f"[soak] status={summary['status']} max_zombie_count={max_zombie_count}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
