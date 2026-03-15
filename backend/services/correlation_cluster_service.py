from models import RiskExposureGroup


FALLBACK_CLUSTERS = {
    "majors": {"BTCUSDT", "ETHUSDT", "SOLUSDT"},
    "ai": {"FETUSDT", "AGIXUSDT", "RNDRUSDT"},
    "meme": {"DOGEUSDT", "SHIBUSDT", "PEPEUSDT"},
    "l2": {"OPUSDT", "ARBUSDT", "MATICUSDT"},
}


def resolve_symbol_cluster(db, symbol: str) -> str:
    normalized = str(symbol or "").upper().strip()
    if not normalized:
        return "unclustered"

    groups = db.query(RiskExposureGroup).all()
    for group in groups:
        symbols = {str(item or "").upper().strip() for item in (group.symbols or []) if str(item or "").strip()}
        if symbols and normalized in symbols:
            return str(group.name or "unclustered")

    for cluster_id, symbols in FALLBACK_CLUSTERS.items():
        if normalized in symbols:
            return cluster_id
    return "unclustered"


def cluster_symbol_map(db) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    groups = db.query(RiskExposureGroup).all()
    for group in groups:
        cluster_id = str(group.name or "unclustered")
        mapping.setdefault(cluster_id, set())
        for symbol in group.symbols or []:
            normalized = str(symbol or "").upper().strip()
            if normalized:
                mapping[cluster_id].add(normalized)

    for cluster_id, symbols in FALLBACK_CLUSTERS.items():
        mapping.setdefault(cluster_id, set()).update(symbols)
    return mapping
