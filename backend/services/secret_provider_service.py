import os
import uuid

import requests

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret


SUPPORTED_SECRET_PROVIDERS = {"local", "vault", "aws_kms", "gcp_kms"}
PRODUCTION_ENVS = {"prod", "production", "live"}
_REVOKED_LOCAL_REFERENCES: set[str] = set()


def _app_env() -> str:
    return str(os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or "dev").strip().lower()


def _provider_from_reference(reference: str) -> str:
    value = str(reference or "")
    if "::" not in value:
        return "local"
    prefix = value.split("::", 1)[0].strip().lower()
    return prefix if prefix in SUPPORTED_SECRET_PROVIDERS else "local"


def secret_provider_name() -> str:
    provider = str(os.environ.get("SECRET_PROVIDER") or "local").strip().lower()
    if provider not in SUPPORTED_SECRET_PROVIDERS:
        return "local"
    return provider


class LocalSecretProvider:
    name = "local"

    def set_secret(self, value: str) -> str:
        encrypted = encrypt_exchange_secret(str(value or ""))
        return f"local::{encrypted}"

    def get_secret(self, reference: str) -> str:
        raw = str(reference or "")
        if raw in _REVOKED_LOCAL_REFERENCES:
            raise RuntimeError("secret_revoked")
        payload = raw.split("::", 1)[1] if "::" in raw else raw
        return decrypt_exchange_secret(payload)

    def rotate_secret(self, reference: str, value: str) -> str:
        new_ref = self.set_secret(value)
        self.revoke_secret(reference)
        return new_ref

    def revoke_secret(self, reference: str) -> None:
        _REVOKED_LOCAL_REFERENCES.add(str(reference or ""))


class VaultSecretProvider:
    name = "vault"

    def __init__(self):
        self.addr = str(os.environ.get("VAULT_ADDR") or "").rstrip("/")
        self.token = str(os.environ.get("VAULT_TOKEN") or "")
        self.mount = str(os.environ.get("VAULT_KV_MOUNT") or "secret").strip("/")
        self.prefix = str(os.environ.get("VAULT_SECRET_PREFIX") or "venue-control-plane").strip("/")
        if not self.addr or not self.token:
            raise RuntimeError("vault_provider_not_configured")

    def _headers(self) -> dict:
        return {"X-Vault-Token": self.token, "Content-Type": "application/json"}

    def _write(self, path: str, value: str) -> None:
        response = requests.post(
            f"{self.addr}/v1/{self.mount}/data/{path}",
            json={"data": {"value": str(value or "")}},
            headers=self._headers(),
            timeout=8,
        )
        if response.status_code >= 300:
            raise RuntimeError("vault_set_failed")

    def _read(self, path: str) -> str:
        response = requests.get(f"{self.addr}/v1/{self.mount}/data/{path}", headers=self._headers(), timeout=8)
        if response.status_code >= 300:
            raise RuntimeError("vault_get_failed")
        body = response.json() if response.content else {}
        return str((((body or {}).get("data") or {}).get("data") or {}).get("value") or "")

    def _delete(self, path: str) -> None:
        requests.delete(f"{self.addr}/v1/{self.mount}/metadata/{path}", headers=self._headers(), timeout=8)

    def set_secret(self, value: str) -> str:
        path = f"{self.prefix}/{uuid.uuid4().hex}"
        self._write(path, value)
        return f"vault::{path}"

    def get_secret(self, reference: str) -> str:
        path = str(reference or "").split("::", 1)[1]
        return self._read(path)

    def rotate_secret(self, reference: str, value: str) -> str:
        new_ref = self.set_secret(value)
        self.revoke_secret(reference)
        return new_ref

    def revoke_secret(self, reference: str) -> None:
        path = str(reference or "").split("::", 1)[1]
        self._delete(path)


class AwsKmsSecretProvider:
    name = "aws_kms"

    def __init__(self):
        try:
            import boto3  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("aws_kms_provider_dependency_missing") from exc
        self._boto3 = boto3
        self.region = str(os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "").strip()
        self.prefix = str(os.environ.get("AWS_SECRET_PREFIX") or "venue-control-plane").strip("/")
        if not self.region:
            raise RuntimeError("aws_kms_provider_not_configured")
        self.client = self._boto3.client("secretsmanager", region_name=self.region)

    def _name(self, suffix: str | None = None) -> str:
        return f"{self.prefix}/{suffix or uuid.uuid4().hex}"

    def set_secret(self, value: str) -> str:
        name = self._name()
        self.client.create_secret(Name=name, SecretString=str(value or ""))
        return f"aws_kms::{name}"

    def get_secret(self, reference: str) -> str:
        name = str(reference or "").split("::", 1)[1]
        response = self.client.get_secret_value(SecretId=name)
        return str(response.get("SecretString") or "")

    def rotate_secret(self, reference: str, value: str) -> str:
        new_ref = self.set_secret(value)
        self.revoke_secret(reference)
        return new_ref

    def revoke_secret(self, reference: str) -> None:
        name = str(reference or "").split("::", 1)[1]
        self.client.delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)


class GcpKmsSecretProvider:
    name = "gcp_kms"

    def __init__(self):
        try:
            from google.cloud import secretmanager  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("gcp_kms_provider_dependency_missing") from exc
        self._secretmanager = secretmanager
        self.project_id = str(os.environ.get("GCP_PROJECT_ID") or "").strip()
        self.prefix = str(os.environ.get("GCP_SECRET_PREFIX") or "venue-control-plane").strip("/")
        if not self.project_id:
            raise RuntimeError("gcp_kms_provider_not_configured")
        self.client = self._secretmanager.SecretManagerServiceClient()

    def _secret_id(self) -> str:
        return f"{self.prefix}-{uuid.uuid4().hex[:20]}"

    def set_secret(self, value: str) -> str:
        parent = f"projects/{self.project_id}"
        secret_id = self._secret_id()
        self.client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        version = self.client.add_secret_version(
            request={"parent": f"{parent}/secrets/{secret_id}", "payload": {"data": str(value or "").encode("utf-8")}}
        )
        return f"gcp_kms::{version.name}"

    def get_secret(self, reference: str) -> str:
        name = str(reference or "").split("::", 1)[1]
        response = self.client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")

    def rotate_secret(self, reference: str, value: str) -> str:
        new_ref = self.set_secret(value)
        self.revoke_secret(reference)
        return new_ref

    def revoke_secret(self, reference: str) -> None:
        name = str(reference or "").split("::", 1)[1]
        self.client.destroy_secret_version(request={"name": name})


def _provider_instance(provider_name: str):
    normalized = str(provider_name or "local").strip().lower()
    if normalized == "vault":
        return VaultSecretProvider()
    if normalized == "aws_kms":
        return AwsKmsSecretProvider()
    if normalized == "gcp_kms":
        return GcpKmsSecretProvider()
    return LocalSecretProvider()


def _enforce_local_provider_policy(provider_name: str) -> None:
    if str(provider_name or "") != "local":
        return
    if _app_env() in PRODUCTION_ENVS:
        raise RuntimeError("local_secret_provider_not_allowed_in_prod")


def encrypt_secret_value(value: str) -> str:
    provider = secret_provider_name()
    _enforce_local_provider_policy(provider)
    return _provider_instance(provider).set_secret(str(value or ""))


def decrypt_secret_value(value: str) -> str:
    reference = str(value or "")
    provider = _provider_from_reference(reference)
    _enforce_local_provider_policy(provider)
    return _provider_instance(provider).get_secret(reference)


def rotate_secret_value(reference: str, value: str) -> str:
    provider = _provider_from_reference(reference)
    _enforce_local_provider_policy(provider)
    return _provider_instance(provider).rotate_secret(reference, str(value or ""))


def revoke_secret_value(reference: str) -> None:
    provider = _provider_from_reference(reference)
    _enforce_local_provider_policy(provider)
    _provider_instance(provider).revoke_secret(reference)
