import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


EXPORT_DIR = Path("/app/backend/exports")
MANIFEST_PATH = EXPORT_DIR / "artifact_manifest.json"
CHAIN_SCHEMA_VERSION = "1.1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"schema_version": CHAIN_SCHEMA_VERSION, "artifacts": []}
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"schema_version": CHAIN_SCHEMA_VERSION, "artifacts": []}
    payload.setdefault("schema_version", CHAIN_SCHEMA_VERSION)
    payload.setdefault("artifacts", [])
    if not isinstance(payload.get("artifacts"), list):
        payload["artifacts"] = []
    return payload


def _write_manifest(payload: dict) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload.setdefault("schema_version", CHAIN_SCHEMA_VERSION)
    payload.setdefault("artifacts", [])
    MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _compute_chain_hash(prev_chain_hash: str, entry: dict) -> str:
    raw = f"{prev_chain_hash}{entry.get('sha256','')}{entry.get('artifact_id','')}{entry.get('created_at','')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_chain(manifest: dict) -> dict:
    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        manifest["schema_version"] = CHAIN_SCHEMA_VERSION
        return manifest

    missing_chain = any(
        item.get("chain_hash") is None
        or item.get("prev_chain_hash") is None
        or item.get("chain_position") is None
        for item in artifacts
    )

    if missing_chain:
        prev_hash = "GENESIS"
        for idx, item in enumerate(artifacts):
            item["chain_position"] = idx
            item["prev_chain_hash"] = prev_hash
            item["chain_hash"] = _compute_chain_hash(prev_hash, item)
            prev_hash = item["chain_hash"]
    manifest["schema_version"] = CHAIN_SCHEMA_VERSION
    return manifest


def compute_artifact_checksum(payload: dict) -> str:
    normalized = copy.deepcopy(payload)
    metadata = normalized.get("metadata")
    if isinstance(metadata, dict):
        metadata["sha256"] = ""
    if "sha256" in normalized:
        normalized["sha256"] = ""
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_signed_artifact(payload: dict, *, artifact_type: str, filename_prefix: str) -> dict:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    created_at = _utc_now_iso()
    artifact_id = str(uuid.uuid4())

    data = copy.deepcopy(payload)
    data.setdefault("schema_version", "1.0")
    data.setdefault("metadata", {})
    data["metadata"]["schema_version"] = "1.0"
    data["metadata"]["artifact_type"] = artifact_type
    data["metadata"]["created_at"] = created_at
    data["metadata"]["artifact_id"] = artifact_id
    data["metadata"]["sha256"] = ""
    data["artifact_type"] = artifact_type
    data["created_at"] = data.get("created_at") or created_at
    data["sha256"] = ""

    checksum = compute_artifact_checksum(data)
    data["metadata"]["sha256"] = checksum
    data["sha256"] = checksum

    filename = f"{filename_prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{artifact_id[:8]}.json"
    file_path = EXPORT_DIR / filename
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    entry = {
        "artifact_id": artifact_id,
        "filename": filename,
        "artifact_type": artifact_type,
        "sha256": checksum,
        "size": file_path.stat().st_size,
        "created_at": created_at,
        "proof_id": data.get("proof_id") or data.get("run_id") or data.get("execution_id") or artifact_id,
        "evidence_type": data.get("evidence_type") or data.get("metadata", {}).get("artifact_type", "unknown"),
        "status": data.get("lifecycle_proof_status") or data.get("status") or "generated",
    }

    manifest = _read_manifest()
    manifest = _ensure_chain(manifest)
    artifacts = manifest.get("artifacts", [])
    prev_chain_hash = artifacts[-1]["chain_hash"] if artifacts else "GENESIS"
    entry["chain_position"] = len(artifacts)
    entry["prev_chain_hash"] = prev_chain_hash
    entry["chain_hash"] = _compute_chain_hash(prev_chain_hash, entry)

    artifacts.append(entry)
    manifest["artifacts"] = artifacts
    _write_manifest(manifest)
    return {"artifact_id": artifact_id, "path": str(file_path), "entry": entry}


def list_manifest_artifacts() -> list[dict]:
    manifest = _ensure_chain(_read_manifest())
    artifacts = manifest.get("artifacts", [])
    _write_manifest(manifest)
    return sorted(artifacts, key=lambda item: item.get("created_at", ""), reverse=True)


def get_manifest_artifact(artifact_id: str) -> dict | None:
    for item in list_manifest_artifacts():
        if item.get("artifact_id") == artifact_id:
            return item
    return None


def resolve_artifact_path(artifact_id: str) -> Path | None:
    entry = get_manifest_artifact(artifact_id)
    if not entry:
        return None
    return EXPORT_DIR / entry["filename"]


def verify_manifest_chain() -> dict:
    manifest = _ensure_chain(_read_manifest())
    _write_manifest(manifest)
    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        return {"total": 0, "chain_broken": False, "broken_index": None, "broken_artifact_id": None}

    prev_hash = "GENESIS"
    broken_index = None
    broken_artifact_id = None

    for idx, entry in enumerate(artifacts):
        expected_chain = _compute_chain_hash(prev_hash, entry)
        position_ok = entry.get("chain_position") == idx
        prev_ok = entry.get("prev_chain_hash") == prev_hash
        chain_ok = entry.get("chain_hash") == expected_chain
        if not (position_ok and prev_ok and chain_ok):
            broken_index = idx
            broken_artifact_id = entry.get("artifact_id")
            break
        prev_hash = entry.get("chain_hash")

    return {
        "total": len(artifacts),
        "chain_broken": broken_index is not None,
        "broken_index": broken_index,
        "broken_artifact_id": broken_artifact_id,
    }


def verify_artifact(artifact_id: str) -> dict:
    manifest = _ensure_chain(_read_manifest())
    _write_manifest(manifest)
    artifacts = manifest.get("artifacts", [])
    entry = None
    entry_index = None
    for idx, item in enumerate(artifacts):
        if item.get("artifact_id") == artifact_id:
            entry = item
            entry_index = idx
            break

    if entry is None:
        raise ValueError("artifact_not_found")

    file_path = EXPORT_DIR / entry["filename"]
    if not file_path.exists():
        raise ValueError("artifact_file_missing")

    payload = json.loads(file_path.read_text(encoding="utf-8"))
    sha256_actual = compute_artifact_checksum(payload)
    sha256_expected = entry["sha256"]
    metadata_sha = payload.get("metadata", {}).get("sha256")
    payload_sha = payload.get("sha256")
    verified = sha256_actual == sha256_expected == metadata_sha == payload_sha

    prev_hash = "GENESIS"
    expected_chain = None
    chain_valid = False
    chain_position = entry.get("chain_position")
    prev_chain_hash = entry.get("prev_chain_hash")
    chain_hash = entry.get("chain_hash")

    for idx, item in enumerate(artifacts):
        expected_chain = _compute_chain_hash(prev_hash, item)
        if idx == entry_index:
            chain_valid = (
                item.get("chain_position") == idx
                and item.get("prev_chain_hash") == prev_hash
                and item.get("chain_hash") == expected_chain
            )
            break
        prev_hash = item.get("chain_hash") or expected_chain

    chain_status = verify_manifest_chain()

    return {
        "artifact_id": artifact_id,
        "filename": entry["filename"],
        "sha256_expected": sha256_expected,
        "sha256_actual": sha256_actual,
        "verified": verified,
        "chain_position": chain_position,
        "prev_chain_hash": prev_chain_hash,
        "chain_hash": chain_hash,
        "chain_valid": chain_valid,
        "chain_broken": chain_status.get("chain_broken"),
        "chain_broken_index": chain_status.get("broken_index"),
        "chain_broken_artifact_id": chain_status.get("broken_artifact_id"),
    }


def verify_all_artifacts(
    *,
    artifact_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status_filter: str = "all",
) -> dict:
    manifest = _ensure_chain(_read_manifest())
    _write_manifest(manifest)
    artifacts = manifest.get("artifacts", [])
    chain_status = verify_manifest_chain()
    broken_index = chain_status.get("broken_index")

    results = []
    for idx, entry in enumerate(artifacts):
        if artifact_type and entry.get("artifact_type") != artifact_type:
            continue
        created_at = entry.get("created_at")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                created_dt = None
        else:
            created_dt = None

        if date_from and created_dt and created_dt < date_from:
            continue
        if date_to and created_dt and created_dt > date_to:
            continue

        file_path = EXPORT_DIR / entry.get("filename", "")
        status = "verified"
        reason_codes: list[str] = []

        if not file_path.exists():
            status = "missing"
            reason_codes.append("missing_artifact")
        else:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            sha256_actual = compute_artifact_checksum(payload)
            sha256_expected = entry.get("sha256")
            metadata_sha = payload.get("metadata", {}).get("sha256")
            payload_sha = payload.get("sha256")
            if not (sha256_actual == sha256_expected == metadata_sha == payload_sha):
                status = "mismatch"
                reason_codes.append("sha256_mismatch")

        if chain_status.get("chain_broken") and broken_index is not None and idx >= broken_index:
            status = "chain_broken"
            reason_codes.append("chain_integrity_failure")

        results.append(
            {
                "artifact_id": entry.get("artifact_id"),
                "filename": entry.get("filename"),
                "artifact_type": entry.get("artifact_type"),
                "status": status,
                "reason_codes": reason_codes,
            }
        )

    if status_filter and status_filter != "all":
        results = [item for item in results if item["status"] == status_filter]

    summary = {
        "total": len(results),
        "verified": sum(1 for item in results if item["status"] == "verified"),
        "mismatch": sum(1 for item in results if item["status"] == "mismatch"),
        "missing": sum(1 for item in results if item["status"] == "missing"),
        "chain_broken": sum(1 for item in results if item["status"] == "chain_broken"),
        "chain_broken_index": chain_status.get("broken_index"),
        "chain_broken_artifact_id": chain_status.get("broken_artifact_id"),
        "items": results,
    }
    return summary
