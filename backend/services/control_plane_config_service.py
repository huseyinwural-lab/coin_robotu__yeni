import json
from datetime import datetime, timezone

from models import ExternalProviderCredential
from services.secret_provider_service import decrypt_secret_value, encrypt_secret_value, rotate_secret_value


CONFIG_PROVIDER_KEYS = {
    "capability_matrix": "venue_cfg_capability_v2",
    "market_policy": "venue_cfg_market_policy_v2",
    "routing_policy": "venue_cfg_routing_policy_v2",
    "health_snapshot": "venue_cfg_health_snapshot_v2",
}


def _provider_key(config_key: str) -> str:
    return CONFIG_PROVIDER_KEYS.get(config_key, f"venue_cfg_{config_key[:40]}")


def get_control_plane_config(db, *, config_key: str, default: dict | None = None) -> dict:
    provider = _provider_key(config_key)
    row = db.query(ExternalProviderCredential).filter(ExternalProviderCredential.provider == provider).first()
    if row is None or not row.api_key_encrypted:
        return dict(default or {})
    try:
        payload = decrypt_secret_value(row.api_key_encrypted)
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # noqa: BLE001
        return dict(default or {})
    return dict(default or {})


def upsert_control_plane_config(db, *, config_key: str, payload: dict, actor_user_id: str | None = None) -> dict:
    provider = _provider_key(config_key)
    row = db.query(ExternalProviderCredential).filter(ExternalProviderCredential.provider == provider).first()
    serialized = json.dumps(payload or {}, ensure_ascii=False)
    if row is None:
        row = ExternalProviderCredential(provider=provider)
        row.api_key_encrypted = encrypt_secret_value(serialized)
        db.add(row)
    else:
        if row.api_key_encrypted:
            row.api_key_encrypted = rotate_secret_value(row.api_key_encrypted, serialized)
        else:
            row.api_key_encrypted = encrypt_secret_value(serialized)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {
        "provider": provider,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": actor_user_id,
        "payload": payload,
    }
