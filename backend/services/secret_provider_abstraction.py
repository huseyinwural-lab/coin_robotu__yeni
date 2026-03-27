from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.users.user_exchange_connector import decrypt_exchange_secret, encrypt_exchange_secret


@dataclass
class SecretEnvelope:
    ciphertext: str
    provider: str
    version: str


class SecretProvider(ABC):
    provider_name: str = "unknown"
    version: str = "v1"

    @abstractmethod
    def encrypt(self, plaintext: str) -> SecretEnvelope:
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, envelope: SecretEnvelope) -> str:
        raise NotImplementedError

    @abstractmethod
    def rotate(self, envelope: SecretEnvelope) -> SecretEnvelope:
        raise NotImplementedError


class LocalEncryptionProvider(SecretProvider):
    provider_name = "local_encryption"
    version = "v1"

    def encrypt(self, plaintext: str) -> SecretEnvelope:
        return SecretEnvelope(
            ciphertext=encrypt_exchange_secret(str(plaintext or "")),
            provider=self.provider_name,
            version=self.version,
        )

    def decrypt(self, envelope: SecretEnvelope) -> str:
        return decrypt_exchange_secret(str(envelope.ciphertext or ""))

    def rotate(self, envelope: SecretEnvelope) -> SecretEnvelope:
        plain = self.decrypt(envelope)
        return self.encrypt(plain)


class AwsKmsProvider(SecretProvider):
    provider_name = "aws_kms"
    version = "v1"

    def encrypt(self, plaintext: str) -> SecretEnvelope:
        raise NotImplementedError("aws_kms_provider_not_implemented_in_this_phase")

    def decrypt(self, envelope: SecretEnvelope) -> str:
        raise NotImplementedError("aws_kms_provider_not_implemented_in_this_phase")

    def rotate(self, envelope: SecretEnvelope) -> SecretEnvelope:
        raise NotImplementedError("aws_kms_provider_not_implemented_in_this_phase")


class VaultProvider(SecretProvider):
    provider_name = "hashicorp_vault"
    version = "v1"

    def encrypt(self, plaintext: str) -> SecretEnvelope:
        raise NotImplementedError("vault_provider_not_implemented_in_this_phase")

    def decrypt(self, envelope: SecretEnvelope) -> str:
        raise NotImplementedError("vault_provider_not_implemented_in_this_phase")

    def rotate(self, envelope: SecretEnvelope) -> SecretEnvelope:
        raise NotImplementedError("vault_provider_not_implemented_in_this_phase")


def default_secret_provider() -> SecretProvider:
    return LocalEncryptionProvider()
