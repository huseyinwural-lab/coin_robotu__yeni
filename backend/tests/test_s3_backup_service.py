from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import backup_service


def _set_full_s3_env(monkeypatch) -> None:
    monkeypatch.setenv("BACKUP_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("BACKUP_AWS_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("BACKUP_AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("BACKUP_AWS_REGION", "eu-central-1")


def test_s3_upload_skips_when_env_missing(monkeypatch, tmp_path: Path):
    backup_file = tmp_path / "backup.sql"
    backup_file.write_text("SELECT 1;", encoding="utf-8")

    for key in backup_service.S3_REQUIRED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    result = backup_service.upload_backup_to_s3(str(backup_file))

    assert result.status == "skipped"
    assert "upload skipped" in result.message


def test_s3_upload_fails_on_partial_env(monkeypatch, tmp_path: Path):
    backup_file = tmp_path / "backup.sql"
    backup_file.write_text("SELECT 1;", encoding="utf-8")

    monkeypatch.setenv("BACKUP_S3_BUCKET", "test-bucket")
    monkeypatch.delenv("BACKUP_AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("BACKUP_AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BACKUP_AWS_REGION", raising=False)

    result = backup_service.upload_backup_to_s3(str(backup_file))

    assert result.status == "failed"
    assert "missing required env vars" in result.message


def test_s3_upload_uses_sse_s3(monkeypatch, tmp_path: Path):
    backup_file = tmp_path / "backup.sql"
    backup_file.write_text("SELECT 1;", encoding="utf-8")
    _set_full_s3_env(monkeypatch)
    monkeypatch.setenv("BACKUP_S3_PREFIX", "scheduled")

    captured: dict = {}

    class DummyClient:
        def upload_file(self, filename, bucket, object_key, ExtraArgs=None):
            captured["filename"] = filename
            captured["bucket"] = bucket
            captured["object_key"] = object_key
            captured["extra_args"] = ExtraArgs or {}

    monkeypatch.setattr(backup_service.boto3, "client", lambda *args, **kwargs: DummyClient())

    result = backup_service.upload_backup_to_s3(str(backup_file))

    assert result.status == "uploaded"
    assert result.s3_uri is not None
    assert captured["filename"] == str(backup_file)
    assert captured["bucket"] == "test-bucket"
    assert captured["object_key"].startswith("scheduled/")
    assert captured["object_key"].endswith("/backup.sql")
    assert captured["extra_args"]["ServerSideEncryption"] == "AES256"
