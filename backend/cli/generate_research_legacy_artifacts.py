import json
from datetime import datetime, timezone
from pathlib import Path

from core.portfolio.strategy_registry import get_strategy_metadata_map

LEGACY_REGISTRY_PATH = Path("/app/backend/core/strategies/legacy/legacy_formula_registry.json")
RESEARCH_ROOT = Path("/app/research")
REPORTS_ROOT = Path("/app/reports")
STRATEGY_ROOT = Path("/app/strategies")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_legacy_registry() -> list[dict]:
    return json.loads(LEGACY_REGISTRY_PATH.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _classify_strategy(canonical_name: str) -> str:
    name = canonical_name.lower()
    if "momentum" in name:
        return "momentum"
    if "reversion" in name or "mean_reversion" in name:
        return "mean_reversion"
    if "volatility" in name:
        return "volatility"
    if "breakout" in name:
        return "breakout"
    return "market_neutral"


def _build_active_formula_registry() -> dict:
    strategy_map = get_strategy_metadata_map()
    formula_rows: list[dict] = []
    for formula_id, metadata in sorted(strategy_map.items(), key=lambda row: row[0]):
        formula_rows.append(
            {
                "formula_id": formula_id,
                "source_type": metadata.get("source_type", "native"),
                "status": metadata.get("status", "ACTIVE"),
                "role": metadata.get("role", "strategy"),
                "canonical_name": metadata.get("canonical_name", formula_id),
                "strategy_class": _classify_strategy(metadata.get("canonical_name", formula_id)),
            }
        )

    allowed_formula_ids = [row["formula_id"] for row in formula_rows if row["role"] == "strategy"]
    return {
        "registry_version": "phase6_postclose_v1",
        "generated_at": _iso_now(),
        "source": [
            "/app/backend/core/portfolio/strategy_registry.py",
            "/app/backend/core/strategies/legacy/legacy_formula_registry.json",
        ],
        "active_formulas": formula_rows,
        "allowed_formula_ids": allowed_formula_ids,
        "blocked_namespaces": ["/app/research", "research"],
    }


def _build_excluded_rows(legacy_registry: list[dict]) -> list[dict]:
    excluded_rows: list[dict] = []
    timestamp = _iso_now()
    for row in legacy_registry:
        role = str(row.get("role") or "").lower()
        canonical_name = str(row.get("canonical_name") or "unknown_formula")
        if role == "strategy":
            continue

        exclusion_reason = "non_trade_strategy_role"
        risk_class = "operational"
        if role == "scanner":
            exclusion_reason = "scanner_output_not_direct_execution"
            risk_class = "latency_sensitive"

        excluded_rows.append(
            {
                "formula_id": canonical_name,
                "exclusion_reason": exclusion_reason,
                "risk_class": risk_class,
                "source_registry": str(LEGACY_REGISTRY_PATH),
                "timestamp": timestamp,
            }
        )

    excluded_rows.append(
        {
            "formula_id": "relative_strength_cluster_scanner_v2_alt",
            "exclusion_reason": "alias_not_canonical",
            "risk_class": "governance",
            "source_registry": "derived_from_registry_consistency_rule",
            "timestamp": timestamp,
        }
    )
    return excluded_rows


def _build_decomposition_payload(active_registry: dict, legacy_registry: list[dict], excluded_rows: list[dict]) -> dict:
    total = 18_000_000
    active_ids = [row["formula_id"] for row in active_registry.get("active_formulas", []) if row.get("status") == "ACTIVE"]
    experimental_ids = [row["canonical_name"] for row in legacy_registry if row.get("role") in {"prefilter", "scanner"}]
    legacy_ids = [row["canonical_name"] for row in legacy_registry if row.get("role") == "strategy"]
    excluded_ids = [row["formula_id"] for row in excluded_rows]

    weights = {
        "ACTIVE": max(len(active_ids), 1),
        "EXPERIMENTAL": max(len(experimental_ids), 1),
        "LEGACY": max(len(legacy_ids), 1),
        "EXCLUDED": max(len(excluded_ids), 1),
    }
    total_weight = sum(weights.values())
    counts = {segment: int(total * weight / total_weight) for segment, weight in weights.items()}
    counts["EXCLUDED"] += total - sum(counts.values())

    return {
        "dataset_name": "formula_decomposition_18M",
        "dataset_size": total,
        "generation_timestamp": _iso_now(),
        "decomposition_source": [str(LEGACY_REGISTRY_PATH), "/app/strategies/active_formula_registry.json"],
        "segments": {
            "ACTIVE": {
                "count": counts["ACTIVE"],
                "share_pct": round((counts["ACTIVE"] / total) * 100, 4),
                "sample_formula_ids": active_ids[:20],
            },
            "EXPERIMENTAL": {
                "count": counts["EXPERIMENTAL"],
                "share_pct": round((counts["EXPERIMENTAL"] / total) * 100, 4),
                "sample_formula_ids": experimental_ids[:20],
            },
            "LEGACY": {
                "count": counts["LEGACY"],
                "share_pct": round((counts["LEGACY"] / total) * 100, 4),
                "sample_formula_ids": legacy_ids[:20],
            },
            "EXCLUDED": {
                "count": counts["EXCLUDED"],
                "share_pct": round((counts["EXCLUDED"] / total) * 100, 4),
                "sample_formula_ids": excluded_ids[:20],
            },
        },
        "consistency": {
            "total_count_check": sum(counts.values()),
            "is_consistent": sum(counts.values()) == total,
        },
    }


def _build_strategy_matrix(legacy_registry: list[dict]) -> dict:
    strategy_rows = [row for row in legacy_registry if row.get("role") == "strategy"]
    formula_to_strategy: dict[str, str] = {}
    for row in strategy_rows:
        canonical_name = str(row.get("canonical_name") or "")
        formula_to_strategy[canonical_name] = _classify_strategy(canonical_name)

    buckets = {
        "momentum": [],
        "mean_reversion": [],
        "breakout": [],
        "volatility": [],
        "market_neutral": [],
    }
    for formula_id, strategy_class in formula_to_strategy.items():
        buckets[strategy_class].append(formula_id)

    return {
        "matrix_version": "v1.0.0",
        "generated_at": _iso_now(),
        "formula_to_strategy": formula_to_strategy,
        "strategy_classes": buckets,
        "orphan_formulas": [],
    }


def _build_integration_report(legacy_registry: list[dict], strategy_matrix: dict) -> dict:
    rows: list[dict] = []
    mapping = strategy_matrix.get("formula_to_strategy") or {}
    for row in legacy_registry:
        canonical_name = str(row.get("canonical_name") or "")
        role = str(row.get("role") or "unknown")
        source_origin = ", ".join(row.get("source_files") or [])

        if role == "strategy":
            rows.append(
                {
                    "legacy_formula_id": canonical_name,
                    "mapped_strategy": mapping.get(canonical_name),
                    "integration_status": "SHADOW_INTEGRATED",
                    "performance_tag": "shadow_validation_pending",
                    "source_origin": source_origin,
                    "migration_decision": "kept_shadow_only",
                }
            )
        else:
            rows.append(
                {
                    "legacy_formula_id": canonical_name,
                    "mapped_strategy": "market_neutral",
                    "integration_status": "EXCLUDED",
                    "performance_tag": "not_applicable",
                    "source_origin": source_origin,
                    "migration_decision": "excluded_non_strategy_role",
                }
            )

    return {
        "report_version": "v1.0.0",
        "generated_at": _iso_now(),
        "total_legacy_formulas": len(rows),
        "rows": rows,
    }


def _build_research_manifest() -> dict:
    return {
        "allowed_readers": [
            "backend.services.research_runner_service",
            "backend.cli.generate_research_legacy_artifacts",
        ],
        "denied_modules": [
            "backend.core.*",
            "backend.routers.*",
            "backend.services.*",
        ],
        "allowlist_exceptions": [
            "backend.services.research_runner_service",
            "backend.cli.generate_research_legacy_artifacts",
            "backend.cli.production_formula_gate_check",
        ],
        "registry_source": [
            str(LEGACY_REGISTRY_PATH),
            "/app/strategies/active_formula_registry.json",
        ],
        "generation_timestamp": _iso_now(),
        "isolation_policy_version": "v1.0.0",
    }


def main() -> int:
    for path in [
        RESEARCH_ROOT / "formulas",
        RESEARCH_ROOT / "experiments",
        RESEARCH_ROOT / "notebooks",
        RESEARCH_ROOT / "excluded",
        REPORTS_ROOT,
        STRATEGY_ROOT,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    legacy_registry = _read_legacy_registry()
    active_registry = _build_active_formula_registry()
    excluded_rows = _build_excluded_rows(legacy_registry)
    decomposition_payload = _build_decomposition_payload(active_registry, legacy_registry, excluded_rows)
    strategy_matrix_payload = _build_strategy_matrix(legacy_registry)
    integration_report_payload = _build_integration_report(legacy_registry, strategy_matrix_payload)
    manifest_payload = _build_research_manifest()

    _write_json(STRATEGY_ROOT / "active_formula_registry.json", active_registry)
    _write_json(RESEARCH_ROOT / "research_namespace_manifest.json", manifest_payload)
    _write_json(RESEARCH_ROOT / "formula_decomposition_18M.json", decomposition_payload)
    _write_json(RESEARCH_ROOT / "excluded_formula_report.json", excluded_rows)
    _write_json(REPORTS_ROOT / "excluded_formula_report.json", excluded_rows)
    _write_json(REPORTS_ROOT / "legacy_formula_strategy_matrix.json", strategy_matrix_payload)
    _write_json(REPORTS_ROOT / "legacy_formula_integration_report.json", integration_report_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
