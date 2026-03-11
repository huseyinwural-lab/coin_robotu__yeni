import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


EXPORT_DIR = Path("/app/backend/exports")
MANIFEST_PATH = EXPORT_DIR / "artifact_manifest.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"schema_version": "1.0", "artifacts": []}
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"schema_version": "1.0", "artifacts": []}
    payload.setdefault("schema_version", "1.0")
    payload.setdefault("artifacts", [])
    return payload


def _write_manifest(payload: dict) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    manifest["artifacts"].append(entry)
    _write_manifest(manifest)
    return {"artifact_id": artifact_id, "path": str(file_path), "entry": entry}


def list_manifest_artifacts() -> list[dict]:
    manifest = _read_manifest()
    artifacts = manifest.get("artifacts", [])
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


def verify_artifact(artifact_id: str) -> dict:
    entry = get_manifest_artifact(artifact_id)
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

    return {
        "artifact_id": artifact_id,
        "filename": entry["filename"],
        "sha256_expected": sha256_expected,
        "sha256_actual": sha256_actual,
        "verified": verified,
    }
