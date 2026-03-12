import json
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_PATH = Path("/app/contracts/api_contract_snapshot.json")


def build_contract_payload() -> dict:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8")) if SNAPSHOT_PATH.exists() else {"contracts": []}
    payload["snapshot_version"] = "phase7_ct_ux_v1"
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def main() -> int:
    payload = build_contract_payload()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
