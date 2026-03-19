# ruff: noqa: E402
from pathlib import Path
import subprocess
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.production_formula_gate import ProductionFormulaGateError, assert_formula_allowed
from services.formula_gate_service import scan_production_import_violations


def test_runtime_gate_rejects_unknown_formula_id():
    try:
        assert_formula_allowed("unknown_formula_id_not_allowed")
        assert False, "gate should reject unknown formula"
    except ProductionFormulaGateError as exc:
        assert "formula_not_allowed" in str(exc)


def test_static_import_scan_detects_research_import_on_temp_code(tmp_path: Path):
    root = tmp_path / "backend"
    services_dir = root / "services"
    services_dir.mkdir(parents=True, exist_ok=True)

    candidate = services_dir / "sample_runtime.py"
    candidate.write_text("from research.formulas import alpha_model\n", encoding="utf-8")

    violations = scan_production_import_violations(root)
    assert len(violations) == 1
    assert violations[0]["file"] == "services/sample_runtime.py"
    assert violations[0]["denied_pattern"] in {"from research", "import research"}


def test_static_import_scan_allows_clean_temp_code(tmp_path: Path):
    root = tmp_path / "backend"
    core_dir = root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)

    candidate = core_dir / "engine.py"
    candidate.write_text("from core.execution.gate import run\n", encoding="utf-8")

    violations = scan_production_import_violations(root)
    assert violations == []


def test_formula_gate_ci_script_returns_valid_status():
    result = subprocess.run(["/app/scripts/run_formula_gate_check.sh"], capture_output=True, text=True)
    assert result.returncode in {0, 2}
    assert "formula_gate_status=" in result.stdout
