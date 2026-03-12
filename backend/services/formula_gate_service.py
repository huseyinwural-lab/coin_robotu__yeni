from pathlib import Path

PRODUCTION_SCAN_ROOT = Path("/app/backend")
DENIED_IMPORT_PATTERNS = (
    "import research",
    "from research",
    "/app/research",
)
ALLOWED_PRODUCTION_REFERENCES = {
    "services/research_runner_service.py",
    "services/formula_gate_service.py",
    "cli/generate_research_legacy_artifacts.py",
    "cli/production_formula_gate_check.py",
}


def scan_production_import_violations(root_path: Path = PRODUCTION_SCAN_ROOT) -> list[dict]:
    violations: list[dict] = []
    for file_path in root_path.rglob("*.py"):
        rel_path = file_path.relative_to(root_path).as_posix()
        if rel_path.startswith(("tests/", "migrations/", "__pycache__/")):
            continue
        if rel_path in ALLOWED_PRODUCTION_REFERENCES:
            continue

        payload = file_path.read_text(encoding="utf-8")
        for denied_pattern in DENIED_IMPORT_PATTERNS:
            if denied_pattern in payload:
                violations.append(
                    {
                        "file": rel_path,
                        "denied_pattern": denied_pattern,
                    }
                )
    return violations
