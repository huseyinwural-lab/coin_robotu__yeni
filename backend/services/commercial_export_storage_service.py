from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path

from supabase import Client, create_client


def _normalize_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExportStorageProvider:
    provider_name = "base"

    def save_artifact(
        self,
        *,
        export_id: str,
        content_bytes: bytes,
        output_format: str,
        retention_until: datetime | None,
        signed_url_ttl_seconds: int,
    ) -> dict:
        raise NotImplementedError

    def delete_artifact(self, *, artifact_ref: str) -> bool:
        raise NotImplementedError


class LocalExportStorageProvider(ExportStorageProvider):
    provider_name = "local"

    def __init__(self, base_dir: str = "/tmp/commercial_exports"):
        self.base_dir = base_dir

    def save_artifact(
        self,
        *,
        export_id: str,
        content_bytes: bytes,
        output_format: str,
        retention_until: datetime | None,
        signed_url_ttl_seconds: int,
    ) -> dict:
        os.makedirs(self.base_dir, exist_ok=True)
        extension = "xlsx" if str(output_format).lower() == "xlsx" else "csv"
        artifact_ref = f"{self.base_dir}/{export_id}.{extension}"
        with open(artifact_ref, "wb") as handle:
            handle.write(content_bytes)
        return {
            "artifact_ref": artifact_ref,
            "signed_download_url": f"/api/admin/commercial/exports/local/{export_id}",
            "retention_until": retention_until.isoformat() if retention_until else None,
            "retention_state": "active",
            "downloadable_state": "ready",
            "storage_provider": self.provider_name,
        }

    def delete_artifact(self, *, artifact_ref: str) -> bool:
        if not artifact_ref:
            return False
        path = Path(artifact_ref)
        if not path.exists():
            return False
        path.unlink()
        return True


@dataclass
class SupabaseStorageSettings:
    supabase_url: str
    service_role_key: str
    bucket_name: str
    object_prefix: str


class SupabaseExportStorageProvider(ExportStorageProvider):
    provider_name = "supabase"

    def __init__(self, settings: SupabaseStorageSettings):
        if not settings.supabase_url:
            raise ValueError("missing_supabase_url")
        if not settings.service_role_key:
            raise ValueError("missing_supabase_service_role_key")
        if not settings.bucket_name:
            raise ValueError("missing_supabase_storage_bucket")
        self.settings = settings
        self.client: Client = create_client(settings.supabase_url, settings.service_role_key)

    def _extension_for_format(self, output_format: str) -> str:
        return "xlsx" if str(output_format).lower() == "xlsx" else "csv"

    def _build_object_path(self, export_id: str, output_format: str) -> str:
        extension = self._extension_for_format(output_format)
        prefix = str(self.settings.object_prefix or "exports").strip().strip("/")
        date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        return f"{prefix}/{date_prefix}/{export_id}.{extension}"

    def _signed_url_absolute(self, signed_url: str | None) -> str | None:
        value = str(signed_url or "").strip()
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return f"{self.settings.supabase_url}{value}"

    def _artifact_ref(self, object_path: str) -> str:
        return f"supabase://{self.settings.bucket_name}/{object_path}"

    def _object_path_from_ref(self, artifact_ref: str) -> str:
        prefix = f"supabase://{self.settings.bucket_name}/"
        if not str(artifact_ref).startswith(prefix):
            raise ValueError("invalid_supabase_artifact_ref")
        return str(artifact_ref)[len(prefix) :]

    def save_artifact(
        self,
        *,
        export_id: str,
        content_bytes: bytes,
        output_format: str,
        retention_until: datetime | None,
        signed_url_ttl_seconds: int,
    ) -> dict:
        object_path = self._build_object_path(export_id, output_format)
        upload_options = {
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if str(output_format).lower() == "xlsx"
            else "text/csv",
            "upsert": "true",
        }
        try:
            self.client.storage.from_(self.settings.bucket_name).upload(
                path=object_path,
                file=content_bytes,
                file_options=upload_options,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"supabase_upload_failed:{str(exc)[:240]}") from exc

        try:
            signed_payload = self.client.storage.from_(self.settings.bucket_name).create_signed_url(
                path=object_path,
                expires_in=max(60, int(signed_url_ttl_seconds or 900)),
            )
            signed_url = self._signed_url_absolute(signed_payload.get("signedURL"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"supabase_signed_url_failed:{str(exc)[:240]}") from exc

        if not signed_url:
            raise RuntimeError("supabase_signed_url_empty")

        return {
            "artifact_ref": self._artifact_ref(object_path),
            "signed_download_url": signed_url,
            "retention_until": retention_until.isoformat() if retention_until else None,
            "retention_state": "active",
            "downloadable_state": "ready",
            "storage_provider": self.provider_name,
            "storage_object_path": object_path,
        }

    def delete_artifact(self, *, artifact_ref: str) -> bool:
        object_path = self._object_path_from_ref(artifact_ref)
        try:
            self.client.storage.from_(self.settings.bucket_name).remove([object_path])
            return True
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"supabase_delete_failed:{str(exc)[:240]}") from exc


def _build_supabase_settings_from_env() -> SupabaseStorageSettings:
    return SupabaseStorageSettings(
        supabase_url=_normalize_url(os.environ.get("SUPABASE_URL")),
        service_role_key=str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip(),
        bucket_name=str(os.environ.get("SUPABASE_STORAGE_BUCKET") or "").strip(),
        object_prefix=str(os.environ.get("COMMERCIAL_EXPORT_STORAGE_PREFIX") or "exports").strip(),
    )


@lru_cache(maxsize=1)
def get_export_storage_provider() -> ExportStorageProvider:
    provider_name = (os.environ.get("COMMERCIAL_EXPORT_STORAGE_PROVIDER") or "local").strip().lower()
    if provider_name == "supabase":
        return SupabaseExportStorageProvider(_build_supabase_settings_from_env())
    if provider_name == "local":
        return LocalExportStorageProvider()
    raise ValueError("unsupported_export_storage_provider")


def reset_export_storage_provider_cache() -> None:
    get_export_storage_provider.cache_clear()
