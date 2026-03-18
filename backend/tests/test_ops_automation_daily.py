import json
import subprocess


def test_daily_ops_automation_dry_run_executes():
    proc = subprocess.run(
        [
            "python",
            "/app/backend/cli/daily_ops_automation.py",
            "--gate-file",
            "/app/test_reports/release_gate_latest.json",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert "gate_overall" in payload
    assert "storage" in payload
    assert "before" in payload["storage"]
    assert "after" in payload["storage"]
    assert "slo_30d" in payload
    assert isinstance(payload.get("actions"), list)
