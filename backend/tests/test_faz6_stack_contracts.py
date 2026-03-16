"""
FAZ-6 Stack Health + Redis + Frontend Connectivity - Static/Contract Level Tests
Tests docker-compose.yml, verify script, and workflow configuration without running docker.
"""

import pytest
import yaml
import re
from pathlib import Path

# Paths
DOCKER_COMPOSE_PATH = Path("/app/docker-compose.yml")
VERIFY_SCRIPT_PATH = Path("/app/scripts/verify_faz6_stack_connectivity.sh")
WORKFLOW_PATH = Path("/app/.github/workflows/faz6-stack-health-connectivity.yml")


class TestDockerComposeHealthchecks:
    """Verify docker-compose.yml has correct healthchecks for all services"""

    @pytest.fixture(scope="class")
    def compose_config(self):
        """Load docker-compose.yml"""
        assert DOCKER_COMPOSE_PATH.exists(), f"docker-compose.yml not found at {DOCKER_COMPOSE_PATH}"
        return yaml.safe_load(DOCKER_COMPOSE_PATH.read_text())

    def test_postgres_healthcheck_exists(self, compose_config):
        """postgres service should have healthcheck"""
        services = compose_config.get("services", {})
        postgres = services.get("postgres", {})
        healthcheck = postgres.get("healthcheck", {})
        
        assert healthcheck, "postgres service missing healthcheck"
        assert "test" in healthcheck, "postgres healthcheck missing test command"
        test_cmd = " ".join(healthcheck["test"]) if isinstance(healthcheck["test"], list) else healthcheck["test"]
        assert "pg_isready" in test_cmd, "postgres healthcheck should use pg_isready"
        print(f"[OK] postgres healthcheck: {healthcheck['test']}")

    def test_redis_healthcheck_exists(self, compose_config):
        """redis service should have healthcheck"""
        services = compose_config.get("services", {})
        redis = services.get("redis", {})
        healthcheck = redis.get("healthcheck", {})
        
        assert healthcheck, "redis service missing healthcheck"
        assert "test" in healthcheck, "redis healthcheck missing test command"
        test_cmd = " ".join(healthcheck["test"]) if isinstance(healthcheck["test"], list) else healthcheck["test"]
        assert "redis-cli" in test_cmd and "ping" in test_cmd, "redis healthcheck should use redis-cli ping"
        print(f"[OK] redis healthcheck: {healthcheck['test']}")

    def test_backend_healthcheck_exists(self, compose_config):
        """backend service should have healthcheck"""
        services = compose_config.get("services", {})
        backend = services.get("backend", {})
        healthcheck = backend.get("healthcheck", {})
        
        assert healthcheck, "backend service missing healthcheck"
        assert "test" in healthcheck, "backend healthcheck missing test command"
        test_cmd = " ".join(healthcheck["test"]) if isinstance(healthcheck["test"], list) else healthcheck["test"]
        assert "/api/health" in test_cmd or "health" in test_cmd.lower(), "backend healthcheck should check /api/health"
        print(f"[OK] backend healthcheck: {healthcheck['test']}")

    def test_frontend_healthcheck_exists(self, compose_config):
        """frontend service should have healthcheck"""
        services = compose_config.get("services", {})
        frontend = services.get("frontend", {})
        healthcheck = frontend.get("healthcheck", {})
        
        assert healthcheck, "frontend service missing healthcheck"
        assert "test" in healthcheck, "frontend healthcheck missing test command"
        print(f"[OK] frontend healthcheck: {healthcheck['test']}")


class TestDockerComposeDependsOn:
    """Verify depends_on service_healthy chain is correct"""

    @pytest.fixture(scope="class")
    def compose_config(self):
        """Load docker-compose.yml"""
        return yaml.safe_load(DOCKER_COMPOSE_PATH.read_text())

    def test_backend_depends_on_postgres_healthy(self, compose_config):
        """backend should depend on postgres with service_healthy condition"""
        services = compose_config.get("services", {})
        backend = services.get("backend", {})
        depends_on = backend.get("depends_on", {})
        
        assert "postgres" in depends_on, "backend should depend on postgres"
        postgres_dep = depends_on.get("postgres", {})
        assert postgres_dep.get("condition") == "service_healthy", \
            f"backend->postgres should use service_healthy, got: {postgres_dep.get('condition')}"
        print("[OK] backend depends_on postgres: service_healthy")

    def test_backend_depends_on_redis_healthy(self, compose_config):
        """backend should depend on redis with service_healthy condition"""
        services = compose_config.get("services", {})
        backend = services.get("backend", {})
        depends_on = backend.get("depends_on", {})
        
        assert "redis" in depends_on, "backend should depend on redis"
        redis_dep = depends_on.get("redis", {})
        assert redis_dep.get("condition") == "service_healthy", \
            f"backend->redis should use service_healthy, got: {redis_dep.get('condition')}"
        print("[OK] backend depends_on redis: service_healthy")

    def test_frontend_depends_on_backend_healthy(self, compose_config):
        """frontend should depend on backend with service_healthy condition"""
        services = compose_config.get("services", {})
        frontend = services.get("frontend", {})
        depends_on = frontend.get("depends_on", {})
        
        assert "backend" in depends_on, "frontend should depend on backend"
        backend_dep = depends_on.get("backend", {})
        assert backend_dep.get("condition") == "service_healthy", \
            f"frontend->backend should use service_healthy, got: {backend_dep.get('condition')}"
        print("[OK] frontend depends_on backend: service_healthy")


class TestVerifyScriptStructure:
    """Verify verify_faz6_stack_connectivity.sh script structure and content"""

    @pytest.fixture(scope="class")
    def script_content(self):
        """Load verify script"""
        assert VERIFY_SCRIPT_PATH.exists(), f"Verify script not found at {VERIFY_SCRIPT_PATH}"
        return VERIFY_SCRIPT_PATH.read_text()

    def test_script_has_fail_fast(self, script_content):
        """Script should use set -euo pipefail for fail-fast"""
        assert "set -euo pipefail" in script_content or "set -e" in script_content, \
            "Script should have fail-fast with set -e or set -euo pipefail"
        print("[OK] Script has fail-fast: set -euo pipefail")

    def test_script_has_docker_compose_up(self, script_content):
        """Script should start docker stack"""
        assert "docker compose up" in script_content or "docker-compose up" in script_content, \
            "Script should start docker stack"
        print("[OK] Script starts docker stack")

    def test_script_validates_healthcheck_presence(self, script_content):
        """Script should validate healthcheck presence in compose"""
        assert "healthcheck" in script_content.lower(), \
            "Script should validate healthcheck presence"
        assert "yaml" in script_content.lower() or "YAML" in script_content, \
            "Script should parse YAML to validate healthchecks"
        print("[OK] Script validates healthcheck presence")

    def test_script_redis_check_from_redis_container(self, script_content):
        """Script should check redis connectivity from redis container"""
        assert "exec -T redis" in script_content and "redis-cli ping" in script_content, \
            "Script should check redis connectivity from redis container"
        print("[OK] Script checks redis from redis container")

    def test_script_redis_check_from_backend_container(self, script_content):
        """Script should check redis connectivity from backend container"""
        assert "exec -T backend" in script_content, \
            "Script should check from backend container"
        # Check for python redis ping in backend container
        assert "redis" in script_content.lower() and "ping" in script_content.lower(), \
            "Script should check redis ping from backend"
        print("[OK] Script checks redis from backend container")

    def test_script_frontend_env_validation(self, script_content):
        """Script should validate frontend runtime environment"""
        assert "REACT_APP_BACKEND_URL" in script_content, \
            "Script should check REACT_APP_BACKEND_URL in frontend"
        assert "exec -T frontend" in script_content, \
            "Script should exec into frontend container"
        print("[OK] Script validates frontend runtime env")

    def test_script_frontend_backend_network_check(self, script_content):
        """Script should check frontend->backend network connectivity"""
        # Should call backend from frontend container
        assert "backend:8001" in script_content or "http://backend" in script_content, \
            "Script should check frontend->backend network connectivity"
        assert "/api/health" in script_content, \
            "Script should check backend health from frontend"
        print("[OK] Script checks frontend->backend network")

    def test_script_frontend_auth_flow_smoke(self, script_content):
        """Script should include frontend auth flow smoke test"""
        assert "/api/auth/login" in script_content or "auth" in script_content.lower(), \
            "Script should include auth flow smoke test"
        # Check for login credentials
        assert "admin@platform.local" in script_content or "email" in script_content.lower(), \
            "Script should use login credentials for auth smoke"
        print("[OK] Script includes frontend auth flow smoke")

    def test_script_step_order_logical(self, script_content):
        """Script steps should be in logical order"""
        # Extract step numbers
        steps = re.findall(r'\[(\d+)/\d+\]', script_content)
        expected_order = ['1', '2', '3', '4', '5', '6', '7']
        
        assert steps == expected_order, f"Steps should be in order 1-7, got: {steps}"
        print(f"[OK] Script steps in correct order: {steps}")


class TestWorkflowStructure:
    """Verify GitHub Actions workflow configuration"""

    @pytest.fixture(scope="class")
    def workflow_config(self):
        """Load workflow YAML"""
        assert WORKFLOW_PATH.exists(), f"Workflow not found at {WORKFLOW_PATH}"
        return yaml.safe_load(WORKFLOW_PATH.read_text())

    @pytest.fixture(scope="class")
    def workflow_content(self):
        """Load workflow raw content"""
        return WORKFLOW_PATH.read_text()

    def test_workflow_runs_verify_script(self, workflow_content):
        """Workflow should run the verify script"""
        assert "verify_faz6_stack_connectivity.sh" in workflow_content, \
            "Workflow should run verify_faz6_stack_connectivity.sh"
        print("[OK] Workflow runs verify script")

    def test_workflow_uploads_artifacts(self, workflow_config, workflow_content):
        """Workflow should upload artifacts"""
        assert "upload-artifact" in workflow_content, \
            "Workflow should use upload-artifact action"
        print("[OK] Workflow uploads artifacts")

    def test_workflow_artifact_upload_always(self, workflow_content):
        """Workflow should upload artifacts even on failure (always condition)"""
        # Check for if: always() or if: ${{ always() }}
        assert "always()" in workflow_content, \
            "Workflow should upload artifacts with always() condition"
        print("[OK] Workflow uploads artifacts on always()")

    def test_workflow_uploads_relevant_logs(self, workflow_config):
        """Workflow should upload relevant log files"""
        jobs = workflow_config.get("jobs", {})
        verify_job = jobs.get("verify-stack", {})
        steps = verify_job.get("steps", [])
        
        # Find upload step
        upload_step = None
        for step in steps:
            if "upload-artifact" in str(step.get("uses", "")):
                upload_step = step
                break
        
        assert upload_step, "Should have upload-artifact step"
        
        # Check artifact paths
        artifact_with = upload_step.get("with", {})
        artifact_path = artifact_with.get("path", "")
        
        expected_logs = [
            "faz6_stack.log",
            "compose_ps.txt",
            "backend.log",
            "redis.log",
            "frontend_env.txt",
            "frontend_backend_health.txt",
            "frontend_auth_smoke.txt"
        ]
        
        for log in expected_logs:
            assert log in artifact_path, f"Artifact should include {log}"
        
        print(f"[OK] Workflow uploads all relevant logs")

    def test_workflow_has_checkout(self, workflow_content):
        """Workflow should checkout repository"""
        assert "actions/checkout" in workflow_content, \
            "Workflow should checkout repository"
        print("[OK] Workflow has checkout step")

    def test_workflow_uses_bash_shell(self, workflow_content):
        """Workflow should use bash shell for script execution"""
        assert "shell: bash" in workflow_content, \
            "Workflow should use bash shell"
        print("[OK] Workflow uses bash shell")


class TestDockerComposeAdditionalConfig:
    """Additional docker-compose configuration validation"""

    @pytest.fixture(scope="class")
    def compose_config(self):
        """Load docker-compose.yml"""
        return yaml.safe_load(DOCKER_COMPOSE_PATH.read_text())

    def test_frontend_has_react_app_backend_url_env(self, compose_config):
        """Frontend should have REACT_APP_BACKEND_URL environment variable"""
        services = compose_config.get("services", {})
        frontend = services.get("frontend", {})
        environment = frontend.get("environment", {})
        
        assert "REACT_APP_BACKEND_URL" in environment, \
            "Frontend should have REACT_APP_BACKEND_URL in environment"
        print(f"[OK] Frontend has REACT_APP_BACKEND_URL: {environment.get('REACT_APP_BACKEND_URL')}")

    def test_backend_has_redis_url_env(self, compose_config):
        """Backend should have REDIS_URL environment variable"""
        services = compose_config.get("services", {})
        backend = services.get("backend", {})
        environment = backend.get("environment", {})
        
        assert "REDIS_URL" in environment, \
            "Backend should have REDIS_URL in environment"
        assert "redis://" in environment.get("REDIS_URL", ""), \
            "REDIS_URL should be a valid redis URL"
        print(f"[OK] Backend has REDIS_URL: {environment.get('REDIS_URL')}")

    def test_frontend_command_validates_env(self, compose_config):
        """Frontend command should validate REACT_APP_BACKEND_URL"""
        services = compose_config.get("services", {})
        frontend = services.get("frontend", {})
        command = frontend.get("command", "")
        
        assert "REACT_APP_BACKEND_URL" in command and "test" in command, \
            "Frontend command should validate REACT_APP_BACKEND_URL"
        print("[OK] Frontend command validates REACT_APP_BACKEND_URL")
