import json
from pathlib import Path

RESEARCH_ROOT = Path("/app/research")


def load_research_manifest() -> dict:
    manifest_path = RESEARCH_ROOT / "research_namespace_manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_formula_decomposition() -> dict:
    decomposition_path = RESEARCH_ROOT / "formula_decomposition_18M.json"
    if not decomposition_path.exists():
        return {}
    return json.loads(decomposition_path.read_text(encoding="utf-8"))
