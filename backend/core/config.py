import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def required_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


class Settings:
    database_url: str = required_env("DATABASE_URL")
    redis_url: str = required_env("REDIS_URL")
    jwt_secret: str = required_env("JWT_SECRET")
    jwt_algorithm: str = required_env("JWT_ALGORITHM")
    jwt_expire_minutes: int = int(required_env("JWT_EXPIRE_MINUTES"))
    cors_origins: list[str] = [
        origin.strip() for origin in required_env("CORS_ORIGINS").split(",") if origin.strip()
    ]
    default_admin_email: str | None = os.environ.get("DEFAULT_ADMIN_EMAIL")
    default_admin_password: str | None = os.environ.get("DEFAULT_ADMIN_PASSWORD")
    scaling_weight_pnl_stability: float = float(os.environ.get("SCALING_WEIGHT_PNL_STABILITY", "0.25"))
    scaling_weight_slippage_impact: float = float(os.environ.get("SCALING_WEIGHT_SLIPPAGE_IMPACT", "0.25"))
    scaling_weight_execution_quality: float = float(os.environ.get("SCALING_WEIGHT_EXECUTION_QUALITY", "0.25"))
    scaling_weight_liquidity_stress: float = float(os.environ.get("SCALING_WEIGHT_LIQUIDITY_STRESS", "0.25"))


settings = Settings()