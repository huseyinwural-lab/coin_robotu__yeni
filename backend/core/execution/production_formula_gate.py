import json
from pathlib import Path

ACTIVE_FORMULA_REGISTRY_PATH = Path("/app/strategies/active_formula_registry.json")


class ProductionFormulaGateError(RuntimeError):
    pass


def load_active_formula_registry(path: Path = ACTIVE_FORMULA_REGISTRY_PATH) -> dict:
    if not path.exists():
        raise ProductionFormulaGateError(f"active_formula_registry_missing:{path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed_formula_ids = payload.get("allowed_formula_ids") or []
    if not isinstance(allowed_formula_ids, list) or not allowed_formula_ids:
        raise ProductionFormulaGateError("active_formula_registry_invalid:allowed_formula_ids")

    payload["allowed_formula_ids"] = [str(formula_id) for formula_id in allowed_formula_ids]
    return payload


def get_allowed_formula_ids(path: Path = ACTIVE_FORMULA_REGISTRY_PATH) -> set[str]:
    payload = load_active_formula_registry(path)
    return set(payload["allowed_formula_ids"])


def filter_catalog_by_active_registry(catalog: dict[str, dict], path: Path = ACTIVE_FORMULA_REGISTRY_PATH) -> dict[str, dict]:
    allowed_formula_ids = get_allowed_formula_ids(path)
    filtered = {strategy_id: row for strategy_id, row in catalog.items() if strategy_id in allowed_formula_ids}
    if not filtered:
        raise ProductionFormulaGateError("active_formula_registry_blocks_all_strategies")
    return filtered


def assert_formula_allowed(formula_id: str, path: Path = ACTIVE_FORMULA_REGISTRY_PATH) -> None:
    allowed_formula_ids = get_allowed_formula_ids(path)
    if formula_id not in allowed_formula_ids:
        raise ProductionFormulaGateError(f"formula_not_allowed:{formula_id}")
