#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    log_path = artifacts_dir / "config_schema_validation.log"
    summary_path = artifacts_dir / "config_schema_validation_summary.json"

    schema_path = root / "config.schema.json"
    sample_config_path = root / "config" / "app.runtime.example.json"

    lines: list[str] = []
    summary: dict[str, object] = {
      "status": "PASS",
      "schema_path": str(schema_path),
      "sample_config_path": str(sample_config_path),
      "errors": [],
    }

    try:
        if not schema_path.exists():
            raise FileNotFoundError(f"schema file missing: {schema_path}")
        if not sample_config_path.exists():
            raise FileNotFoundError(f"sample config file missing: {sample_config_path}")

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        sample_config = json.loads(sample_config_path.read_text(encoding="utf-8"))

        Draft202012Validator.check_schema(schema)
        lines.append("PASS: config.schema.json itself is a valid Draft 2020-12 schema")

        validator = Draft202012Validator(schema)
        validation_errors = sorted(validator.iter_errors(sample_config), key=lambda error: list(error.absolute_path))
        if validation_errors:
            for error in validation_errors:
                location = ".".join(str(part) for part in error.absolute_path) or "<root>"
                message = f"FAIL: sample config validation error at {location}: {error.message}"
                lines.append(message)
                summary["errors"].append({"path": location, "message": error.message})
            summary["status"] = "FAIL"
        else:
            lines.append("PASS: sample config matches config.schema.json")
    except Exception as exc:
        lines.append(f"FAIL: {exc}")
        summary["status"] = "FAIL"
        summary["errors"].append({"path": "<runtime>", "message": str(exc)})

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"Summary: {summary_path}")

    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
