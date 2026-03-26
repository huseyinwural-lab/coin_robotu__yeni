import os

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret


SUPPORTED_SECRET_PROVIDERS = {"local", "vault", "kms"}


def secret_provider_name() -> str:
    provider = str(os.environ.get("SECRET_PROVIDER") or "local").strip().lower()
    if provider not in SUPPORTED_SECRET_PROVIDERS:
        return "local"
    return provider


def encrypt_secret_value(value: str) -> str:
    plain = str(value or "")
    provider = secret_provider_name()
    encrypted = encrypt_exchange_secret(plain)
    return f"{provider}::{encrypted}"


def decrypt_secret_value(value: str) -> str:
    raw = str(value or "")
    if "::" in raw:
        _, payload = raw.split("::", 1)
        return decrypt_exchange_secret(payload)
    return decrypt_exchange_secret(raw)
