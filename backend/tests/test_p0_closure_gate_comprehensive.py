"""
P0 Closure Gate Script Comprehensive Tests
Tests: p0_closure_gate.py and final_release_smoke_suite.py

Features tested:
- python /app/backend/cli/p0_closure_gate.py --target-env preview returns JSON and exit code 0 or 2
- --skip-user-contracts flag skips user contract checks
- All required checks present: sqlite_fallback_policy, alembic_heads, alembic_db_revision_match, critical_tables_presence, final_release_smoke_suite
- final_release_smoke_suite.py runs and returns valid JSON
- release_readiness_final_checklist.md exists and contains up-to-date commands
"""
import json
import os
import subprocess
from pathlib import Path

import pytest


class TestP0ClosureGateScript:
    """Tests for p0_closure_gate.py CLI script"""

    def test_preview_mode_runs_and_returns_json(self):
        """Test: python /app/backend/cli/p0_closure_gate.py --target-env preview runs and returns JSON"""
        proc = subprocess.run(
            [
                "python",
                "/app/backend/cli/p0_closure_gate.py",
                "--target-env",
                "preview",
                "--skip-user-contracts",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # Exit code should be 0 (PASS) or 2 (FAIL)
        assert proc.returncode in {0, 2}, f"Unexpected exit code: {proc.returncode}, stderr: {proc.stderr}"
        
        # Output should be valid JSON
        payload = json.loads(proc.stdout)
        assert payload.get("target_env") == "preview"
        assert "overall" in payload
        assert payload["overall"] in {"PASS", "FAIL"}
        assert isinstance(payload.get("checks"), list)
        assert "generated_at" in payload
        assert "base_url" in payload
        assert "fail_count" in payload
        assert "warn_count" in payload

    def test_skip_user_contracts_flag(self):
        """Test: --skip-user-contracts flag works and skips user contract checks"""
        proc = subprocess.run(
            [
                "python",
                "/app/backend/cli/p0_closure_gate.py",
                "--target-env",
                "preview",
                "--skip-user-contracts",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode in {0, 2}
        payload = json.loads(proc.stdout)
        
        # Find user_contract_checks in checks
        contract_check = next(
            (c for c in payload.get("checks", []) if c.get("name") == "user_contract_checks"),
            None,
        )
        assert contract_check is not None, "user_contract_checks should be present when --skip-user-contracts is used"
        assert contract_check.get("status") == "SKIP", "status should be SKIP when --skip-user-contracts is used"
        assert contract_check.get("details", {}).get("reason") == "skip_user_contracts=true"

    def test_required_check_names_present(self):
        """Test: All required check names are present in output"""
        proc = subprocess.run(
            [
                "python",
                "/app/backend/cli/p0_closure_gate.py",
                "--target-env",
                "preview",
                "--skip-user-contracts",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode in {0, 2}
        payload = json.loads(proc.stdout)
        
        check_names = {item.get("name") for item in payload.get("checks", [])}
        required_checks = {
            "sqlite_fallback_policy",
            "alembic_heads",
            "alembic_db_revision_match",
            "critical_tables_presence",
            "final_release_smoke_suite",
        }
        for check in required_checks:
            assert check in check_names, f"Required check '{check}' not found in output"

    def test_prod_mode_strict_sqlite_fallback(self):
        """Test: Prod mode is strict about sqlite_fallback_policy (expects ALEMBIC_ALLOW_SQLITE_FALLBACK=0)"""
        proc = subprocess.run(
            [
                "python",
                "/app/backend/cli/p0_closure_gate.py",
                "--target-env",
                "prod",
                "--skip-user-contracts",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # In preview env with SQLite, prod mode should return exit code 2 (FAIL)
        payload = json.loads(proc.stdout)
        assert payload.get("target_env") == "prod"
        
        # Find sqlite_fallback_policy check
        sqlite_check = next(
            (c for c in payload.get("checks", []) if c.get("name") == "sqlite_fallback_policy"),
            None,
        )
        assert sqlite_check is not None
        # Since ALEMBIC_ALLOW_SQLITE_FALLBACK=1 in backend/.env, prod should FAIL
        if sqlite_check.get("details", {}).get("value") == "1":
            assert sqlite_check.get("status") == "FAIL", "Prod should FAIL when ALEMBIC_ALLOW_SQLITE_FALLBACK=1"
            assert proc.returncode == 2, "Exit code should be 2 when overall is FAIL"

    def test_exit_code_behavior(self):
        """Test: Exit code is 0 when overall PASS, 2 when overall FAIL"""
        # Run with preview mode (should likely PASS)
        proc_preview = subprocess.run(
            [
                "python",
                "/app/backend/cli/p0_closure_gate.py",
                "--target-env",
                "preview",
                "--skip-user-contracts",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        payload_preview = json.loads(proc_preview.stdout)
        expected_exit_preview = 0 if payload_preview.get("overall") == "PASS" else 2
        assert proc_preview.returncode == expected_exit_preview


class TestFinalReleaseSmokeScript:
    """Tests for final_release_smoke_suite.py CLI script"""

    def test_smoke_suite_runs_and_returns_json(self):
        """Test: final_release_smoke_suite.py runs and returns valid JSON"""
        proc = subprocess.run(
            ["python", "/app/backend/cli/final_release_smoke_suite.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode in {0, 1}, f"Unexpected exit code: {proc.returncode}"
        
        payload = json.loads(proc.stdout)
        assert "generated_at" in payload
        assert "base_url" in payload
        assert "checks" in payload
        assert "overall" in payload
        assert payload["overall"] in {"PASS", "FAIL"}

    def test_smoke_suite_required_checks(self):
        """Test: final_release_smoke_suite.py has required checks"""
        proc = subprocess.run(
            ["python", "/app/backend/cli/final_release_smoke_suite.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(proc.stdout)
        
        check_names = {item.get("name") for item in payload.get("checks", [])}
        # These are the checks in final_release_smoke_suite.py
        expected_checks = {
            "health_endpoint",
            "admin_login",
            "futures_live_path_check",
            "alert_burnin",
            "audit_timeline",
            "incident_export",
        }
        for check in expected_checks:
            assert check in check_names, f"Expected check '{check}' not found"


class TestReleaseReadinessChecklist:
    """Tests for release_readiness_final_checklist.md"""

    def test_checklist_file_exists(self):
        """Test: release_readiness_final_checklist.md file exists"""
        checklist_path = Path("/app/memory/release_readiness_final_checklist.md")
        assert checklist_path.exists(), "release_readiness_final_checklist.md not found"

    def test_checklist_contains_required_commands(self):
        """Test: Checklist contains up-to-date automation commands"""
        checklist_path = Path("/app/memory/release_readiness_final_checklist.md")
        content = checklist_path.read_text(encoding="utf-8")
        
        # Check for automation commands
        assert "python /app/backend/cli/final_release_smoke_suite.py" in content
        assert "python /app/backend/cli/p0_closure_gate.py --target-env preview" in content
        assert "python /app/backend/cli/p0_closure_gate.py --target-env prod" in content

    def test_checklist_contains_critical_tables(self):
        """Test: Checklist mentions critical tables"""
        checklist_path = Path("/app/memory/release_readiness_final_checklist.md")
        content = checklist_path.read_text(encoding="utf-8")
        
        critical_tables = [
            "users",
            "bot_profiles",
            "risk_policies",
            "pending_signals",
            "admin_control",
            "audit_logs",
            "signal_events",
            "paper_positions",
        ]
        for table in critical_tables:
            assert table in content, f"Critical table '{table}' not mentioned in checklist"

    def test_checklist_contains_contract_smoke_items(self):
        """Test: Checklist contains contract/API smoke items"""
        checklist_path = Path("/app/memory/release_readiness_final_checklist.md")
        content = checklist_path.read_text(encoding="utf-8")
        
        # Check for leverage fields
        assert "requested_leverage" in content
        assert "recommended_leverage" in content
        assert "applied_leverage" in content
        
        # Check for exchange connection endpoints
        assert "/api/user/exchange-connections" in content
        assert "revalidate" in content
        
        # Check for incident export
        assert "incident-export" in content


class TestUserContractChecks:
    """Tests for user contract checks (run without --skip-user-contracts)"""

    def test_full_run_with_user_contracts(self):
        """Test: Full run includes user contract checks when not skipped"""
        proc = subprocess.run(
            [
                "python",
                "/app/backend/cli/p0_closure_gate.py",
                "--target-env",
                "preview",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert proc.returncode in {0, 2}
        payload = json.loads(proc.stdout)
        
        check_names = {item.get("name") for item in payload.get("checks", [])}
        
        # When not skipped, user contract checks should be present
        # Either as individual checks or user_contract_checks with FAIL reason
        if "user_contract_checks" in check_names:
            # If user_contract_checks is present, it should NOT be SKIP
            contract_check = next(c for c in payload["checks"] if c["name"] == "user_contract_checks")
            # If it's SKIP here without flag, something is wrong
            if contract_check.get("status") == "SKIP":
                pytest.fail("user_contract_checks should not be SKIP when --skip-user-contracts is not used")
        else:
            # Individual user contract checks should be present
            user_contract_checks = {
                "user_approve",
                "trading_preview_leverage_fields",
                "exchange_connections_list",
                "exchange_connection_revalidate",
                "bot_soft_delete_hidden",
            }
            # At least some should be present
            found = user_contract_checks & check_names
            assert len(found) >= 3, f"Expected user contract checks, found: {found}"
