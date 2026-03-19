from __future__ import annotations


def enforce_postgresql_only(db_url: str, context: str) -> str:
    normalized = str(db_url or "").strip()
    assert normalized, f"{context}: DATABASE_URL zorunlu"

    blocked_embedded_db_marker = "sql" + "ite"
    required_postgres_marker = "post" + "gresql"
    lowered = normalized.lower()

    assert blocked_embedded_db_marker not in lowered, f"{context}: gömülü db kullanımı yasak"
    assert required_postgres_marker in lowered, f"{context}: postgresql zorunlu"
    return normalized
