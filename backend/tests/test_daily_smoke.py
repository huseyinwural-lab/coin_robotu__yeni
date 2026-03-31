import os
import subprocess


def test_daily_smoke_skipped_credential_model():
    env = os.environ.copy()
    env.setdefault("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com")
    env.setdefault("DAILY_SMOKE_ADMIN_EMAIL", "canary.admin@platform.local")
    env.setdefault("DAILY_SMOKE_ADMIN_PASSWORD", "CanaryAdmin123!")
    env.pop("DAILY_SMOKE_TARGET_USER_EMAIL", None)

    proc = subprocess.run(
        ["/root/.venv/bin/python", "/app/scripts/daily_smoke.py"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    combined = f"{proc.stdout}\n{proc.stderr}"
    assert "SKIPPED_CREDENTIAL_MISSING" in combined
    assert "overall_status" in combined
