import sys

from db import SessionLocal
from services.live_mode_service import enforce_release_gate


def main() -> int:
    db = SessionLocal()
    try:
        gate = enforce_release_gate(db)
        print(f"release_gate_status={gate['status']}")
        if gate["status"] == "BLOCKED":
            reason = gate["reasons"][0] if gate["reasons"] else "unknown"
            print(f"reason={reason}")
            return 2
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())