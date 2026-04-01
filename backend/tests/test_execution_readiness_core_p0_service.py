"""
Execution Safety Core P0 - Direct Service Tests
Tests service-level functions directly without HTTP layer to bypass auth issues.
"""

import os
import sys
import pytest

# Add backend to path
sys.path.insert(0, "/app/backend")

# Set environment variables before imports
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres.wpaejjyirhblphihxnli:iY9yPPYAe4dLU3+@aws-1-eu-west-1.pooler.supabase.com:6543/postgres")


class TestServiceLevelGateFunction:
    """Direct tests for get_execution_safety_gate function"""

    def test_gate_function_returns_expected_structure(self):
        """get_execution_safety_gate should return expected structure"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_safety_gate
        
        db = SessionLocal()
        try:
            result = get_execution_safety_gate(db)
            
            # Verify required fields
            assert "gate_state" in result, "Missing gate_state"
            assert "execution_allowed" in result, "Missing execution_allowed"
            assert "hard_blockers" in result, "Missing hard_blockers"
            assert "soft_warnings" in result, "Missing soft_warnings"
            assert "hard_blockers_detail" in result, "Missing hard_blockers_detail"
            assert "bybit_order_smoke" in result, "Missing bybit_order_smoke"
            assert "artifact" in result, "Missing artifact"
            assert "checked_at" in result, "Missing checked_at"
            
            print(f"PASS: gate_state={result['gate_state']}, execution_allowed={result['execution_allowed']}")
            print(f"PASS: hard_blockers count={len(result['hard_blockers'])}")
            print(f"PASS: bybit_order_smoke status={result['bybit_order_smoke'].get('status')}")
        finally:
            db.close()

    def test_gate_state_is_valid_enum(self):
        """gate_state should be READY, DEGRADED, or BLOCKED"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_safety_gate
        
        db = SessionLocal()
        try:
            result = get_execution_safety_gate(db)
            assert result["gate_state"] in ["READY", "DEGRADED", "BLOCKED"], f"Invalid gate_state: {result['gate_state']}"
            print(f"PASS: gate_state={result['gate_state']} is valid")
        finally:
            db.close()

    def test_hard_blockers_are_normalized_codes(self):
        """hard_blockers should be normalized uppercase codes"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_safety_gate
        
        db = SessionLocal()
        try:
            result = get_execution_safety_gate(db)
            hard_blockers = result.get("hard_blockers", [])
            
            for code in hard_blockers:
                assert code == code.upper(), f"Code {code} should be uppercase"
                assert code == code.strip(), f"Code {code} should be trimmed"
            
            print(f"PASS: {len(hard_blockers)} hard_blockers are normalized: {hard_blockers[:5]}")
        finally:
            db.close()

    def test_hard_blockers_detail_structure(self):
        """hard_blockers_detail should have step_key, reason_code, message"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_safety_gate
        
        db = SessionLocal()
        try:
            result = get_execution_safety_gate(db)
            details = result.get("hard_blockers_detail", [])
            
            for item in details[:5]:
                assert "step_key" in item, "Missing step_key in detail"
                assert "reason_code" in item, "Missing reason_code in detail"
                assert "message" in item, "Missing message in detail"
            
            print(f"PASS: {len(details)} hard_blockers_detail items have correct structure")
        finally:
            db.close()

    def test_bybit_smoke_structure(self):
        """bybit_order_smoke should have status, reason_code, checked_at"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_safety_gate
        
        db = SessionLocal()
        try:
            result = get_execution_safety_gate(db)
            smoke = result.get("bybit_order_smoke", {})
            
            assert "status" in smoke, "Missing status in bybit_order_smoke"
            assert "reason_code" in smoke, "Missing reason_code in bybit_order_smoke"
            assert "checked_at" in smoke, "Missing checked_at in bybit_order_smoke"
            
            # Status should be PASS or FAIL
            assert smoke["status"] in ["PASS", "FAIL"], f"Invalid smoke status: {smoke['status']}"
            
            print(f"PASS: bybit_order_smoke status={smoke['status']}, reason_code={smoke['reason_code']}")
        finally:
            db.close()

    def test_artifact_structure(self):
        """artifact should have status and local_path"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_safety_gate
        
        db = SessionLocal()
        try:
            result = get_execution_safety_gate(db)
            artifact = result.get("artifact", {})
            
            assert "status" in artifact, "Missing status in artifact"
            assert artifact["status"] in ["LOCAL_ONLY", "S3_UPLOADED"], f"Invalid artifact status: {artifact['status']}"
            assert "local_path" in artifact, "Missing local_path in artifact"
            
            print(f"PASS: artifact status={artifact['status']}")
        finally:
            db.close()

    def test_execution_allowed_logic(self):
        """execution_allowed should be False when hard_blockers exist"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_safety_gate
        
        db = SessionLocal()
        try:
            result = get_execution_safety_gate(db)
            
            hard_blockers = result.get("hard_blockers", [])
            execution_allowed = result.get("execution_allowed")
            gate_state = result.get("gate_state")
            
            if hard_blockers:
                assert execution_allowed is False, "execution_allowed should be False when hard_blockers exist"
            
            if gate_state == "BLOCKED":
                assert execution_allowed is False, "execution_allowed should be False when BLOCKED"
            
            print(f"PASS: execution_allowed={execution_allowed}, gate_state={gate_state}, blockers={len(hard_blockers)}")
        finally:
            db.close()


class TestServiceLevelIntentsFunction:
    """Direct tests for get_execution_intent_state_machine_snapshot function"""

    def test_intents_function_returns_expected_structure(self):
        """get_execution_intent_state_machine_snapshot should return expected structure"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_intent_state_machine_snapshot
        
        db = SessionLocal()
        try:
            result = get_execution_intent_state_machine_snapshot(db)
            
            # Verify required fields
            assert "total" in result, "Missing total"
            assert "stuck_count" in result, "Missing stuck_count"
            assert "state_counts" in result, "Missing state_counts"
            assert "timeouts" in result, "Missing timeouts"
            assert "items" in result, "Missing items"
            
            print(f"PASS: total={result['total']}, stuck_count={result['stuck_count']}")
        finally:
            db.close()

    def test_state_counts_has_all_states(self):
        """state_counts should have all expected states"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_intent_state_machine_snapshot
        
        db = SessionLocal()
        try:
            result = get_execution_intent_state_machine_snapshot(db)
            state_counts = result.get("state_counts", {})
            
            expected_states = ["CREATED", "SUBMITTED", "ACKED", "FILLED", "FAILED", "CANCELLED", "QUARANTINED"]
            for state in expected_states:
                assert state in state_counts, f"Missing state {state} in state_counts"
            
            print(f"PASS: state_counts={state_counts}")
        finally:
            db.close()

    def test_timeouts_has_expected_states(self):
        """timeouts should have CREATED, SUBMITTED, ACKED"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_intent_state_machine_snapshot
        
        db = SessionLocal()
        try:
            result = get_execution_intent_state_machine_snapshot(db)
            timeouts = result.get("timeouts", {})
            
            expected_timeout_states = ["CREATED", "SUBMITTED", "ACKED"]
            for state in expected_timeout_states:
                assert state in timeouts, f"Missing timeout for state {state}"
                assert isinstance(timeouts[state], int), f"Timeout for {state} should be int"
            
            print(f"PASS: timeouts={timeouts}")
        finally:
            db.close()

    def test_limit_parameter_respected(self):
        """limit parameter should be respected"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_execution_intent_state_machine_snapshot
        
        db = SessionLocal()
        try:
            result = get_execution_intent_state_machine_snapshot(db, limit=5)
            items = result.get("items", [])
            
            assert len(items) <= 5, f"Expected max 5 items, got {len(items)}"
            print(f"PASS: limit=5 returned {len(items)} items")
        finally:
            db.close()


class TestServiceLevelQuarantineFunction:
    """Direct tests for get_runtime_quarantine_snapshot function"""

    def test_quarantine_function_returns_expected_structure(self):
        """get_runtime_quarantine_snapshot should return expected structure"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_runtime_quarantine_snapshot
        
        db = SessionLocal()
        try:
            result = get_runtime_quarantine_snapshot(db)
            
            # Verify required fields
            assert "total" in result, "Missing total"
            assert "summary" in result, "Missing summary"
            assert "queue_metrics" in result, "Missing queue_metrics"
            assert "items" in result, "Missing items"
            
            print(f"PASS: total={result['total']}, summary keys={list(result['summary'].keys())}")
        finally:
            db.close()

    def test_queue_metrics_structure(self):
        """queue_metrics should have expected fields"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_runtime_quarantine_snapshot
        
        db = SessionLocal()
        try:
            result = get_runtime_quarantine_snapshot(db)
            queue_metrics = result.get("queue_metrics", {})
            
            expected_fields = [
                "redis_available",
                "runtime_events_queue",
                "runtime_retry_queue",
                "runtime_dead_letter_queue",
                "runtime_quarantine_queue",
            ]
            
            for field in expected_fields:
                assert field in queue_metrics, f"Missing {field} in queue_metrics"
            
            print(f"PASS: queue_metrics={queue_metrics}")
        finally:
            db.close()

    def test_limit_parameter_respected(self):
        """limit parameter should be respected"""
        from db import SessionLocal
        from services.execution_safety_core_service import get_runtime_quarantine_snapshot
        
        db = SessionLocal()
        try:
            result = get_runtime_quarantine_snapshot(db, limit=10)
            items = result.get("items", [])
            
            assert len(items) <= 10, f"Expected max 10 items, got {len(items)}"
            print(f"PASS: limit=10 returned {len(items)} items")
        finally:
            db.close()


class TestServiceLevelQuarantineActions:
    """Direct tests for apply_runtime_quarantine_action function"""

    def test_invalid_event_raises_value_error(self):
        """apply_runtime_quarantine_action should raise ValueError for invalid event"""
        from db import SessionLocal
        from services.execution_safety_core_service import apply_runtime_quarantine_action
        
        db = SessionLocal()
        try:
            with pytest.raises(ValueError) as exc_info:
                apply_runtime_quarantine_action(
                    db,
                    event_id="nonexistent-event-id-12345",
                    action="replay",
                    actor_user_id="test-user",
                    actor_role="admin",
                )
            
            assert "quarantine_event_not_found" in str(exc_info.value)
            print("PASS: Invalid event_id raises ValueError with quarantine_event_not_found")
        finally:
            db.close()

    def test_invalid_action_raises_value_error(self):
        """apply_runtime_quarantine_action should raise ValueError for invalid action"""
        from db import SessionLocal
        from services.execution_safety_core_service import apply_runtime_quarantine_action
        
        db = SessionLocal()
        try:
            # First, we need to check if there's any quarantine event
            from services.execution_safety_core_service import get_runtime_quarantine_snapshot
            snapshot = get_runtime_quarantine_snapshot(db, limit=1)
            
            if snapshot.get("items"):
                event_id = snapshot["items"][0]["id"]
                with pytest.raises(ValueError) as exc_info:
                    apply_runtime_quarantine_action(
                        db,
                        event_id=event_id,
                        action="invalid_action",
                        actor_user_id="test-user",
                        actor_role="admin",
                    )
                assert "invalid_action" in str(exc_info.value)
                print("PASS: Invalid action raises ValueError with invalid_action")
            else:
                # No quarantine events, test with nonexistent event
                with pytest.raises(ValueError) as exc_info:
                    apply_runtime_quarantine_action(
                        db,
                        event_id="test-event",
                        action="invalid_action",
                        actor_user_id="test-user",
                        actor_role="admin",
                    )
                # Should fail with quarantine_event_not_found first
                assert "quarantine_event_not_found" in str(exc_info.value)
                print("PASS: No quarantine events, event not found error raised first")
        finally:
            db.close()


class TestHardBlockReasonCodes:
    """Tests for HARD_BLOCK_REASON_CODES constant"""

    def test_expected_codes_present(self):
        """HARD_BLOCK_REASON_CODES should contain expected codes"""
        from services.execution_safety_core_service import HARD_BLOCK_REASON_CODES
        
        expected_codes = [
            "TESTNET_TRADING_DISABLED",
            "MARKET_DATA_MISSING",
            "MARKET_DATA_STALE",
            "KILL_SWITCH_ACTIVE",
            "BYBIT_TESTNET_CREDENTIALS_MISSING",
            "BYBIT_AUTH_PROBE_FAIL",
            "BYBIT_CONNECTIVITY_FAIL",
            "BYBIT_ORDER_SMOKE_FAIL",
            "BYBIT_ORDER_SMOKE_AUTH_FAIL",
            "ORDERBOOK_INVALID",
            "EXCHANGE_CONNECTION_UNHEALTHY",
            "EXECUTION_PROOF_REAL_METRIC_MISSING",
            "EXECUTION_PROOF_MOCKED_PATHS",
            "READINESS_BLOCKING_FAILURE",
        ]
        
        for code in expected_codes:
            assert code in HARD_BLOCK_REASON_CODES, f"Missing expected code: {code}"
        
        print(f"PASS: All {len(expected_codes)} expected codes present in HARD_BLOCK_REASON_CODES")


class TestIntentAllowedTransitions:
    """Tests for INTENT_ALLOWED_TRANSITIONS constant"""

    def test_all_states_defined(self):
        """INTENT_ALLOWED_TRANSITIONS should define all states"""
        from services.execution_safety_core_service import INTENT_ALLOWED_TRANSITIONS
        
        expected_states = ["CREATED", "SUBMITTED", "ACKED", "FILLED", "FAILED", "CANCELLED", "QUARANTINED"]
        
        for state in expected_states:
            assert state in INTENT_ALLOWED_TRANSITIONS, f"Missing state: {state}"
        
        print(f"PASS: All {len(expected_states)} states defined")

    def test_terminal_states_have_no_transitions(self):
        """Terminal states should have no allowed transitions"""
        from services.execution_safety_core_service import INTENT_ALLOWED_TRANSITIONS
        
        terminal_states = ["FILLED", "FAILED", "CANCELLED"]
        
        for state in terminal_states:
            assert len(INTENT_ALLOWED_TRANSITIONS[state]) == 0, f"{state} should be terminal (no transitions)"
        
        print(f"PASS: Terminal states {terminal_states} have no transitions")

    def test_created_can_transition_to_submitted(self):
        """CREATED should be able to transition to SUBMITTED"""
        from services.execution_safety_core_service import INTENT_ALLOWED_TRANSITIONS
        
        assert "SUBMITTED" in INTENT_ALLOWED_TRANSITIONS["CREATED"], "CREATED should transition to SUBMITTED"
        print("PASS: CREATED can transition to SUBMITTED")

    def test_quarantined_can_be_replayed(self):
        """QUARANTINED should be able to transition to SUBMITTED (replay)"""
        from services.execution_safety_core_service import INTENT_ALLOWED_TRANSITIONS
        
        assert "SUBMITTED" in INTENT_ALLOWED_TRANSITIONS["QUARANTINED"], "QUARANTINED should transition to SUBMITTED"
        print("PASS: QUARANTINED can transition to SUBMITTED (replay)")


class TestBybitOrderSmoke:
    """Tests for run_bybit_testnet_order_smoke function"""

    def test_smoke_returns_expected_structure(self):
        """run_bybit_testnet_order_smoke should return expected structure"""
        from db import SessionLocal
        from services.execution_safety_core_service import run_bybit_testnet_order_smoke
        
        db = SessionLocal()
        try:
            result = run_bybit_testnet_order_smoke(db)
            
            assert "status" in result, "Missing status"
            assert "reason_code" in result, "Missing reason_code"
            assert "checked_at" in result, "Missing checked_at"
            
            assert result["status"] in ["PASS", "FAIL"], f"Invalid status: {result['status']}"
            
            print(f"PASS: smoke status={result['status']}, reason_code={result['reason_code']}")
        finally:
            db.close()

    def test_smoke_with_force_refresh(self):
        """run_bybit_testnet_order_smoke should accept force_refresh parameter"""
        from db import SessionLocal
        from services.execution_safety_core_service import run_bybit_testnet_order_smoke
        
        db = SessionLocal()
        try:
            result = run_bybit_testnet_order_smoke(db, force_refresh=True)
            
            assert "status" in result, "Missing status"
            assert "checked_at" in result, "Missing checked_at"
            
            print(f"PASS: force_refresh=True accepted, status={result['status']}")
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
