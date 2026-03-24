#!/usr/bin/env python3
import argparse
import os
import socket
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(message: str) -> None:
    print(f"[{_now()}] [postgres-wait] {message}", flush=True)


def _read_database_url() -> str:
    load_dotenv("/app/backend/.env")
    database_url = str(os.environ.get("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL missing")
    return database_url


def _parse_target(database_url: str) -> tuple[str, int]:
    parsed = make_url(database_url)
    host = str(parsed.host or "").strip()
    port = int(parsed.port or 5432)
    if not host:
        raise RuntimeError("DATABASE_URL host missing")
    if host.lower() in LOCALHOST_HOSTS:
        raise RuntimeError("DATABASE_URL localhost forbidden")
    if not parsed.database:
        raise RuntimeError("DATABASE_URL database name missing")
    return host, port


def _can_connect(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for PostgreSQL TCP readiness")
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--initial-delay", type=float, default=1.0)
    parser.add_argument("--connect-timeout", type=float, default=2.0)
    args = parser.parse_args()

    try:
        database_url = _read_database_url()
        host, port = _parse_target(database_url)
    except Exception as exc:
        _log(f"FAIL_FAST: {exc}")
        return 2

    delay = max(0.2, args.initial_delay)
    for attempt in range(1, max(1, args.attempts) + 1):
        if _can_connect(host, port, timeout=max(0.5, args.connect_timeout)):
            _log(f"READY: {host}:{port} reachable on attempt={attempt}")
            return 0
        _log(f"WAIT: {host}:{port} unreachable attempt={attempt}/{args.attempts}; retry_in={delay:.1f}s")
        time.sleep(delay)
        delay = min(delay * 1.5, 8.0)

    _log(f"NOT_READY: {host}:{port} unreachable after attempts={args.attempts}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
