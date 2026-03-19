import re
from pathlib import Path


WORKFLOW_PATH = Path("/app/.github/workflows/deploy-gate.yml")
ARTIFACT_PATH = Path("/app/artifacts/faz2_ci_gate_check.log")


def test_faz2_ci_gate_includes_required_tests():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    required_patterns = [
        r"test_faz2_idempotency_key_unit\.py",
        r"test_faz2_execution_integrity\.py",
        r"test_faz2_unique_constraint_contract\.py",
    ]

    missing = [pattern for pattern in required_patterns if re.search(pattern, content) is None]

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        "\n".join(
            [
                "FAZ2_CI_GATE_CHECK_START",
                "REQUIRED_TESTS=" + ",".join(required_patterns),
                "MISSING=" + ",".join(missing),
                "FAZ2_CI_GATE_CHECK_PASS" if not missing else "FAZ2_CI_GATE_CHECK_FAIL",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert not missing
