from __future__ import annotations

import os


class ExportStorageProvider:
    def save_artifact(self, *, export_id: str, content_bytes: bytes, output_format: str) -> tuple[str, str | None]:
        raise NotImplementedError


class LocalExportStorageProvider(ExportStorageProvider):
    def __init__(self, base_dir: str = "/tmp/commercial_exports"):
        self.base_dir = base_dir

    def save_artifact(self, *, export_id: str, content_bytes: bytes, output_format: str) -> tuple[str, str | None]:
        os.makedirs(self.base_dir, exist_ok=True)
        extension = "xlsx" if str(output_format).lower() == "xlsx" else "csv"
        artifact_ref = f"{self.base_dir}/{export_id}.{extension}"
        with open(artifact_ref, "wb") as handle:
            handle.write(content_bytes)
        signed_url = f"local://download/{export_id}"
        return artifact_ref, signed_url


def get_export_storage_provider() -> ExportStorageProvider:
    provider_name = (os.environ.get("COMMERCIAL_EXPORT_STORAGE_PROVIDER") or "local").strip().lower()
    if provider_name == "local":
        return LocalExportStorageProvider()
    # Contract placeholder for future object storage providers
    return LocalExportStorageProvider()
