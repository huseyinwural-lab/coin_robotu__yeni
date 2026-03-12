import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.execution.production_formula_gate import get_allowed_formula_ids, load_active_formula_registry
from core.portfolio.strategy_registry import build_strategy_catalog

RESEARCH_ROOT = Path("/app/research")
REPORTS_ROOT = Path("/app/reports")
STRATEGIES_ROOT = Path("/app/strategies")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_research_namespace_directories_exist():
    for folder in ["formulas", "experiments", "notebooks", "excluded"]:
        assert (RESEARCH_ROOT / folder).exists(), f"missing folder: {folder}"


def test_research_namespace_manifest_schema():
    payload = _load_json(RESEARCH_ROOT / "research_namespace_manifest.json")
    required_fields = {
        "allowed_readers",
        "denied_modules",
        "registry_source",
        "generation_timestamp",
        "isolation_policy_version",
    }
    assert required_fields.issubset(set(payload.keys()))
    assert isinstance(payload["allowed_readers"], list) and payload["allowed_readers"]
    assert isinstance(payload["denied_modules"], list) and payload["denied_modules"]


def test_formula_decomposition_18m_consistency():
    payload = _load_json(RESEARCH_ROOT / "formula_decomposition_18M.json")
    assert payload["dataset_size"] == 18_000_000
    for segment in ["ACTIVE", "EXPERIMENTAL", "LEGACY", "EXCLUDED"]:
        assert segment in payload["segments"]
        assert payload["segments"][segment]["count"] > 0
    assert payload["consistency"]["is_consistent"] is True
    assert payload["consistency"]["total_count_check"] == 18_000_000


def test_excluded_reports_are_mirrored_and_schema_valid():
    research_rows = _load_json(RESEARCH_ROOT / "excluded_formula_report.json")
    release_rows = _load_json(REPORTS_ROOT / "excluded_formula_report.json")
    assert research_rows == release_rows

    required = {"formula_id", "exclusion_reason", "risk_class", "source_registry", "timestamp"}
    assert research_rows, "excluded report should not be empty"
    for row in research_rows:
        assert required.issubset(set(row.keys()))


def test_strategy_matrix_one_formula_one_strategy_and_no_orphan():
    payload = _load_json(REPORTS_ROOT / "legacy_formula_strategy_matrix.json")
    mapping = payload["formula_to_strategy"]
    values = list(mapping.values())
    assert len(mapping.keys()) == len(set(mapping.keys()))
    for strategy_class in values:
        assert strategy_class in {"momentum", "mean_reversion", "breakout", "volatility", "market_neutral"}
    assert payload["orphan_formulas"] == []


def test_legacy_integration_report_schema_and_uniqueness():
    payload = _load_json(REPORTS_ROOT / "legacy_formula_integration_report.json")
    rows = payload["rows"]
    required = {
        "legacy_formula_id",
        "mapped_strategy",
        "integration_status",
        "performance_tag",
        "source_origin",
        "migration_decision",
    }
    ids = []
    for row in rows:
        assert required.issubset(set(row.keys()))
        ids.append(row["legacy_formula_id"])
    assert len(ids) == len(set(ids)), "duplicate legacy formula rows detected"


def test_active_formula_registry_and_runtime_filtering():
    registry = load_active_formula_registry()
    assert registry["allowed_formula_ids"]
    allowed_ids = get_allowed_formula_ids()
    catalog = build_strategy_catalog()
    assert set(catalog.keys()).issubset(allowed_ids)
    assert len(catalog) > 0


def test_active_registry_is_created_in_expected_path():
    path = STRATEGIES_ROOT / "active_formula_registry.json"
    assert path.exists()
    payload = _load_json(path)
    assert payload.get("registry_version")
    assert payload.get("allowed_formula_ids")
