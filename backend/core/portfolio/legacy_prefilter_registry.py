from core.strategies.prefilters import (
    CryptoUniversePrefilterV1,
    RelativeStrengthClusterScannerV2,
    VolatilityContractionPrefilter,
)


def build_legacy_prefilter_registry() -> dict[str, object]:
    return {
        "crypto_universe_prefilter_v1": CryptoUniversePrefilterV1(),
        "volatility_contraction_prefilter": VolatilityContractionPrefilter(),
        "relative_strength_cluster_scanner_v2": RelativeStrengthClusterScannerV2(),
        "relative_strength_cluster_scanner_v2_alt": RelativeStrengthClusterScannerV2(),
    }


def get_legacy_prefilter_metadata() -> dict[str, dict]:
    return {
        "crypto_universe_prefilter_v1": {
            "family_code": "SCAN-CRYPTO-01",
            "source_type": "legacy_formula",
            "shadow_only": True,
            "status": "DISABLED",
            "role": "prefilter",
        },
        "volatility_contraction_prefilter": {
            "family_code": "SCAN-CONTRACTION-01",
            "source_type": "legacy_formula",
            "shadow_only": True,
            "status": "DISABLED",
            "role": "prefilter",
        },
        "relative_strength_cluster_scanner_v2": {
            "family_code": "SCAN-RS-01",
            "source_type": "legacy_formula",
            "shadow_only": True,
            "status": "DISABLED",
            "role": "scanner",
        },
        "relative_strength_cluster_scanner_v2_alt": {
            "family_code": "SCAN-RS-01-ALT",
            "source_type": "legacy_formula",
            "shadow_only": True,
            "status": "DISABLED",
            "role": "scanner",
        },
    }
