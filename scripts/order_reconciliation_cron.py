#!/usr/bin/env python3

import json
from datetime import datetime, timezone

import sys

sys.path.append("/app/backend")

from core.reconciliation.order_reconciliation import run_order_reconciliation  # noqa: E402
from db import SessionLocal  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        result = run_order_reconciliation(db, limit=200)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "result": result,
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
