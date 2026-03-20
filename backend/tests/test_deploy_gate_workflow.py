"""
Test deploy-gate.yml workflow configuration for yarn install resilience.
Tests the frontend-quality-gate job's yarn install step with:
- Registry configuration
- Network timeout
- Retry loop (3 attempts)
- Proper break/fail logic
"""

import pytest
import re
import yaml
import os

WORKFLOW_PATH = "/app/.github/workflows/deploy-gate.yml"


class TestDeployGateWorkflow:
    """Tests for deploy-gate.yml workflow yarn install resilience"""

    @pytest.fixture(scope="class")
    def workflow_content(self):
        """Load workflow file content"""
        with open(WORKFLOW_PATH, "r") as f:
            return f.read()

    @pytest.fixture(scope="class")
    def parsed_yaml(self, workflow_content):
        """Parse workflow YAML"""
        return yaml.safe_load(workflow_content)

    @pytest.fixture(scope="class")
    def frontend_install_step(self, parsed_yaml):
        """Extract the frontend install dependencies step"""
        frontend_job = parsed_yaml.get("jobs", {}).get("frontend-quality-gate", {})
        steps = frontend_job.get("steps", [])
        for step in steps:
            if step.get("name") == "Install frontend dependencies":
                return step
        return None

    def test_workflow_file_exists(self):
        """Verify deploy-gate.yml file exists"""
        assert os.path.exists(WORKFLOW_PATH), f"Workflow file not found: {WORKFLOW_PATH}"
        print(f"✅ Workflow file exists: {WORKFLOW_PATH}")

    def test_workflow_yaml_valid(self, workflow_content):
        """Verify YAML syntax is valid"""
        try:
            yaml.safe_load(workflow_content)
            print("✅ YAML syntax is valid")
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML syntax: {e}")

    def test_frontend_quality_gate_job_exists(self, parsed_yaml):
        """Verify frontend-quality-gate job exists"""
        jobs = parsed_yaml.get("jobs", {})
        assert "frontend-quality-gate" in jobs, "frontend-quality-gate job not found"
        print("✅ frontend-quality-gate job exists")

    def test_frontend_install_step_exists(self, frontend_install_step):
        """Verify Install frontend dependencies step exists"""
        assert frontend_install_step is not None, "Install frontend dependencies step not found"
        print("✅ 'Install frontend dependencies' step exists")

    def test_yarn_registry_configured(self, frontend_install_step):
        """Verify yarn registry is set to https://registry.npmjs.org"""
        run_script = frontend_install_step.get("run", "")
        assert "yarn config set registry https://registry.npmjs.org" in run_script, \
            "Yarn registry configuration not found"
        print("✅ Yarn registry is configured: https://registry.npmjs.org")

    def test_network_timeout_configured(self, frontend_install_step):
        """Verify --network-timeout 600000 (10 min) is set"""
        run_script = frontend_install_step.get("run", "")
        assert "--network-timeout 600000" in run_script, \
            "Network timeout 600000 not found in yarn install command"
        print("✅ Network timeout is configured: --network-timeout 600000 (10 min)")

    def test_frozen_lockfile_used(self, frontend_install_step):
        """Verify --frozen-lockfile flag is used for deterministic installs"""
        run_script = frontend_install_step.get("run", "")
        assert "--frozen-lockfile" in run_script, \
            "--frozen-lockfile flag not found in yarn install command"
        print("✅ --frozen-lockfile flag is used for deterministic installs")

    def test_retry_loop_3_attempts(self, frontend_install_step):
        """Verify retry loop has 3 attempts"""
        run_script = frontend_install_step.get("run", "")
        # Check for loop with 3 iterations
        assert re.search(r"for\s+attempt\s+in\s+1\s+2\s+3", run_script), \
            "Retry loop with 3 attempts not found"
        print("✅ Retry loop is configured with 3 attempts")

    def test_break_on_success_logic(self, frontend_install_step):
        """Verify break is called when yarn install succeeds"""
        run_script = frontend_install_step.get("run", "")
        # Check for if yarn install ... then break pattern
        assert "if yarn install" in run_script and "break" in run_script, \
            "Break on success logic not found"
        print("✅ Break on success logic is correctly implemented")

    def test_fail_after_3_attempts(self, frontend_install_step):
        """Verify script exits with error after 3 failed attempts"""
        run_script = frontend_install_step.get("run", "")
        # Check for attempt == 3 and exit 1 pattern
        assert 'if [[ "$attempt" == "3" ]]' in run_script, \
            "Attempt 3 check not found"
        assert "exit 1" in run_script, \
            "exit 1 not found for failure case"
        print("✅ Script correctly fails after 3 attempts")

    def test_cache_clean_on_retry(self, frontend_install_step):
        """Verify yarn cache clean is called between retries"""
        run_script = frontend_install_step.get("run", "")
        assert "yarn cache clean" in run_script, \
            "yarn cache clean not found in retry logic"
        print("✅ yarn cache clean is called between retries")

    def test_sleep_between_retries(self, frontend_install_step):
        """Verify sleep is used between retries"""
        run_script = frontend_install_step.get("run", "")
        assert "sleep" in run_script, \
            "sleep command not found between retries"
        print("✅ Sleep is used between retries")

    def test_working_directory_is_frontend(self, frontend_install_step):
        """Verify working-directory is set to frontend"""
        working_dir = frontend_install_step.get("working-directory", "")
        assert working_dir == "frontend", \
            f"Expected working-directory='frontend', got '{working_dir}'"
        print("✅ working-directory is correctly set to 'frontend'")

    def test_full_retry_logic_structure(self, frontend_install_step):
        """Verify the complete retry logic structure is correct"""
        run_script = frontend_install_step.get("run", "")
        
        # Verify the complete structure
        expected_patterns = [
            r"yarn config set registry https://registry\.npmjs\.org",
            r"for attempt in 1 2 3",
            r"echo.*Yarn install attempt",
            r"if yarn install --frozen-lockfile --network-timeout 600000; then",
            r"break",
            r"fi",
            r'if \[\[ "\$attempt" == "3" \]\]',
            r"exit 1",
            r"yarn cache clean",
            r"sleep \d+",
            r"done",
        ]
        
        for pattern in expected_patterns:
            assert re.search(pattern, run_script), \
                f"Expected pattern not found: {pattern}"
        
        print("✅ Full retry logic structure is valid and complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
