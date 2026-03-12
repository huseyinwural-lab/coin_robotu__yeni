from core.execution.production_formula_gate import filter_catalog_by_active_registry
from core.strategies.futures_breakout_v1 import FuturesBreakoutV1
from core.strategies.futures_mean_reversion_v1 import FuturesMeanReversionV1
from core.strategies.legacy import (
    AdaptiveLevelBreakoutV2,
    MomentumVolumeBreakoutV3,
    OscillatorCompositeReversionV2,
    VolatilityBreakoutV2,
)


LEGACY_SOURCE_TYPE = "legacy_formula"


class FuturesTrendFollowAdapter:
    strategy_type = "trend_follow_v1"

    def generate_signal(self, market_state: dict) -> dict:
        trend_strength = float(market_state.get("trend_strength", 0.0))
        trend_direction = str(market_state.get("trend_direction", "NONE")).upper()
        volatility_regime = str(market_state.get("volatility_regime", "RANGING")).upper()
        spread_state = str(market_state.get("spread_state", "NORMAL")).upper()
        funding_alignment = bool(market_state.get("funding_alignment", False))

        if spread_state == "SHOCK" or volatility_regime != "TRENDING" or trend_strength < 0.0025 or not funding_alignment:
            return {
                "signal": "NONE",
                "confidence": 0.0,
                "context": {
                    "strategy_type": self.strategy_type,
                    "reason": "TREND_FILTERED",
                },
            }

        confidence = min(0.95, 0.44 + trend_strength * 38)
        return {
            "signal": trend_direction if trend_direction in {"LONG", "SHORT"} else "NONE",
            "confidence": round(confidence, 4),
            "context": {
                "strategy_type": self.strategy_type,
                "trend_strength": round(trend_strength, 6),
                "regime": volatility_regime,
                "reason": "TREND_FUNDING_ALIGNED",
            },
        }


def _build_catalog_unfiltered() -> dict[str, dict]:
    return {
        "trend_follow_v1": {
            "instance": FuturesTrendFollowAdapter(),
            "family_code": "NATIVE-TREND-01",
            "source_type": "native",
            "shadow_only": False,
            "status": "ACTIVE",
            "role": "strategy",
        },
        "mean_reversion_v1": {
            "instance": FuturesMeanReversionV1(),
            "family_code": "NATIVE-MR-01",
            "source_type": "native",
            "shadow_only": False,
            "status": "ACTIVE",
            "role": "strategy",
        },
        "breakout_v1": {
            "instance": FuturesBreakoutV1(),
            "family_code": "NATIVE-BO-01",
            "source_type": "native",
            "shadow_only": False,
            "status": "ACTIVE",
            "role": "strategy",
        },
        "momentum_volume_breakout_v3": {
            "instance": MomentumVolumeBreakoutV3(),
            "family_code": "BC03",
            "source_type": LEGACY_SOURCE_TYPE,
            "shadow_only": True,
            "status": "DISABLED",
            "role": "strategy",
            "canonical_name": "momentum_volume_breakout_v3",
        },
        "volatility_breakout_v2": {
            "instance": VolatilityBreakoutV2(),
            "family_code": "BC01",
            "source_type": LEGACY_SOURCE_TYPE,
            "shadow_only": True,
            "status": "DISABLED",
            "role": "strategy",
            "canonical_name": "volatility_breakout_v2",
        },
        "adaptive_level_breakout_v2": {
            "instance": AdaptiveLevelBreakoutV2(),
            "family_code": "BC02",
            "source_type": LEGACY_SOURCE_TYPE,
            "shadow_only": True,
            "status": "DISABLED",
            "role": "strategy",
            "canonical_name": "adaptive_level_breakout_v2",
        },
        "oscillator_composite_reversion_v2": {
            "instance": OscillatorCompositeReversionV2(),
            "family_code": "BC04",
            "source_type": LEGACY_SOURCE_TYPE,
            "shadow_only": True,
            "status": "DISABLED",
            "role": "strategy",
            "canonical_name": "oscillator_composite_reversion_v2",
        },
    }


def build_strategy_catalog() -> dict[str, dict]:
    catalog = _build_catalog_unfiltered()
    return filter_catalog_by_active_registry(catalog)


def build_strategy_registry() -> dict:
    catalog = build_strategy_catalog()
    return {strategy_id: item["instance"] for strategy_id, item in catalog.items()}


def get_strategy_metadata_map() -> dict[str, dict]:
    catalog = _build_catalog_unfiltered()
    metadata: dict[str, dict] = {}
    for strategy_id, item in catalog.items():
        metadata[strategy_id] = {
            "strategy": strategy_id,
            "family_code": item.get("family_code"),
            "source_type": item.get("source_type", "native"),
            "shadow_only": bool(item.get("shadow_only", False)),
            "status": item.get("status", "ACTIVE"),
            "role": item.get("role", "strategy"),
            "canonical_name": item.get("canonical_name", strategy_id),
        }
    return metadata


def get_legacy_shadow_strategy_ids() -> list[str]:
    return [
        strategy_id
        for strategy_id, metadata in get_strategy_metadata_map().items()
        if metadata.get("source_type") == LEGACY_SOURCE_TYPE and bool(metadata.get("shadow_only"))
    ]
