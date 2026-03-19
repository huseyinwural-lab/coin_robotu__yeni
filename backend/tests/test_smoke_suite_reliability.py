"""
Test suite for final_release_smoke_suite.py reliability fixes.

Tests verify:
1. Script never crashes with traceback on network failures
2. With valid URL, smoke suite completes and returns JSON output  
3. With unreachable URL, smoke suite returns graceful FAIL JSON and exit code 1
"""

import json
import os
import subprocess
import sys

import pytest

# Add backend to path for imports
sys.path.insert(0, "/app/backend")

# Get base URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
if not BASE_URL:
    env_file = "/app/frontend/.env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip()
                    break


class TestSmokeScriptReliability:
    """Tests for smoke script crash-safety and reliability - Unit tests for helper functions"""

    def test_script_module_imports_correctly(self):
        """Verify the smoke suite module can be imported without errors"""
        try:
            from cli.final_release_smoke_suite import run, _http_request, _safe_json, _check
            assert callable(run)
            assert callable(_http_request)
            assert callable(_safe_json)
            assert callable(_check)
            print("PASS: Module imports correctly with all expected functions")
        except ImportError as e:
            pytest.fail(f"Module import failed: {e}")

    def test_http_request_wrapper_handles_connection_error(self):
        """Verify _http_request returns (None, error_string) on connection error - no traceback"""
        from cli.final_release_smoke_suite import _http_request
        
        # Use an unreachable URL
        response, error = _http_request("GET", "http://127.0.0.1:59999/unreachable", timeout=2)
        
        assert response is None, "Expected None response for unreachable URL"
        assert error is not None, "Expected error string for unreachable URL"
        assert isinstance(error, str), "Error should be a string"
        print(f"PASS: _http_request gracefully returns error: {error[:80]}...")

    def test_http_request_wrapper_handles_timeout(self):
        """Verify _http_request handles timeout without traceback"""
        from cli.final_release_smoke_suite import _http_request
        
        # Use httpbin delay endpoint or similar - we'll use very short timeout
        # This tests the timeout handling path
        response, error = _http_request("GET", "http://httpbin.org/delay/10", timeout=1)
        
        # Should return gracefully, not crash
        assert response is None or error is not None, "Should handle timeout gracefully"
        print("PASS: _http_request handles timeout gracefully")

    def test_safe_json_handles_none_response(self):
        """Verify _safe_json returns empty dict for None response"""
        from cli.final_release_smoke_suite import _safe_json
        
        result = _safe_json(None)
        assert result == {}, "Expected empty dict for None response"
        print("PASS: _safe_json handles None response")

    def test_safe_json_handles_non_json_response(self):
        """Verify _safe_json returns empty dict for non-JSON response"""
        from cli.final_release_smoke_suite import _safe_json
        from unittest.mock import MagicMock
        
        # Create a mock response that will raise ValueError on .json()
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("No JSON")
        
        result = _safe_json(mock_response)
        assert result == {}, "Expected empty dict for invalid JSON"
        print("PASS: _safe_json handles non-JSON response")

    def test_check_function_returns_correct_structure(self):
        """Verify _check returns proper PASS/FAIL structure"""
        from cli.final_release_smoke_suite import _check
        
        pass_result = _check(True, "test_check", {"detail": "value"})
        assert pass_result["status"] == "PASS"
        assert pass_result["name"] == "test_check"
        assert pass_result["details"]["detail"] == "value"
        
        fail_result = _check(False, "fail_check")
        assert fail_result["status"] == "FAIL"
        assert fail_result["name"] == "fail_check"
        print("PASS: _check function returns correct structure")


class TestSmokeScriptExecution:
    """Integration tests for smoke script execution"""

    def test_smoke_script_with_valid_url_returns_json(self):
        """With valid preview URL, smoke suite should complete and return JSON output"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.final_release_smoke_suite"],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "REACT_APP_BACKEND_URL": BASE_URL}
        )
        
        # Script should complete without traceback
        assert "Traceback" not in result.stderr, f"Script crashed with traceback:\n{result.stderr}"
        
        # Output should be valid JSON
        try:
            output = json.loads(result.stdout)
            assert "generated_at" in output, "Missing generated_at field"
            assert "base_url" in output, "Missing base_url field"
            assert "checks" in output, "Missing checks field"
            assert "overall" in output, "Missing overall field"
            assert output["overall"] in ["PASS", "FAIL"], "overall must be PASS or FAIL"
            print(f"PASS: Smoke script returned valid JSON with overall={output['overall']}")
            print(f"  Base URL: {output['base_url']}")
            print(f"  Checks count: {len(output['checks'])}")
            for check in output["checks"]:
                print(f"    - {check['name']}: {check['status']}")
        except json.JSONDecodeError as e:
            pytest.fail(f"Output is not valid JSON: {e}\nStdout: {result.stdout}\nStderr: {result.stderr}")

    def test_smoke_script_with_unreachable_url_returns_graceful_fail(self):
        """With unreachable URL, smoke suite should return graceful FAIL JSON and exit code 1"""
        unreachable_url = "http://127.0.0.1:59999"
        
        result = subprocess.run(
            [sys.executable, "-m", "cli.final_release_smoke_suite"],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "REACT_APP_BACKEND_URL": unreachable_url}
        )
        
        # CRITICAL: Script should NOT crash with traceback
        assert "Traceback" not in result.stderr, f"Script crashed with traceback on unreachable URL:\n{result.stderr}"
        
        # Should return non-zero exit code
        assert result.returncode != 0, "Expected non-zero exit code for unreachable URL"
        
        # Output should still be valid JSON with FAIL status
        try:
            output = json.loads(result.stdout)
            assert output["overall"] == "FAIL", "Expected overall=FAIL for unreachable URL"
            assert "checks" in output, "Missing checks field"
            print("PASS: Smoke script gracefully failed with JSON output")
            print(f"  Exit code: {result.returncode}")
            print(f"  Overall: {output['overall']}")
            print(f"  Base URL: {output.get('base_url', 'N/A')}")
            for check in output.get("checks", []):
                print(f"    - {check['name']}: {check['status']}")
                if check.get("details", {}).get("error"):
                    print(f"      Error: {check['details']['error'][:60]}...")
        except json.JSONDecodeError as e:
            pytest.fail(f"Output is not valid JSON even on failure: {e}\nStdout: {result.stdout}\nStderr: {result.stderr}")

    def test_smoke_script_with_invalid_host_no_crash(self):
        """With completely invalid host, script should not crash with traceback"""
        invalid_url = "http://this-host-definitely-does-not-exist-12345.invalid"
        
        result = subprocess.run(
            [sys.executable, "-m", "cli.final_release_smoke_suite"],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "REACT_APP_BACKEND_URL": invalid_url}
        )
        
        # CRITICAL: No traceback even with DNS resolution failure
        assert "Traceback" not in result.stderr, f"Script crashed with traceback on invalid host:\n{result.stderr}"
        
        # Should still output JSON
        try:
            output = json.loads(result.stdout)
            assert output["overall"] == "FAIL"
            print("PASS: Script handled invalid host gracefully")
            print(f"  Exit code: {result.returncode}")
        except json.JSONDecodeError:
            pytest.fail(f"No JSON output for invalid host. Stdout: {result.stdout}\nStderr: {result.stderr}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
