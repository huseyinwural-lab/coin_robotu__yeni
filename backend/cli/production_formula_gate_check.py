import sys

from core.execution.production_formula_gate import ProductionFormulaGateError, load_active_formula_registry
from services.formula_gate_service import scan_production_import_violations


def main() -> int:
    try:
        registry = load_active_formula_registry()
    except ProductionFormulaGateError as exc:
        print("formula_gate_status=BLOCKED")
        print(f"reason={exc}")
        return 2

    violations = scan_production_import_violations()
    if violations:
        print("formula_gate_status=BLOCKED")
        print("reason=research_import_detected")
        print(f"violation_count={len(violations)}")
        first = violations[0]
        print(f"violation_file={first['file']}")
        print(f"violation_pattern={first['denied_pattern']}")
        return 2

    print("formula_gate_status=PASS")
    print(f"allowed_formula_count={len(registry.get('allowed_formula_ids') or [])}")
    print(f"registry_version={registry.get('registry_version', 'unknown')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
