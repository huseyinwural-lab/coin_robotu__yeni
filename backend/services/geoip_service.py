from __future__ import annotations

import ipaddress
from functools import lru_cache

from geolite2 import geolite2


def _is_public_ip(ip_address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(str(ip_address or "").strip())
        return bool(parsed.is_global)
    except Exception:
        return False


@lru_cache(maxsize=1)
def _get_reader():
    return geolite2.reader()


def resolve_ip_location(ip_address: str) -> dict:
    ip_value = str(ip_address or "").strip()
    if not _is_public_ip(ip_value):
        return {
            "country": None,
            "country_iso": None,
            "city": None,
            "region": None,
            "latitude": None,
            "longitude": None,
            "source": "geoip_local",
            "resolved": False,
        }

    reader = _get_reader()
    payload = reader.get(ip_value) or {}
    country = ((payload.get("country") or {}).get("names") or {}).get("en")
    country_iso = (payload.get("country") or {}).get("iso_code")
    city = ((payload.get("city") or {}).get("names") or {}).get("en")
    subdivisions = payload.get("subdivisions") or []
    region = ((subdivisions[0] or {}).get("names") or {}).get("en") if subdivisions else None
    location = payload.get("location") or {}

    return {
        "country": country,
        "country_iso": country_iso,
        "city": city,
        "region": region,
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "source": "geoip_local",
        "resolved": bool(country or city),
    }
