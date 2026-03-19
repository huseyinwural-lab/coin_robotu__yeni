from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError


S3_REQUIRED_ENV_KEYS = (
    "BACKUP_S3_BUCKET",
    "BACKUP_AWS_ACCESS_KEY_ID",
    "BACKUP_AWS_SECRET_ACCESS_KEY",
    "BACKUP_AWS_REGION",
)


@dataclass
class S3BackupUploadResult:
    status: str
    message: str
    s3_uri: str | None = None


def _read_s3_config() -> tuple[dict[str, str] | None, str | None]:
    config = {key: (os.getenv(key) or "").strip() for key in S3_REQUIRED_ENV_KEYS}
    present = [key for key, value in config.items() if value]

    if not present:
        return None, None

    missing = [key for key, value in config.items() if not value]
    if missing:
        return None, f"S3 misconfiguration: missing required env vars: {', '.join(missing)}"

    return config, None


def _build_s3_object_key(file_path: Path) -> str:
    prefix = (os.getenv("BACKUP_S3_PREFIX") or "").strip().strip("/")
    date_path = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    key_parts = [part for part in (prefix, date_path, file_path.name) if part]
    return "/".join(key_parts)


def upload_backup_to_s3(backup_file_path: str) -> S3BackupUploadResult:
    file_path = Path(backup_file_path)
    if not file_path.exists():
        return S3BackupUploadResult(status="failed", message=f"Backup file not found: {file_path}")

    if file_path.stat().st_size == 0:
        return S3BackupUploadResult(status="failed", message=f"Backup file is empty: {file_path}")

    s3_config, config_error = _read_s3_config()
    if config_error:
        return S3BackupUploadResult(status="failed", message=config_error)

    if s3_config is None:
        return S3BackupUploadResult(status="skipped", message="S3 env vars are not set; upload skipped")

    bucket = s3_config["BACKUP_S3_BUCKET"]
    object_key = _build_s3_object_key(file_path)

    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=s3_config["BACKUP_AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=s3_config["BACKUP_AWS_SECRET_ACCESS_KEY"],
            region_name=s3_config["BACKUP_AWS_REGION"],
        )
        s3_client.upload_file(
            str(file_path),
            bucket,
            object_key,
            ExtraArgs={"ServerSideEncryption": "AES256"},
        )
    except (ClientError, BotoCoreError) as exc:
        return S3BackupUploadResult(status="failed", message=f"S3 upload failed: {exc}")
    except Exception as exc:  # pragma: no cover - defensive fallback
        return S3BackupUploadResult(status="failed", message=f"Unexpected S3 upload failure: {exc}")

    s3_uri = f"s3://{bucket}/{object_key}"
    return S3BackupUploadResult(status="uploaded", message=f"S3 upload completed: {s3_uri}", s3_uri=s3_uri)
