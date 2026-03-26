from core.alerts.runtime_alert_triggers import trigger_runtime_threshold_alert
from db import SessionLocal
from models import SystemAlert


def test_runtime_alert_trigger_writes_system_alert():
    db = SessionLocal()
    try:
        before_row = (
            db.query(SystemAlert)
            .filter(SystemAlert.alert_type == "runtime_test_alert")
            .order_by(SystemAlert.updated_at.desc())
            .first()
        )
        before_occurrences = int(before_row.occurrences) if before_row else 0

        trigger_runtime_threshold_alert(
            db,
            alert_type="runtime_test_alert",
            severity="WARNING",
            message="runtime alert trigger test",
            source="test_runtime_alert_triggers",
            threshold=5,
            actual_value=8,
            user_id="test-user",
            symbol="BTCUSDT",
            root_cause_code="runtime_test",
        )

        latest = (
            db.query(SystemAlert)
            .filter(SystemAlert.alert_type == "runtime_test_alert")
            .order_by(SystemAlert.updated_at.desc())
            .first()
        )
        assert latest is not None
        assert latest.alert_type == "runtime_test_alert"
        assert latest.details.get("severity") == "WARNING"
        assert latest.details.get("source") == "test_runtime_alert_triggers"
        assert int(latest.occurrences or 1) >= before_occurrences
    finally:
        db.close()
