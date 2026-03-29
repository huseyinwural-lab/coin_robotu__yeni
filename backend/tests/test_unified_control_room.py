# ruff: noqa: E402
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db import SessionLocal
from services.unified_control_room_service import build_unified_control_room


def test_unified_control_room_overview_contract():
    db = SessionLocal()
    try:
        payload = build_unified_control_room(db, user_id="canary-admin", window="7d")
        assert set(payload.keys()) >= {
            "generated_at",
            "window",
            "checklist",
            "stage_activation",
            "live_operations",
            "learning_adaptation",
            "risk_market_context",
            "action_center",
            "explainability",
        }
        assert set((payload.get("live_operations") or {}).keys()) >= {"incidents", "execution_alerts", "quarantined_runtime"}
        assert set((payload.get("learning_adaptation") or {}).keys()) >= {"actionable_recommendations", "adaptive_summary", "simulation_delta"}
    finally:
        db.close()
