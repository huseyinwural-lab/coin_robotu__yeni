import os
from dataclasses import dataclass


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return float(raw)


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return int(raw)


@dataclass(frozen=True)
class MomentumVolumeBreakoutConfig:
    momentum_threshold: float = _env_float("LEGACY_MVB_MOMENTUM_THRESHOLD", 0.005)
    volume_momentum_threshold: float = _env_float("LEGACY_MVB_VOLUME_MOMENTUM_THRESHOLD", 0.08)
    volume_anomaly_z_threshold: float = _env_float("LEGACY_MVB_VOLUME_ANOMALY_Z_THRESHOLD", 0.45)
    atr_range_threshold: float = _env_float("LEGACY_MVB_ATR_RANGE_THRESHOLD", 0.95)
    breakout_lookback: int = _env_int("LEGACY_MVB_BREAKOUT_LOOKBACK", 20)
    breakout_buffer: float = _env_float("LEGACY_MVB_BREAKOUT_BUFFER", 0.0008)


@dataclass(frozen=True)
class VolatilityBreakoutConfig:
    bb_period: int = _env_int("LEGACY_VB_BB_PERIOD", 20)
    bb_std: float = _env_float("LEGACY_VB_BB_STD", 1.6)
    close_confirm_bars: int = _env_int("LEGACY_VB_CLOSE_CONFIRM_BARS", 2)
    max_spread_bps: float = _env_float("LEGACY_VB_MAX_SPREAD_BPS", 30.0)
    min_volatility: float = _env_float("LEGACY_VB_MIN_VOLATILITY", 0.002)
    min_body_ratio: float = _env_float("LEGACY_VB_MIN_BODY_RATIO", 0.24)
    breakout_buffer: float = _env_float("LEGACY_VB_BREAKOUT_BUFFER", 0.0005)


@dataclass(frozen=True)
class AdaptiveLevelBreakoutConfig:
    breakout_buffer: float = _env_float("LEGACY_ALB_BREAKOUT_BUFFER", 0.001)
    false_breakout_retrace_ratio: float = _env_float("LEGACY_ALB_FALSE_BREAKOUT_RETRACE_RATIO", 0.6)
    min_volume_ratio: float = _env_float("LEGACY_ALB_MIN_VOLUME_RATIO", 0.95)


@dataclass(frozen=True)
class OscillatorCompositeConfig:
    long_threshold: float = _env_float("LEGACY_OCR_LONG_THRESHOLD", 0.34)
    short_threshold: float = _env_float("LEGACY_OCR_SHORT_THRESHOLD", 0.66)
    min_regime_compression: float = _env_float("LEGACY_OCR_MIN_REGIME_COMPRESSION", 0.15)


@dataclass(frozen=True)
class CryptoUniversePrefilterConfig:
    min_liquidity_usd: float = _env_float("LEGACY_PREFILTER_MIN_LIQUIDITY_USD", 2_000_000.0)
    max_spread_bps: float = _env_float("LEGACY_PREFILTER_MAX_SPREAD_BPS", 35.0)
    min_volume_stability: float = _env_float("LEGACY_PREFILTER_MIN_VOLUME_STABILITY", 0.55)
    min_volatility: float = _env_float("LEGACY_PREFILTER_MIN_VOLATILITY", 0.0015)
    max_volatility: float = _env_float("LEGACY_PREFILTER_MAX_VOLATILITY", 0.06)


@dataclass(frozen=True)
class VolatilityContractionPrefilterConfig:
    max_relative_range: float = _env_float("LEGACY_CONTRACTION_MAX_RELATIVE_RANGE", 0.018)
    max_relative_volume: float = _env_float("LEGACY_CONTRACTION_MAX_RELATIVE_VOLUME", 0.95)
    min_compression_score: float = _env_float("LEGACY_CONTRACTION_MIN_COMPRESSION_SCORE", 0.2)


@dataclass(frozen=True)
class RelativeStrengthScannerConfig:
    min_liquidity_usd: float = _env_float("LEGACY_RS_MIN_LIQUIDITY_USD", 1_500_000.0)
    top_n: int = _env_int("LEGACY_RS_TOP_N", 10)
    min_rs_edge: float = _env_float("LEGACY_RS_MIN_EDGE", -0.01)
