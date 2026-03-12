import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.strategies.prefilters.volatility_contraction_prefilter import VolatilityContractionPrefilter


def test_volatility_contraction_prefilter_detects_contracted_state():
    prefilter = VolatilityContractionPrefilter()
    payload = prefilter.scan(
        [
            {
                "symbol": "ETHUSDT",
                "relative_range": 0.01,
                "relative_volume": 0.8,
                "volatility_compression": 0.35,
            },
            {
                "symbol": "WILDUSDT",
                "relative_range": 0.06,
                "relative_volume": 2.1,
                "volatility_compression": 0.05,
            },
        ]
    )
    assert "ETHUSDT" in payload["selected_symbols"]
    assert "WILDUSDT" not in payload["selected_symbols"]
