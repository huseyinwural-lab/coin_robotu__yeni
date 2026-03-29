# ruff: noqa: E402
"""
Comprehensive tests for Unified Control Room API and related services.
Tests: Backend unified control room overview endpoint, shared audit payload standard,
action center controls, and stage activation.
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from db import SessionLocal
from services.unified_control_room_service import build_unified_control_room
from services.audit_service import build_critical_action_details, create_audit_log
from services.incident_intelligence_service import list_intelligence_incidents


class TestUnifiedControlRoomOverview:
    """Tests for unified control room overview endpoint contract"""

    def test_overview_returns_all_expected_sections(self):
        """Verify overview returns all required top-level keys"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            
            # Check all required top-level keys
            required_keys = {
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
            assert set(payload.keys()) >= required_keys, f"Missing keys: {required_keys - set(payload.keys())}"
            print(f"SUCCESS: All {len(required_keys)} required top-level keys present")
        finally:
            db.close()

    def test_live_operations_structure(self):
        """Verify live_operations contains incidents, execution_alerts, quarantined_runtime"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            live_ops = payload.get("live_operations") or {}
            
            required_keys = {"incidents", "execution_alerts", "quarantined_runtime"}
            assert set(live_ops.keys()) >= required_keys, f"Missing live_operations keys: {required_keys - set(live_ops.keys())}"
            
            # Verify incidents is a list
            assert isinstance(live_ops.get("incidents"), list), "incidents should be a list"
            assert isinstance(live_ops.get("execution_alerts"), list), "execution_alerts should be a list"
            print("SUCCESS: live_operations structure verified")
        finally:
            db.close()

    def test_learning_adaptation_structure(self):
        """Verify learning_adaptation contains actionable_recommendations, adaptive_summary, simulation_delta"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            learning = payload.get("learning_adaptation") or {}
            
            required_keys = {"actionable_recommendations", "adaptive_summary", "simulation_delta"}
            assert set(learning.keys()) >= required_keys, f"Missing learning_adaptation keys: {required_keys - set(learning.keys())}"
            
            assert isinstance(learning.get("actionable_recommendations"), list), "actionable_recommendations should be a list"
            print("SUCCESS: learning_adaptation structure verified")
        finally:
            db.close()

    def test_risk_market_context_structure(self):
        """Verify risk_market_context contains cluster_risk, tail_risk, capital_pressure, microstructure_stress"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            risk = payload.get("risk_market_context") or {}
            
            required_keys = {"cluster_risk", "tail_risk", "capital_pressure", "microstructure_stress"}
            assert set(risk.keys()) >= required_keys, f"Missing risk_market_context keys: {required_keys - set(risk.keys())}"
            print("SUCCESS: risk_market_context structure verified")
        finally:
            db.close()

    def test_action_center_controls(self):
        """Verify action_center contains preview_action, approve_reject, apply_rollback"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            action_center = payload.get("action_center") or {}
            
            required_keys = {"preview_action", "approve_reject", "apply_rollback"}
            assert set(action_center.keys()) >= required_keys, f"Missing action_center keys: {required_keys - set(action_center.keys())}"
            
            # Verify all controls are boolean True (enabled)
            assert action_center.get("preview_action") is True, "preview_action should be True"
            assert action_center.get("approve_reject") is True, "approve_reject should be True"
            assert action_center.get("apply_rollback") is True, "apply_rollback should be True"
            print("SUCCESS: action_center controls verified")
        finally:
            db.close()

    def test_stage_activation_structure(self):
        """Verify stage_activation contains stage_1, stage_2, stage_3 with correct modes"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            stages = payload.get("stage_activation") or {}
            
            # Check all stages present
            assert "stage_1" in stages, "stage_1 missing"
            assert "stage_2" in stages, "stage_2 missing"
            assert "stage_3" in stages, "stage_3 missing"
            
            # Verify stage_1 is enabled and read_only
            stage_1 = stages.get("stage_1") or {}
            assert stage_1.get("enabled") is True, "stage_1 should be enabled"
            assert stage_1.get("mode") == "read_only", "stage_1 mode should be read_only"
            assert stage_1.get("live_action") is False, "stage_1 live_action should be False"
            
            # Verify stage_2 and stage_3 are disabled by default
            stage_2 = stages.get("stage_2") or {}
            assert stage_2.get("enabled") is False, "stage_2 should be disabled by default"
            
            stage_3 = stages.get("stage_3") or {}
            assert stage_3.get("enabled") is False, "stage_3 should be disabled by default"
            
            print("SUCCESS: stage_activation structure verified - Stage 1 active, Stage 2/3 disabled")
        finally:
            db.close()

    def test_checklist_structure(self):
        """Verify checklist contains all required flags"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            checklist = payload.get("checklist") or {}
            
            required_keys = {
                "auth_stable",
                "browser_e2e_pass",
                "rollback_pass",
                "audit_complete",
                "dry_run_live_separation",
                "guardrails_active",
                "unified_control_room_visible",
            }
            assert set(checklist.keys()) >= required_keys, f"Missing checklist keys: {required_keys - set(checklist.keys())}"
            print("SUCCESS: checklist structure verified")
        finally:
            db.close()

    def test_explainability_cards(self):
        """Verify explainability is a list of cards with expected structure"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            explainability = payload.get("explainability") or []
            
            assert isinstance(explainability, list), "explainability should be a list"
            
            # If there are cards, verify structure
            if explainability:
                card = explainability[0]
                expected_keys = {"title", "why", "evidence", "recommended_action", "what_if", "rollback_ready", "refs"}
                assert set(card.keys()) >= expected_keys, f"Missing explainability card keys: {expected_keys - set(card.keys())}"
            
            print(f"SUCCESS: explainability verified with {len(explainability)} cards")
        finally:
            db.close()


class TestSharedAuditPayloadStandard:
    """Tests for shared critical action audit payload standard"""

    def test_build_critical_action_details_returns_all_fields(self):
        """Verify build_critical_action_details returns all required fields"""
        result = build_critical_action_details(
            actor="test-user",
            reason="test-reason",
            scope="test-scope",
            before_state={"key": "before"},
            after_state={"key": "after"},
            rollback_ref="rollback-123",
            incident_ref="incident-456",
            recommendation_ref="rec-789",
            execution_ref="exec-abc",
            action_ref="action-def",
        )
        
        required_keys = {
            "actor",
            "reason",
            "timestamp",
            "scope",
            "before_state",
            "after_state",
            "rollback_ref",
            "incident_ref",
            "recommendation_ref",
            "execution_ref",
            "action_ref",
        }
        assert set(result.keys()) >= required_keys, f"Missing keys: {required_keys - set(result.keys())}"
        
        # Verify values
        assert result["actor"] == "test-user"
        assert result["reason"] == "test-reason"
        assert result["scope"] == "test-scope"
        assert result["before_state"] == {"key": "before"}
        assert result["after_state"] == {"key": "after"}
        assert result["rollback_ref"] == "rollback-123"
        assert result["incident_ref"] == "incident-456"
        assert result["recommendation_ref"] == "rec-789"
        assert result["execution_ref"] == "exec-abc"
        assert result["action_ref"] == "action-def"
        
        print("SUCCESS: build_critical_action_details returns all required fields")

    def test_build_critical_action_details_with_extra(self):
        """Verify extra fields are merged into result"""
        result = build_critical_action_details(
            actor="test-user",
            reason="test-reason",
            scope="test-scope",
            extra={"custom_field": "custom_value", "another_field": 123},
        )
        
        assert result.get("custom_field") == "custom_value"
        assert result.get("another_field") == 123
        print("SUCCESS: extra fields merged correctly")

    def test_audit_log_creation_with_critical_action_details(self):
        """Verify audit log can be created with critical action details"""
        db = SessionLocal()
        try:
            details = build_critical_action_details(
                actor="test-admin",
                reason="unified_control_room_test",
                scope="test:audit",
                before_state={"status": "pending"},
                after_state={"status": "completed"},
                action_ref="test-action-ref",
            )
            
            audit_entry = create_audit_log(
                db,
                action="TEST_UNIFIED_CONTROL_ROOM_AUDIT",
                entity_type="test_entity",
                entity_id="test-entity-123",
                actor_user_id="test-admin",
                actor_role="admin",
                severity="info",
                details=details,
            )
            
            assert audit_entry is not None
            assert audit_entry.action == "TEST_UNIFIED_CONTROL_ROOM_AUDIT"
            assert audit_entry.details.get("actor") == "test-admin"
            assert audit_entry.details.get("action_ref") == "test-action-ref"
            
            print("SUCCESS: audit log created with critical action details")
        finally:
            db.close()


class TestIncidentIntelligenceIntegration:
    """Tests for incident intelligence integration with unified control room"""

    def test_list_intelligence_incidents(self):
        """Verify list_intelligence_incidents returns proper structure"""
        db = SessionLocal()
        try:
            incidents = list_intelligence_incidents(db, limit=10)
            
            assert isinstance(incidents, list), "incidents should be a list"
            
            # If there are incidents, verify structure
            if incidents:
                incident = incidents[0]
                expected_keys = {"incident_id", "title", "severity", "state", "owner"}
                assert set(incident.keys()) >= expected_keys, f"Missing incident keys: {expected_keys - set(incident.keys())}"
            
            print(f"SUCCESS: list_intelligence_incidents returned {len(incidents)} incidents")
        finally:
            db.close()


class TestUnifiedRefsStructure:
    """Tests for unified refs structure in control room items"""

    def test_incident_refs_structure(self):
        """Verify incidents have refs with unified structure"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            incidents = (payload.get("live_operations") or {}).get("incidents") or []
            
            if incidents:
                incident = incidents[0]
                refs = incident.get("refs") or {}
                
                # Verify refs structure
                expected_ref_keys = {"incident_id", "recommendation_ref", "execution_ref", "strategy_id", "symbol", "risk_domain", "action_ref"}
                assert set(refs.keys()) >= expected_ref_keys, f"Missing refs keys: {expected_ref_keys - set(refs.keys())}"
            
            print(f"SUCCESS: incident refs structure verified for {len(incidents)} incidents")
        finally:
            db.close()

    def test_learning_card_refs_structure(self):
        """Verify learning cards have refs with unified structure"""
        db = SessionLocal()
        try:
            payload = build_unified_control_room(db, user_id="test-admin", window="7d")
            recommendations = (payload.get("learning_adaptation") or {}).get("actionable_recommendations") or []
            
            if recommendations:
                rec = recommendations[0]
                refs = rec.get("refs") or {}
                
                # Verify refs structure
                expected_ref_keys = {"incident_id", "recommendation_ref", "execution_ref", "strategy_id", "symbol", "risk_domain", "action_ref"}
                assert set(refs.keys()) >= expected_ref_keys, f"Missing refs keys: {expected_ref_keys - set(refs.keys())}"
            
            print(f"SUCCESS: learning card refs structure verified for {len(recommendations)} recommendations")
        finally:
            db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
