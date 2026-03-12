import json
import os
import sys
from pathlib import Path

import requests

SNAPSHOT_PATH = Path("/app/contracts/api_contract_snapshot.json")


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct

    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


def main() -> int:
    if not SNAPSHOT_PATH.exists():
        print("contract_gate_status=BLOCKED")
        print("reason=contract_snapshot_missing")
        return 2

    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    contracts = snapshot.get("contracts") or []
    if not contracts:
        print("contract_gate_status=BLOCKED")
        print("reason=contract_snapshot_empty")
        return 2

    base_url = _resolve_base_url()
    missing: list[str] = []
    for item in contracts:
        endpoint = item.get("endpoint")
        method = str(item.get("method", "GET")).upper()
        probe = requests.request(method, f"{base_url}{endpoint}", timeout=20)
        if probe.status_code == 404:
            missing.append(f"{method.upper()} {endpoint}")

    if missing:
        print("contract_gate_status=BLOCKED")
        print("reason=endpoint_removed_or_missing")
        print(f"missing={missing}")
        return 2

    print("contract_gate_status=PASS")
    print(f"checked_contracts={len(contracts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
