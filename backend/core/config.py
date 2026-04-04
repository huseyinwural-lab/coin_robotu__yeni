import os
from pathlib import Path

from dotenv import load_dotenv

from core.db_determinism import enforce_postgresql_only

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def required_env(key: str) -> str:
    value = os.environ.get(key)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {key}")
    normalized = str(value).strip()
    if not normalized:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return normalized


def optional_env(key: str) -> str | None:
    value = os.environ.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def forbidden_env(key: str) -> None:
    value = os.environ.get(key)
    if value is None:
        return
    normalized = str(value).strip()
    if normalized:
        raise RuntimeError(f"Deprecated environment variable is forbidden: {key}")


def require_secure_jwt_secret() -> str:
    secret = required_env("JWT_SECRET")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    weak_values = {"change-this", "changeme", "secret", "jwt-secret", "ci-jwt-secret", "ci-test-secret"}
    if secret.lower() in weak_values:
        raise RuntimeError("JWT_SECRET is too weak")
    return secret


class Settings:
    database_url: str = enforce_postgresql_only(required_env("DATABASE_URL"), "settings")
    redis_url: str = required_env("REDIS_URL")
    jwt_secret: str = require_secure_jwt_secret()
    jwt_algorithm: str = required_env("JWT_ALGORITHM")
    jwt_expire_minutes: int = int(required_env("JWT_EXPIRE_MINUTES"))
    exchange_credentials_encryption_key: str = required_env("EXCHANGE_CREDENTIALS_ENCRYPTION_KEY")
    cors_origins: list[str] = [
        origin.strip() for origin in required_env("CORS_ORIGINS").split(",") if origin.strip()
    ]
    bootstrap_admin_email: str | None = optional_env("ADMIN_BOOTSTRAP_EMAIL")
    bootstrap_admin_password: str | None = optional_env("ADMIN_BOOTSTRAP_PASSWORD")
    review_user_bootstrap_email: str | None = optional_env("REVIEW_USER_BOOTSTRAP_EMAIL")
    review_user_bootstrap_password: str | None = optional_env("REVIEW_USER_BOOTSTRAP_PASSWORD")
    scaling_weight_pnl_stability: float = float(os.environ.get("SCALING_WEIGHT_PNL_STABILITY", "0.25"))
    scaling_weight_slippage_impact: float = float(os.environ.get("SCALING_WEIGHT_SLIPPAGE_IMPACT", "0.25"))
    scaling_weight_execution_quality: float = float(os.environ.get("SCALING_WEIGHT_EXECUTION_QUALITY", "0.25"))
    scaling_weight_liquidity_stress: float = float(os.environ.get("SCALING_WEIGHT_LIQUIDITY_STRESS", "0.25"))


forbidden_env("DEFAULT_ADMIN_" + "EMAIL")
forbidden_env("DEFAULT_ADMIN_" + "PASSWORD")


settings = Settings()