import json
import subprocess


def test_p0_closure_gate_preview_mode_runs():
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
    assert payload.get("target_env") == "preview"
    assert "overall" in payload
    assert isinstance(payload.get("checks"), list)
    check_names = {item.get("name") for item in payload.get("checks", [])}
    assert "critical_tables_presence" in check_names
    assert "final_release_smoke_suite" in check_names
