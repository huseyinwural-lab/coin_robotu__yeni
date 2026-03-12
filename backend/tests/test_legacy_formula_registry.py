import json
from pathlib import Path


def test_legacy_formula_registry_has_required_fields_and_unique_canonical_names():
    registry_path = Path(__file__).resolve().parents[1] / "core" / "strategies" / "legacy" / "legacy_formula_registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))

    required = {"family_code", "source_files", "canonical_name", "role", "status"}
    canonical_by_family = {}
    for row in payload:
        assert required.issubset(set(row.keys()))
        family = row["family_code"]
        canonical = row["canonical_name"]
        assert isinstance(row["source_files"], list) and row["source_files"]
        canonical_by_family.setdefault(family, canonical)
        assert canonical_by_family[family] == canonical

    strategy_rows = [row for row in payload if row["role"] == "strategy"]
    assert len(strategy_rows) == 4
