#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import websocket


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime WS soak test")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "started_at": _now_iso(),
        "base_url": base_url,
        "production_url_used": ".preview." not in base_url,
        "connected": False,
        "messages": 0,
        "duration_seconds": args.minutes * 60,
        "error": None,
    }

    try:
        login = requests.post(
            f"{base_url}/api/auth/login",
            json={"email": args.email, "password": args.password},
            timeout=30,
        )
        login.raise_for_status()
        token = login.json().get("access_token") or login.json().get("token")
        if not token:
            raise RuntimeError("missing_token")

        ws_url = f"{ws_base}/api/runtime/ws/execution-timeline?token={token}"
        ws = websocket.create_connection(ws_url, timeout=30)
        payload["connected"] = True

        stop_at = time.time() + (args.minutes * 60)
        while time.time() < stop_at:
            try:
                ws.send("ping")
                _ = ws.recv()
                payload["messages"] += 1
            except Exception:
                break
            time.sleep(5)

        ws.close()
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)

    payload["completed_at"] = _now_iso()
    payload["status"] = "PASS" if payload["connected"] and payload["messages"] >= 3 and not payload["error"] else "FAIL"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(output_path)
    print(payload["status"])
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
