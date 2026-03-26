from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from db import SessionLocal
from models import CommercialExportAudit, CommercialExportManifest, User
from server import fastapi_app
from services.admin_commercial_service import cleanup_expired_export_artifacts, finalize_export_delivery
from services.commercial_export_storage_service import (
    get_export_storage_provider,
    reset_export_storage_provider_cache,
)


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "canary.admin@platform.local", "password": "CanaryAdmin123!", "panel": "admin"},
    )
    assert response.status_code == 200
    payload = response.json()
    token = payload.get("access_token") or payload.get("token")
    assert token
    return token


def test_supabase_provider_upload_and_signed_url_pass_with_valid_config(monkeypatch):
    class FakeBucket:
        def upload(self, path, file, file_options):
            assert path.endswith(".csv")
            assert file
            assert file_options.get("upsert") == "true"
            return {"path": path}

        def create_signed_url(self, path, expires_in):
            assert expires_in == 900
            return {"signedURL": f"/storage/v1/object/sign/commercial-exports/{path}?token=fake"}

        def remove(self, paths):
            return {"deleted": paths}

    class FakeStorage:
        def from_(self, _bucket):
            return FakeBucket()

    class FakeClient:
        storage = FakeStorage()

    monkeypatch.setenv("COMMERCIAL_EXPORT_STORAGE_PROVIDER", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://wpaejjyirhblphihxnli.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "commercial-exports")
    monkeypatch.setenv("COMMERCIAL_EXPORT_SIGNED_URL_TTL_SECONDS", "900")

    monkeypatch.setattr("services.commercial_export_storage_service.create_client", lambda *_args, **_kwargs: FakeClient())
    reset_export_storage_provider_cache()

    provider = get_export_storage_provider()
    result = provider.save_artifact(
        export_id="exp-test-1",
        content_bytes=b"a,b\n1,2\n",
        output_format="csv",
        retention_until=datetime.now(timezone.utc) + timedelta(days=30),
        signed_url_ttl_seconds=900,
    )

    assert result["artifact_ref"].startswith("supabase://commercial-exports/")
    assert result["signed_download_url"].startswith("https://wpaejjyirhblphihxnli.supabase.co/storage/v1/object/sign/")


def test_supabase_provider_missing_bucket_config_fails_deterministically(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_EXPORT_STORAGE_PROVIDER", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://wpaejjyirhblphihxnli.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.delenv("SUPABASE_STORAGE_BUCKET", raising=False)
    reset_export_storage_provider_cache()

    with pytest.raises(ValueError):
        get_export_storage_provider()


def test_expired_retention_cleanup_passes_for_local_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("COMMERCIAL_EXPORT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("COMMERCIAL_EXPORT_RETENTION_DAYS", "30")
    reset_export_storage_provider_cache()

    artifact_path = tmp_path / "cleanup-test.csv"
    artifact_path.write_bytes(b"x,y\n1,2\n")

    db = SessionLocal()
    try:
        actor = db.query(User).filter(User.email == "canary.admin@platform.local").first()
        assert actor is not None
        manifest = CommercialExportManifest(
            export_type="pnl",
            schema_version="v1",
            requested_by=actor.id,
            requested_at=datetime.now(timezone.utc) - timedelta(days=31),
            output_format="csv",
            checksum="",
            status="delivered",
            delivery_status="success",
            artifact_ref=str(artifact_path),
            signed_download_url="/api/admin/commercial/exports/local/sample",
            delivered_at=datetime.now(timezone.utc) - timedelta(days=31),
            retention_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            retention_state="active",
            downloadable_state="ready",
        )
        db.add(manifest)
        db.commit()
        db.refresh(manifest)

        stats = cleanup_expired_export_artifacts(db, limit=10)
        assert stats["deleted"] >= 1

        row = db.query(CommercialExportManifest).filter(CommercialExportManifest.id == manifest.id).first()
        assert row.retention_state == "deleted"
        assert row.downloadable_state == "expired"
        assert row.signed_download_url is None
        assert not artifact_path.exists()
    finally:
        db.close()


def test_manifest_audit_artifact_linkage_preserved(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_EXPORT_STORAGE_PROVIDER", "local")
    reset_export_storage_provider_cache()

    client = TestClient(fastapi_app)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    manifest_resp = client.post(
        "/api/admin/commercial/exports/request",
        headers=headers,
        json={
            "export_type": "pnl",
            "schema_version": "v1",
            "filters_snapshot": {},
            "column_mapping": {},
            "output_format": "csv",
            "row_count": 0,
            "reason_note": "linkage-test",
        },
    )
    assert manifest_resp.status_code == 200
    export_id = manifest_resp.json()["export_id"]

    db = SessionLocal()
    try:
        delivery = finalize_export_delivery(
            db,
            export_id=export_id,
            content_bytes=b"a,b\n1,2\n",
            output_format="csv",
        )
        assert delivery["delivery_status"] == "success"

        manifest = db.query(CommercialExportManifest).filter(CommercialExportManifest.id == export_id).first()
        audit = (
            db.query(CommercialExportAudit)
            .filter(CommercialExportAudit.export_id == export_id)
            .order_by(CommercialExportAudit.created_at.desc())
            .first()
        )
        assert manifest is not None
        assert audit is not None
        assert manifest.artifact_ref
        assert manifest.file_hash
        assert audit.artifact_ref == manifest.artifact_ref
        assert audit.file_hash == manifest.file_hash
        assert bool(manifest.signed_download_url)
    finally:
        db.close()


def test_local_provider_fallback_controlled_without_local_download_placeholder(monkeypatch):
    monkeypatch.setenv("COMMERCIAL_EXPORT_STORAGE_PROVIDER", "local")
    reset_export_storage_provider_cache()
    provider = get_export_storage_provider()

    result = provider.save_artifact(
        export_id="local-fallback-test",
        content_bytes=b"c1,c2\n3,4\n",
        output_format="csv",
        retention_until=datetime.now(timezone.utc) + timedelta(days=30),
        signed_url_ttl_seconds=900,
    )
    assert result["artifact_ref"].endswith("local-fallback-test.csv")
    assert str(result["signed_download_url"]).startswith("/api/admin/commercial/exports/local/")
    assert "local://download/" not in str(result["signed_download_url"])
