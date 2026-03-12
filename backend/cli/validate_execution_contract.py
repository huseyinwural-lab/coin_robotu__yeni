import json
import os
import sys
from pathlib import Path

import requests

CONTRACT_PATH = Path("/app/contracts/execution_intent_contract.json")


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_path = Path("/app/frontend/.env")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


def main() -> int:
    if not CONTRACT_PATH.exists():
        print("execution_contract_gate_status=BLOCKED")
        print("reason=execution_contract_missing")
        return 2

    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    endpoints = payload.get("endpoints") or []
    base_url = _resolve_base_url()

    missing = []
    for item in endpoints:
        method = item.get("method", "GET").upper()
        endpoint = item.get("endpoint")
        probe = requests.request(method, f"{base_url}{endpoint}", timeout=20)
        if probe.status_code == 404:
            missing.append(f"{method} {endpoint}")

    if missing:
        print("execution_contract_gate_status=BLOCKED")
        print("reason=execution_endpoint_missing")
        print(f"missing={missing}")
        return 2

    print("execution_contract_gate_status=PASS")
    print(f"checked_endpoints={len(endpoints)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
