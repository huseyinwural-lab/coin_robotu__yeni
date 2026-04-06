import os
import uuid
from datetime import datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from db import redis_client
from models import (
    BotProfile,
    PaperPosition,
    PendingSignal,
    RiskPolicy,
    RiskOrchestratorPolicy,
    SignalEvent,
    UserExchangeConnection,
    UserExecutionIntent,
    UserScannerAutomationConfig,
    UserScannerAutomationProfile,
    UserScannerResult,
    UserSignalMode,
)
from services.execution_intent_service import (
    approve_execution_intent,
    preview_execution_intent,
    submit_execution_intent,
)
from core.users.user_portfolio_engine import build_user_portfolio_snapshot
from services.explainability_service import record_decision_trace
from services.meta_strategy_engine_service import run_meta_strategy_engine
from services.canonical_strategy_registry_service import GLOBAL_RISK_POLICY
from services.pipeline.cache_store import get_json, incr_counter, set_json
from services.pipeline.canonical_signal_engine import scan_canonical_universe_for_signals
from services.pipeline.universe_engine import apply_scanner_mode, build_effective_universe, normalize_scanner_mode
from services.quote_asset_policy import extract_quote_asset, filter_allowed_quote_symbols
from services.risk_policy_defaults_service import ensure_user_safe_default_risk_policy
from services.scanner_observability_service import (
    get_rollout_state,
    record_fallback_event,
    record_scanner_perf_snapshot,
    resolve_fallback_mode,
)
from services.venue_service import check_user_venue_access, seed_binance_venue_registry

ALLOWED_SIGNAL_MODES = {"ASSISTED", "AUTO", "MANUAL"}
DEFAULT_SIGNAL_MODE = "MANUAL"
ALLOWED_SCANNER_SOURCES = {"crypto", "stock"}
ALLOWED_SCANNER_SELECTION_MODES = {"all_market_symbols", "top_volume", "manual_selection"}
ALLOWED_SCANNER_MARKET_TYPES = {"spot", "futures", "all"}
FRESHNESS_SLA_SECONDS = {
    "3m": 90,
    "5m": 150,
    "15m": 360,
}

SIGNAL_PENDING_REASON_HINTS = {
    "MANUAL_APPROVAL_REQUIRED": (
        "Sinyal manuel onay bekliyor.",
        "Signals satırından Approve veya Fix All Blockers ile AUTO moda geçirip devam edin.",
    ),
    "BOT_NOT_RUNNING": ("Bot runtime çalışmıyor.", "Bot profilini başlatın (is_running=true)."),
    "RISK_POLICY_MISSING": ("Risk policy tanımlı değil.", "Signals satırından Auto-Fix veya Risk Policy ekranından policy oluşturun."),
    "RISK_LIMIT_BLOCKED": ("Risk limiti engeli oluştu.", "Risk limitlerini veya mevcut pozisyon riskini kontrol edin."),
    "EXCHANGE_NOT_READY": ("Exchange readiness uygun değil.", "Exchange key/venue assignment/readiness durumunu düzeltin."),
    "MARKET_DATA_STALE": ("Piyasa verisi güncel değil.", "Market data akışını ve son candle zamanını doğrulayın."),
    "POSITION_LIMIT_REACHED": ("Pozisyon limiti dolu.", "Açık pozisyon sayısını azaltın veya policy limitini artırın."),
    "SYMBOL_NOT_ALLOWED": ("Sembol bot kapsamı dışında.", "Bot symbols listesine sembolü ekleyin."),
    "ORDER_PRECHECK_FAILED": ("Order precheck başarısız.", "Preview hata kodlarını inceleyip parametreleri düzeltin."),
    "EXECUTION_DISABLED": ("Execution strategy tarafından devre dışı.", "Meta strategy / bot strategy eşleşmesini düzeltin."),
    "SIGNAL_EXPIRED": ("Signal süresi doldu.", "Yeni sinyal üretimi bekleyin veya scanner yeniden çalıştırın."),
    "STALE_DATA_BLOCK": (
        "Veri snapshot yaşı freshness SLA eşiğini aştı.",
        "Taze candle/snapshot gelene kadar sinyal trade intent'e çevrilmez.",
    ),
}

SIGNAL_REASON_PRIORITY = [
    "SIGNAL_EXPIRED",
    "BOT_NOT_RUNNING",
    "RISK_POLICY_MISSING",
    "POSITION_LIMIT_REACHED",
    "RISK_LIMIT_BLOCKED",
    "EXCHANGE_NOT_READY",
    "MARKET_DATA_STALE",
    "STALE_DATA_BLOCK",
    "SYMBOL_NOT_ALLOWED",
    "EXECUTION_DISABLED",
    "ORDER_PRECHECK_FAILED",
    "MANUAL_APPROVAL_REQUIRED",
]


def _ensure_scanner_tables(db: Session):
    inspector = inspect(db.bind)
    existing = set(inspector.get_table_names())
    required_models = [
        UserSignalMode,
        BotProfile,
        UserScannerResult,
        SignalEvent,
        PendingSignal,
        PaperPosition,
        RiskPolicy,
        UserExchangeConnection,
    ]
    for model in required_models:
        table_name = model.__table__.name
        if table_name not in existing:
            model.__table__.create(bind=db.bind, checkfirst=True)
            existing.add(table_name)


def _normalize_mode(mode: str | None) -> str:
    candidate = (mode or DEFAULT_SIGNAL_MODE).strip().upper()
    if candidate not in ALLOWED_SIGNAL_MODES:
        return DEFAULT_SIGNAL_MODE
    return candidate


def _normalize_symbol_source(source: str | None) -> str:
    candidate = str(source or "crypto").strip().lower()
    return candidate if candidate in ALLOWED_SCANNER_SOURCES else "crypto"


def _normalize_symbol_selection_mode(selection_mode: str | None) -> str:
    normalized = normalize_scanner_mode(selection_mode)
    candidate = normalized.strip().lower()
    return candidate if candidate in ALLOWED_SCANNER_SELECTION_MODES else "all_market_symbols"


def _normalize_scanner_market_type(market_type: str | None) -> str:
    candidate = str(market_type or "all").strip().lower()
    return candidate if candidate in ALLOWED_SCANNER_MARKET_TYPES else "all"


def _freshness_threshold_for_timeframe(timeframe: str | None) -> int:
    return int(FRESHNESS_SLA_SECONDS.get(str(timeframe or "15m").lower(), FRESHNESS_SLA_SECONDS["15m"]))


def _is_stale_snapshot(age_seconds: float | int | None, timeframe: str | None = "15m") -> bool:
    try:
        age = float(age_seconds or 0)
    except (TypeError, ValueError):
        age = 0.0
    return age > float(_freshness_threshold_for_timeframe(timeframe))


def _build_candidate_tiers(
    *,
    user_open_symbols: set[str],
    scanner_scope: list[str],
    advisory_lookup: dict,
    volume_lookup: dict[str, float],
    event_hints: set[str],
    normalized_selection_mode: str,
) -> dict[str, list[str]]:
    scope_unique = [str(symbol).upper() for symbol in scanner_scope if str(symbol).strip()]
    scope_unique = list(dict.fromkeys(scope_unique))
    if not scope_unique:
        return {"candidate_high": [], "candidate_medium": [], "candidate_low": [], "ignore_for_now": [], "decision_scope": []}

    ranked_by_volume = sorted(scope_unique, key=lambda item: float(volume_lookup.get(item, 0.0)), reverse=True)
    top_volume_40 = set(ranked_by_volume[:40])
    top_volume_120 = set(ranked_by_volume[:120])

    candidate_high_set = set(symbol for symbol in scope_unique if symbol in user_open_symbols or symbol in event_hints or symbol in top_volume_40)
    candidate_medium_set = set(symbol for symbol in scope_unique if symbol in top_volume_120 and symbol not in candidate_high_set)
    ignore_set = set(
        symbol
        for symbol in scope_unique
        if str((advisory_lookup.get(symbol) or {}).get("advisory_state") or "") == "data_unavailable"
    )
    candidate_low_set = set(scope_unique) - candidate_high_set - candidate_medium_set - ignore_set

    if normalized_selection_mode == "manual_selection":
        decision_scope = [symbol for symbol in scope_unique if symbol not in ignore_set]
    else:
        decision_scope = [
            symbol
            for symbol in scope_unique
            if symbol in candidate_high_set or symbol in candidate_medium_set
        ]
        if not decision_scope:
            decision_scope = [symbol for symbol in scope_unique if symbol not in ignore_set][:120]

    return {
        "candidate_high": [symbol for symbol in scope_unique if symbol in candidate_high_set],
        "candidate_medium": [symbol for symbol in scope_unique if symbol in candidate_medium_set],
        "candidate_low": [symbol for symbol in scope_unique if symbol in candidate_low_set],
        "ignore_for_now": [symbol for symbol in scope_unique if symbol in ignore_set],
        "decision_scope": decision_scope,
    }


def _parse_candle_time(raw_value) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)
    if isinstance(raw_value, (int, float)):
        ts = float(raw_value)
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    value = str(raw_value).strip()
    if not value:
        return None
    if value.isdigit():
        return _parse_candle_time(int(value))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _snapshot_age_seconds(symbol: str, timeframe: str = "15m") -> float | None:
    candles = get_json(redis_client, f"market_data_store:{symbol}:{timeframe}") or get_json(redis_client, f"market:candles:{symbol}:{timeframe}") or []
    if not candles:
        return None
    latest = candles[-1]
    if not isinstance(latest, dict):
        return None
    close_raw = latest.get("close_time") or latest.get("timestamp") or latest.get("time")
    close_dt = _parse_candle_time(close_raw)
    if close_dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - close_dt).total_seconds())


def _acquire_symbol_lock(lock_key: str, token: str, ttl_seconds: int = 90) -> bool:
    try:
        acquired = redis_client.set(lock_key, token, ex=ttl_seconds, nx=True)
        return bool(acquired)
    except TypeError:
        existing = redis_client.get(lock_key)
        if existing:
            return False
        redis_client.set(lock_key, token)
        return True


def _release_symbol_lock(lock_key: str) -> None:
    try:
        redis_client.delete(lock_key)
    except Exception:
        pass


def _normalize_selected_symbols(symbols: list[str] | None) -> list[str]:
    normalized = [str(item or "").strip().upper() for item in (symbols or []) if str(item or "").strip()]
    return filter_allowed_quote_symbols(normalized)


def _clamp_scanner_max_results(max_results: int | None) -> int:
    try:
        value = int(max_results or 25)
    except (TypeError, ValueError):
        value = 25
    return max(5, min(100, value))


def _clamp_interval_seconds(interval_seconds: int | None) -> int:
    try:
        value = int(interval_seconds or 60)
    except (TypeError, ValueError):
        value = 60
    return max(30, min(120, value))


def _clamp_profile_interval_seconds(interval_seconds: int | None) -> int:
    try:
        value = int(interval_seconds or 60)
    except (TypeError, ValueError):
        value = 60
    return max(30, min(120, value))


def _next_scanner_run_at(config: UserScannerAutomationConfig) -> datetime | None:
    if not config.auto_enabled:
        return None
    if config.last_run_at is None:
        return datetime.now(timezone.utc)
    base = config.last_run_at
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(seconds=int(config.interval_seconds or 60))


def _next_profile_run_at(profile: UserScannerAutomationProfile) -> datetime | None:
    if not profile.auto_enabled:
        return None
    if profile.last_run_at is None:
        return datetime.now(timezone.utc)
    base = profile.last_run_at
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(seconds=int(profile.interval_seconds or 60))


def get_or_create_scanner_automation_config(db: Session, user_id: str) -> UserScannerAutomationConfig:
    row = db.query(UserScannerAutomationConfig).filter(UserScannerAutomationConfig.user_id == user_id).first()
    if row:
        return row

    row = UserScannerAutomationConfig(
        id=str(uuid.uuid4()),
        user_id=user_id,
        auto_enabled=True,
        interval_seconds=60,
        max_results=25,
        symbol_source="crypto",
        symbol_selection_mode="all_market_symbols",
        selected_symbols=[],
        last_run_status="idle",
        last_actionable_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_scanner_automation_config(
    db: Session,
    user_id: str,
    *,
    auto_enabled: bool,
    interval_seconds: int,
    max_results: int,
    symbol_source: str,
    symbol_selection_mode: str,
    selected_symbols: list[str],
) -> UserScannerAutomationConfig:
    row = get_or_create_scanner_automation_config(db, user_id)
    row.auto_enabled = bool(auto_enabled)
    row.interval_seconds = _clamp_interval_seconds(interval_seconds)
    row.max_results = _clamp_scanner_max_results(max_results)
    row.symbol_source = _normalize_symbol_source(symbol_source)
    row.symbol_selection_mode = _normalize_symbol_selection_mode(symbol_selection_mode)
    row.selected_symbols = _normalize_selected_symbols(selected_symbols)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def scanner_automation_config_response_payload(config: UserScannerAutomationConfig) -> dict:
    return {
        "id": config.id,
        "user_id": config.user_id,
        "auto_enabled": bool(config.auto_enabled),
        "interval_seconds": int(config.interval_seconds or 60),
        "max_results": _clamp_scanner_max_results(config.max_results),
        "symbol_source": _normalize_symbol_source(config.symbol_source),
        "symbol_selection_mode": _normalize_symbol_selection_mode(config.symbol_selection_mode),
        "selected_symbols": _normalize_selected_symbols(config.selected_symbols),
        "last_run_id": config.last_run_id,
        "last_run_status": config.last_run_status or "idle",
        "last_actionable_count": int(config.last_actionable_count or 0),
        "last_run_error": config.last_run_error,
        "last_run_at": config.last_run_at,
        "next_run_at": _next_scanner_run_at(config),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def scanner_automation_profile_response_payload(profile: UserScannerAutomationProfile) -> dict:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "name": profile.name,
        "auto_enabled": bool(profile.auto_enabled),
        "is_active": bool(profile.is_active),
        "interval_seconds": _clamp_profile_interval_seconds(profile.interval_seconds),
        "max_results": _clamp_scanner_max_results(profile.max_results),
        "symbol_source": _normalize_symbol_source(profile.symbol_source),
        "symbol_selection_mode": _normalize_symbol_selection_mode(profile.symbol_selection_mode),
        "selected_symbols": _normalize_selected_symbols(profile.selected_symbols),
        "last_run_id": profile.last_run_id,
        "last_run_status": profile.last_run_status or "idle",
        "last_actionable_count": int(profile.last_actionable_count or 0),
        "last_run_error": profile.last_run_error,
        "last_run_at": profile.last_run_at,
        "next_run_at": _next_profile_run_at(profile),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def list_scanner_automation_profiles(db: Session, user_id: str) -> list[UserScannerAutomationProfile]:
    rows = (
        db.query(UserScannerAutomationProfile)
        .filter(UserScannerAutomationProfile.user_id == user_id)
        .order_by(UserScannerAutomationProfile.is_active.desc(), UserScannerAutomationProfile.updated_at.desc())
        .all()
    )
    return rows


def create_scanner_automation_profile(
    db: Session,
    user_id: str,
    *,
    name: str,
    auto_enabled: bool,
    is_active: bool,
    interval_seconds: int,
    max_results: int,
    symbol_source: str,
    symbol_selection_mode: str,
    selected_symbols: list[str],
) -> UserScannerAutomationProfile:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("profile_name_required")

    existing = (
        db.query(UserScannerAutomationProfile)
        .filter(UserScannerAutomationProfile.user_id == user_id, UserScannerAutomationProfile.name == normalized_name)
        .first()
    )
    if existing is not None:
        raise ValueError("profile_name_already_exists")

    if is_active:
        db.query(UserScannerAutomationProfile).filter(UserScannerAutomationProfile.user_id == user_id).update(
            {UserScannerAutomationProfile.is_active: False}
        )

    row = UserScannerAutomationProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=normalized_name,
        auto_enabled=bool(auto_enabled),
        is_active=bool(is_active),
        interval_seconds=_clamp_profile_interval_seconds(interval_seconds),
        max_results=_clamp_scanner_max_results(max_results),
        symbol_source=_normalize_symbol_source(symbol_source),
        symbol_selection_mode=_normalize_symbol_selection_mode(symbol_selection_mode),
        selected_symbols=_normalize_selected_symbols(selected_symbols),
        last_run_status="idle",
        last_actionable_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_scanner_automation_profile(
    db: Session,
    user_id: str,
    profile_id: str,
    *,
    name: str,
    auto_enabled: bool,
    is_active: bool,
    interval_seconds: int,
    max_results: int,
    symbol_source: str,
    symbol_selection_mode: str,
    selected_symbols: list[str],
) -> UserScannerAutomationProfile:
    row = (
        db.query(UserScannerAutomationProfile)
        .filter(UserScannerAutomationProfile.id == profile_id, UserScannerAutomationProfile.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("scanner_automation_profile_not_found")

    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("profile_name_required")

    name_conflict = (
        db.query(UserScannerAutomationProfile)
        .filter(
            UserScannerAutomationProfile.user_id == user_id,
            UserScannerAutomationProfile.name == normalized_name,
            UserScannerAutomationProfile.id != profile_id,
        )
        .first()
    )
    if name_conflict is not None:
        raise ValueError("profile_name_already_exists")

    if is_active:
        db.query(UserScannerAutomationProfile).filter(
            UserScannerAutomationProfile.user_id == user_id,
            UserScannerAutomationProfile.id != profile_id,
        ).update({UserScannerAutomationProfile.is_active: False})

    row.name = normalized_name
    row.auto_enabled = bool(auto_enabled)
    row.is_active = bool(is_active)
    row.interval_seconds = _clamp_profile_interval_seconds(interval_seconds)
    row.max_results = _clamp_scanner_max_results(max_results)
    row.symbol_source = _normalize_symbol_source(symbol_source)
    row.symbol_selection_mode = _normalize_symbol_selection_mode(symbol_selection_mode)
    row.selected_symbols = _normalize_selected_symbols(selected_symbols)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def activate_scanner_automation_profile(db: Session, user_id: str, profile_id: str) -> UserScannerAutomationProfile:
    row = (
        db.query(UserScannerAutomationProfile)
        .filter(UserScannerAutomationProfile.id == profile_id, UserScannerAutomationProfile.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("scanner_automation_profile_not_found")

    db.query(UserScannerAutomationProfile).filter(UserScannerAutomationProfile.user_id == user_id).update(
        {UserScannerAutomationProfile.is_active: False}
    )
    row.is_active = True
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def delete_scanner_automation_profile(db: Session, user_id: str, profile_id: str) -> bool:
    row = (
        db.query(UserScannerAutomationProfile)
        .filter(UserScannerAutomationProfile.id == profile_id, UserScannerAutomationProfile.user_id == user_id)
        .first()
    )
    if row is None:
        return False

    was_active = bool(row.is_active)
    db.delete(row)
    db.commit()

    if was_active:
        fallback = (
            db.query(UserScannerAutomationProfile)
            .filter(UserScannerAutomationProfile.user_id == user_id)
            .order_by(UserScannerAutomationProfile.updated_at.desc())
            .first()
        )
        if fallback is not None:
            fallback.is_active = True
            fallback.updated_at = datetime.now(timezone.utc)
            db.commit()
    return True


def _user_symbols_scope(db: Session, user_id: str) -> set[str]:
    rows = db.query(BotProfile).filter(BotProfile.user_id == user_id, BotProfile.is_deleted.is_(False)).all()
    symbols: set[str] = set()
    for row in rows:
        symbols.update((row.symbols or []))
    return {symbol.upper() for symbol in symbols if symbol}


def _has_active_bot(db: Session, user_id: str) -> bool:
    row = (
        db.query(BotProfile)
        .filter(BotProfile.user_id == user_id, BotProfile.is_deleted.is_(False), BotProfile.is_running.is_(True), BotProfile.is_enabled.is_(True))
        .order_by(BotProfile.updated_at.desc())
        .first()
    )
    return row is not None


def _default_bot_for_user(db: Session, user_id: str, symbols: list[str], market_type: str) -> BotProfile:
    normalized_symbols = [symbol.upper() for symbol in symbols if symbol]
    normalized_market_type = _normalize_scanner_market_type(market_type)

    running_row = (
        db.query(BotProfile)
        .filter(
            BotProfile.user_id == user_id,
            BotProfile.is_deleted.is_(False),
            BotProfile.is_running.is_(True),
            BotProfile.market_type == normalized_market_type,
        )
        .order_by(BotProfile.created_at.desc())
        .first()
    )
    if running_row:
        merged_symbols = list(dict.fromkeys([*normalized_symbols, *(running_row.symbols or [])]))[:40]
        if merged_symbols != (running_row.symbols or []):
            running_row.symbols = merged_symbols
        if int(getattr(running_row, "leverage", 1) or 1) != 1:
            running_row.leverage = 1
        running_row.updated_at = datetime.now(timezone.utc)
        db.flush()
        return running_row

    row = (
        db.query(BotProfile)
        .filter(
            BotProfile.user_id == user_id,
            BotProfile.is_deleted.is_(False),
            BotProfile.market_type == normalized_market_type,
        )
        .order_by(BotProfile.created_at.desc())
        .first()
    )
    if row:
        row.is_running = True
        merged_symbols = list(dict.fromkeys([*normalized_symbols, *(row.symbols or [])]))[:40]
        row.symbols = merged_symbols
        if str(row.market_type or "spot").lower() != normalized_market_type:
            row.market_type = normalized_market_type
        row.leverage = 1
        row.updated_at = datetime.now(timezone.utc)
        db.flush()
        return row

    row = BotProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="Assisted Signal Bot",
        exchange="binance",
        market_type=normalized_market_type,
        symbols=normalized_symbols[:40],
        strategy_type="futures_momentum" if normalized_market_type == "futures" else "spot_pullback",
        timeframe="15m",
        trend_timeframe="1h",
        leverage=1,
        is_enabled=True,
        is_running=True,
    )
    db.add(row)
    db.flush()
    return row


def _execution_mode_label(mode: str | None) -> str:
    normalized = _normalize_mode(mode)
    if normalized == "MANUAL":
        return "Manual"
    if normalized == "AUTO":
        return "Full Auto"
    return "Semi-Auto"


def _requires_manual_approval(mode: str | None) -> bool:
    return _normalize_mode(mode) in {"MANUAL", "ASSISTED"}


def _base_strategy_code(strategy_code: str | None) -> str:
    raw = (strategy_code or "").strip().lower()
    if "_v" in raw:
        return raw.split("_v", 1)[0]
    return raw


def _resolve_default_risk_policy(db: Session, user_id: str) -> RiskPolicy | None:
    return (
        db.query(RiskPolicy)
        .filter(RiskPolicy.user_id == user_id)
        .order_by(RiskPolicy.updated_at.desc())
        .first()
    )


def _resolve_default_exchange_connection(db: Session, user_id: str) -> UserExchangeConnection | None:
    return (
        db.query(UserExchangeConnection)
        .filter(UserExchangeConnection.user_id == user_id)
        .order_by(UserExchangeConnection.is_default.desc(), UserExchangeConnection.updated_at.desc())
        .first()
    )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        candidate = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _is_market_data_stale(symbol: str, stale_minutes: int = 12) -> bool:
    payload = get_json(redis_client, f"market:ticker:{symbol.upper()}") or {}
    timestamp_raw = payload.get("updated_at") or payload.get("timestamp")
    parsed = _parse_iso_datetime(str(timestamp_raw)) if timestamp_raw else None
    if parsed is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
    return age_seconds > stale_minutes * 60


def _signal_reason_details(reason_code: str) -> tuple[str, str]:
    return SIGNAL_PENDING_REASON_HINTS.get(
        reason_code,
        ("Sinyal işleme dönüşemedi.", "Decision trace ve execution precheck kayıtlarını inceleyin."),
    )


def _apply_order_precheck_failed(
    row: PendingSignal,
    *,
    reason_codes: list[str] | None = None,
    error_detail: str = "",
) -> None:
    row.execution_eligible = False
    row.status = "blocked"
    row.blocked_reason_code = "ORDER_PRECHECK_FAILED"

    base_message, base_hint = _signal_reason_details("ORDER_PRECHECK_FAILED")
    normalized_codes = [str(code).strip() for code in (reason_codes or []) if str(code).strip()]

    if normalized_codes:
        compact_codes = normalized_codes[:5]
        row.blocked_reason_message = f"{base_message} / codes: {', '.join(compact_codes)}"
        row.blocked_solution_hint = (
            f"Precheck kodları: {', '.join(compact_codes)}. Exchange connection, permission snapshot ve risk limitlerini doğrulayın."
        )
        row.decision_note = f"order_precheck_failed:{'|'.join(compact_codes)}"[:240]
    elif error_detail:
        compact_detail = str(error_detail).replace("\n", " ").strip()[:180]
        row.blocked_reason_message = f"{base_message} / detail: {compact_detail}"
        row.blocked_solution_hint = "Exchange connection ve execution preview parametrelerini kontrol edin."
        row.decision_note = f"order_precheck_failed:{compact_detail}"[:240]
    else:
        row.blocked_reason_message = base_message
        row.blocked_solution_hint = base_hint
        row.decision_note = "order_precheck_failed"

    _set_state(row, "BLOCKED")


def _primary_reason_code(reason_codes: list[str]) -> str:
    for code in SIGNAL_REASON_PRIORITY:
        if code in reason_codes:
            return code
    return reason_codes[0] if reason_codes else ""


def _set_state(row: PendingSignal, next_state: str) -> None:
    if row.current_state == next_state:
        return
    row.previous_state = row.current_state or "DETECTED"
    row.current_state = next_state
    row.last_transition_at = datetime.now(timezone.utc)


def _evaluate_signal_blockers(
    db: Session,
    *,
    row: PendingSignal,
    signal: SignalEvent,
    bot: BotProfile | None,
    risk_policy: RiskPolicy | None,
    exchange_connection: UserExchangeConnection | None,
) -> tuple[list[str], bool, bool]:
    reason_codes: list[str] = []
    requires_manual = _requires_manual_approval(row.mode)

    if requires_manual:
        reason_codes.append("MANUAL_APPROVAL_REQUIRED")

    if bot is None or not bool(bot.is_running):
        reason_codes.append("BOT_NOT_RUNNING")

    if bot is not None:
        symbols = {item.upper() for item in (bot.symbols or []) if item}
        if symbols and row.symbol.upper() not in symbols:
            reason_codes.append("SYMBOL_NOT_ALLOWED")

        signal_strategy = _base_strategy_code(signal.strategy_id)
        bot_strategy = _base_strategy_code(bot.strategy_type)
        generic_runtime_strategies = {"spot_pullback", "trend_following", "mean_reversion", "volatility_breakout"}
        if (
            bot_strategy
            and signal_strategy
            and bot_strategy not in generic_runtime_strategies
            and bot_strategy != signal_strategy
        ):
            reason_codes.append("EXECUTION_DISABLED")

        if signal.market_type and bot.market_type and str(signal.market_type).lower() != str(bot.market_type).lower():
            reason_codes.append("EXECUTION_DISABLED")

    if risk_policy is None:
        reason_codes.append("RISK_POLICY_MISSING")
    else:
        ignore_position_limit = str(os.getenv("LIVE_SCANNER_IGNORE_POSITION_LIMIT", "1")).strip().lower() in {"1", "true", "yes"}
        open_positions = (
            db.query(PaperPosition)
            .filter(PaperPosition.user_id == row.user_id, PaperPosition.status == "open")
            .count()
        )
        if (not ignore_position_limit) and open_positions >= int(risk_policy.max_open_positions or 0):
            reason_codes.append("POSITION_LIMIT_REACHED")

    if row.meta_engine_decision == "DISABLED":
        reason_codes.append("EXECUTION_DISABLED")

    if _is_market_data_stale(row.symbol):
        reason_codes.append("MARKET_DATA_STALE")

    signal_generated_at = signal.generated_at
    if signal_generated_at.tzinfo is None:
        signal_generated_at = signal_generated_at.replace(tzinfo=timezone.utc)
    signal_age_seconds = (datetime.now(timezone.utc) - signal_generated_at).total_seconds()
    if signal_age_seconds > 60 * 45:
        reason_codes.append("SIGNAL_EXPIRED")

    if exchange_connection is None:
        reason_codes.append("EXCHANGE_NOT_READY")
    elif str(exchange_connection.environment).lower() == "live":
        seed_binance_venue_registry(db)
        allowed, _, _, _ = check_user_venue_access(
            db,
            row.user_id,
            exchange_connection.exchange,
            exchange_connection.market_type,
            exchange_connection.environment,
        )
        if not allowed:
            reason_codes.append("EXCHANGE_NOT_READY")

    deduped = list(dict.fromkeys(reason_codes))
    hard_blockers = [code for code in deduped if code != "MANUAL_APPROVAL_REQUIRED"]
    execution_eligible = len(hard_blockers) == 0 and not requires_manual
    return deduped, requires_manual, execution_eligible


def _refresh_pending_signal_snapshot(db: Session, row: PendingSignal) -> PendingSignal:
    if row.current_state in {"ORDER_SUBMITTED", "FILLED", "REJECTED"}:
        return row
    if row.current_state == "BLOCKED" and row.blocked_reason_code == "ORDER_PRECHECK_FAILED":
        row.status = "blocked"
        row.execution_eligible = False
        row.last_eligibility_check_at = datetime.now(timezone.utc)
        return row

    if row.mode != "AUTO" and _has_active_bot(db, row.user_id):
        row.mode = "AUTO"

    signal = db.query(SignalEvent).filter(SignalEvent.id == row.signal_id, SignalEvent.user_id == row.user_id).first()
    if signal is None:
        row.blocked_reason_code = "SIGNAL_EXPIRED"
        row.blocked_reason_message, row.blocked_solution_hint = _signal_reason_details("SIGNAL_EXPIRED")
        row.status = "expired"
        row.execution_eligible = False
        _set_state(row, "EXPIRED")
        row.last_eligibility_check_at = datetime.now(timezone.utc)
        return row

    bot = db.query(BotProfile).filter(BotProfile.id == signal.bot_profile_id, BotProfile.is_deleted.is_(False)).first()
    risk_policy = _resolve_default_risk_policy(db, row.user_id)
    exchange_connection = _resolve_default_exchange_connection(db, row.user_id)
    reason_codes, requires_manual, execution_eligible = _evaluate_signal_blockers(
        db,
        row=row,
        signal=signal,
        bot=bot,
        risk_policy=risk_policy,
        exchange_connection=exchange_connection,
    )

    primary_reason = _primary_reason_code(reason_codes)
    message, hint = _signal_reason_details(primary_reason) if primary_reason else ("", "")

    row.bot_profile_id = bot.id if bot else None
    row.risk_policy_id = risk_policy.id if risk_policy else None
    row.exchange_connection_id = exchange_connection.id if exchange_connection else None
    row.runtime_owner = bot.name if bot else ""
    row.requires_manual_approval = requires_manual
    row.execution_eligible = execution_eligible
    row.blocked_reason_code = primary_reason
    row.blocked_reason_message = message
    row.blocked_solution_hint = hint
    row.last_eligibility_check_at = datetime.now(timezone.utc)

    if primary_reason == "SIGNAL_EXPIRED":
        row.status = "expired"
        _set_state(row, "EXPIRED")
    elif execution_eligible:
        row.status = "ready"
        _set_state(row, "EXECUTION_READY")
    elif primary_reason == "MANUAL_APPROVAL_REQUIRED":
        row.status = "pending"
        _set_state(row, "PENDING_APPROVAL")
    else:
        row.status = "blocked"
        _set_state(row, "BLOCKED")

    return row


def _build_signal_intent_payload(
    row: PendingSignal,
    signal: SignalEvent,
    exchange_connection: UserExchangeConnection | None,
    position_size_value_usdt: float,
) -> dict:
    side = "buy" if signal.direction == "long" else "sell"
    market_type = (signal.market_type or "spot").lower()
    strategy_binding = str(signal.strategy_id or "trend_following")
    scanner_timestamp = datetime.now(timezone.utc).isoformat()
    score_value = round(float(row.confidence or 0.5) * 100.0, 4)
    scanner_signal_snapshot = {
        "symbol": row.symbol,
        "signal": signal.direction,
        "score": score_value,
        "strategy": strategy_binding,
        "confidence": float(row.confidence or 0.5),
        "timestamp": scanner_timestamp,
    }
    payload = {
        "source_type": "scanner",
        "source_ref_id": row.signal_id,
        "market_type": market_type,
        "symbol": row.symbol,
        "side": side,
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": round(max(float(position_size_value_usdt or 0.0), 0.0), 4),
        "take_profit_mode": "percent",
        "take_profit_value": 2,
        "stop_loss_mode": "percent",
        "stop_loss_value": 1,
        "execution_mode": "bot_assisted",
        "strategy_binding": strategy_binding,
        "signal_confidence": float(row.confidence or 0.5),
        "signal_bridge_context": True,
        "signal": signal.direction,
        "score": score_value,
        "strategy": strategy_binding,
        "confidence": float(row.confidence or 0.5),
        "timestamp": scanner_timestamp,
        "scanner_signal_snapshot": scanner_signal_snapshot,
    }

    if market_type == "futures":
        payload["margin_mode"] = "isolated"
        payload["leverage"] = 1

    if exchange_connection is not None:
        payload.update(
            {
                "exchange_connection_id": exchange_connection.id,
                "exchange": exchange_connection.exchange,
                "environment": exchange_connection.environment,
                "account_label": exchange_connection.account_label,
            }
        )
    return payload


def _resolve_dynamic_trade_notional_usdt(db: Session, user_id: str) -> float:
    try:
        snapshot = build_user_portfolio_snapshot(db, user_id)
    except Exception:
        snapshot = {}

    available_balance = float(snapshot.get("available_balance") or 0.0)
    current_capital = float(snapshot.get("current_capital") or 0.0)
    reference_balance = available_balance if available_balance > 0 else current_capital
    if reference_balance <= 0:
        return 0.0

    # User constraint: per trade max 20% of wallet balance.
    return round(reference_balance * 0.19, 4)


def _dispatch_signal_to_execution(
    db: Session,
    *,
    row: PendingSignal,
    signal: SignalEvent,
    exchange_connection: UserExchangeConnection | None,
    actor_user_id: str,
) -> PendingSignal:
    _set_state(row, "APPROVED")
    row.status = "approved"
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = row.decision_note or "approved"

    dynamic_notional_usdt = _resolve_dynamic_trade_notional_usdt(db, row.user_id)
    payload = _build_signal_intent_payload(row, signal, exchange_connection, dynamic_notional_usdt)
    intent, validation = preview_execution_intent(db, row.user_id, payload)
    row.created_order_intent_id = intent.id
    _set_state(row, "ORDER_INTENT_CREATED")

    if validation.get("validation_status") != "valid":
        reason_codes = [str(item) for item in (validation.get("reject_reason_codes") or []) if str(item).strip()]
        _apply_order_precheck_failed(row, reason_codes=reason_codes)
        return row

    submitted_intent = submit_execution_intent(db, row.user_id, intent.intent_token, preview_hash=intent.preview_hash)
    _set_state(row, "ORDER_SUBMITTED")
    row.status = "submitted"

    submitted_status = str(getattr(submitted_intent, "status", "")).upper()
    if submitted_status in {"RELEASED", "FILLED", "EXECUTED"}:
        row.order_position_id = submitted_intent.position_id
        row.status = "filled"
        row.execution_eligible = True
        row.blocked_reason_code = ""
        row.blocked_reason_message = ""
        row.blocked_solution_hint = ""
        row.decision_note = "approved_and_filled"
        _set_state(row, "FILLED")
        return row

    try:
        released_intent = approve_execution_intent(
            db,
            submitted_intent.id,
            admin_user_id=actor_user_id,
            admin_note="signal_runtime_auto_release",
        )
    except ValueError as exc:
        if str(exc) == "intent_not_in_queue":
            latest_intent = db.query(UserExecutionIntent).filter(UserExecutionIntent.id == submitted_intent.id).first()
            latest_status = str(getattr(latest_intent, "status", "")).upper()
            if latest_status in {"RELEASED", "FILLED", "EXECUTED"}:
                row.order_position_id = getattr(latest_intent, "position_id", None)
                row.status = "filled"
                row.execution_eligible = True
                row.blocked_reason_code = ""
                row.blocked_reason_message = ""
                row.blocked_solution_hint = ""
                row.decision_note = "approved_and_filled"
                _set_state(row, "FILLED")
                return row
        _apply_order_precheck_failed(row, reason_codes=[str(exc)])
        return row

    row.order_position_id = released_intent.position_id
    row.status = "filled"
    row.execution_eligible = True
    row.blocked_reason_code = ""
    row.blocked_reason_message = ""
    row.blocked_solution_hint = ""
    row.decision_note = "approved_and_filled"
    _set_state(row, "FILLED")
    return row


def get_or_create_signal_mode(db: Session, user_id: str) -> UserSignalMode:
    _ensure_scanner_tables(db)

    row = db.query(UserSignalMode).filter(UserSignalMode.user_id == user_id).first()
    if row:
        return row

    default_mode = "AUTO" if _has_active_bot(db, user_id) else DEFAULT_SIGNAL_MODE
    row = UserSignalMode(id=str(uuid.uuid4()), user_id=user_id, mode=default_mode)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_signal_mode(db: Session, user_id: str, mode: str) -> UserSignalMode:
    row = get_or_create_signal_mode(db, user_id)
    row.mode = _normalize_mode(mode)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def list_user_scanner_results(db: Session, user_id: str, limit: int = 100) -> list[UserScannerResult]:
    return (
        db.query(UserScannerResult)
        .filter(UserScannerResult.user_id == user_id)
        .order_by(UserScannerResult.generated_at.desc())
        .limit(limit)
        .all()
    )


def list_user_signals(
    db: Session,
    user_id: str,
    limit: int = 100,
    *,
    refresh_snapshot: bool = True,
) -> list[PendingSignal]:
    rows = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id)
        .order_by(PendingSignal.created_at.desc())
        .limit(limit)
        .all()
    )

    signal_ids = [row.signal_id for row in rows if row.signal_id]
    signal_rows = (
        db.query(SignalEvent.id, SignalEvent.market_type)
        .filter(SignalEvent.id.in_(signal_ids))
        .all()
        if signal_ids
        else []
    )
    signal_market_type_map = {str(signal_id): str(market_type or "spot").lower() for signal_id, market_type in signal_rows}

    mutated = False
    for row in rows:
        row.market_type = signal_market_type_map.get(str(row.signal_id), "spot")
        if refresh_snapshot and row.status not in {"rejected", "filled"}:
            before = (
                row.status,
                row.current_state,
                row.blocked_reason_code,
                row.execution_eligible,
                row.requires_manual_approval,
            )
            _refresh_pending_signal_snapshot(db, row)
            after = (
                row.status,
                row.current_state,
                row.blocked_reason_code,
                row.execution_eligible,
                row.requires_manual_approval,
            )
            if before != after:
                mutated = True
        row.execution_mode_label = _execution_mode_label(row.mode)

    if refresh_snapshot and mutated:
        db.commit()
        for row in rows:
            db.refresh(row)
            row.execution_mode_label = _execution_mode_label(row.mode)
    return rows


def run_user_scanner(
    db: Session,
    user_id: str,
    *,
    requested_mode: str | None = None,
    max_results: int = 20,
    symbol_source: str = "crypto",
    market_type: str = "all",
    selected_symbols: list[str] | None = None,
    symbol_selection_mode: str = "all_market_symbols",
) -> dict:
    cycle_started = perf_counter()
    run_id = str(uuid.uuid4())
    _ensure_scanner_tables(db)
    mode_row = get_or_create_signal_mode(db, user_id)
    mode = _normalize_mode(requested_mode or mode_row.mode)
    warning_set: set[str] = set()

    if mode != "AUTO" and _has_active_bot(db, user_id):
        mode = "AUTO"
        warning_set.add("signal_mode_auto_enforced_for_active_bot")

    if mode_row.mode != mode:
        mode_row.mode = mode
        mode_row.updated_at = datetime.now(timezone.utc)

    queue_state = get_json(redis_client, "scanner:queue:state") or {}
    queue_backlog = int(queue_state.get("depth") or 0)
    latest_global_perf = get_json(redis_client, "scanner:perf:latest:global") or {}

    normalized_selection_mode = _normalize_symbol_selection_mode(symbol_selection_mode)
    normalized_market_type = _normalize_scanner_market_type(market_type)
    latest_cycle_latency = float(latest_global_perf.get("cycle_duration_ms") or queue_state.get("cycle_latency_ms") or 0)
    latest_stale_blocks = float(latest_global_perf.get("stale_block_count") or queue_state.get("stale_blocks") or 0)
    latest_symbols_eval = float(latest_global_perf.get("symbols_evaluated") or 0)
    stale_rate = latest_stale_blocks / max(latest_symbols_eval, 1.0)

    fallback_resolution = resolve_fallback_mode(
        redis_client,
        requested_mode=normalized_selection_mode,
        queue_backlog=queue_backlog,
        cycle_latency_ms=latest_cycle_latency,
        stale_rate=stale_rate,
    )
    effective_selection_mode = str(fallback_resolution.get("effective_mode") or normalized_selection_mode)
    overload_fallback_applied = bool(fallback_resolution.get("overload_fallback_applied"))
    fallback_trigger_metric = fallback_resolution.get("trigger_metric")
    fallback_threshold_breach = fallback_resolution.get("threshold_breach") or {}
    fallback_exit_reason = fallback_resolution.get("exit_reason")
    fallback_state = fallback_resolution.get("state") or {}

    if overload_fallback_applied:
        warning_set.add("auto_top_volume_fallback_enabled")
    if fallback_resolution.get("transition_event") == "trigger":
        warning_set.add("fallback_triggered")
    elif fallback_resolution.get("transition_event") == "exit":
        warning_set.add("fallback_exited")

    if fallback_resolution.get("transition_event") in {"trigger", "exit"}:
        record_fallback_event(
            db,
            run_id=run_id,
            event_type=str(fallback_resolution.get("transition_event")),
            requested_mode=normalized_selection_mode,
            effective_mode=effective_selection_mode,
            trigger_metric=fallback_trigger_metric,
            threshold_breach=fallback_threshold_breach,
            exit_reason=fallback_exit_reason,
            cycle_snapshot={
                "queue_backlog": queue_backlog,
                "cycle_latency_ms": latest_cycle_latency,
                "stale_rate": stale_rate,
                "symbols_evaluated": latest_symbols_eval,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    universe_payload = build_effective_universe(db, redis_client)
    spot_scope = filter_allowed_quote_symbols([str(item).upper() for item in (universe_payload.get("spot_symbols") or [])])
    futures_scope = filter_allowed_quote_symbols([str(item).upper() for item in (universe_payload.get("futures_symbols") or [])])
    if normalized_market_type == "futures":
        market_scope = futures_scope
    elif normalized_market_type == "spot":
        market_scope = spot_scope
    else:
        market_scope = list(dict.fromkeys([*spot_scope, *futures_scope]))
    advisory_lookup = {
        **((universe_payload.get("liquidity_advisory") or {}).get("spot") or {}),
        **((universe_payload.get("liquidity_advisory") or {}).get("futures") or {}),
    }
    volume_lookup = {
        symbol: float((advisory_lookup.get(symbol) or {}).get("quote_volume") or 0)
        for symbol in market_scope
    }
    engine_version = "canonical-engine.v3"
    schema_version = "decision-card.v1"
    scoped_symbols = _user_symbols_scope(db, user_id)
    normalized_selected_symbols = filter_allowed_quote_symbols(
        [str(item).strip().upper() for item in (selected_symbols or []) if str(item).strip()]
    )
    open_symbols = {
        str(item.symbol or "").upper()
        for item in db.query(PaperPosition).filter(PaperPosition.user_id == user_id, PaperPosition.status == "open").all()
        if item.symbol
    }
    hints_payload = get_json(redis_client, "scanner:event-hints") or {}
    event_hints = {
        str(item).upper()
        for item in (hints_payload.get("symbols") or [])
        if str(item).strip()
    }
    for item in (hints_payload.get("items") or []):
        symbol_hint = str(item.get("symbol") or "").upper().strip()
        if not symbol_hint:
            continue
        score_hint = float(item.get("score") or 0)
        reasons_hint = [str(reason) for reason in (item.get("reasons") or [])]
        if score_hint >= 1.5 or any(reason in {"volume_spike", "spread_jump", "position_activity"} for reason in reasons_hint):
            event_hints.add(symbol_hint)

    if str(symbol_source or "crypto").lower() != "crypto":
        warning_set.add("scanner_currently_supports_crypto_only")
        scanner_scope: list[str] = []
    else:
        manual_scope = normalized_selected_symbols
        if normalized_selection_mode == "manual_selection" and not manual_scope and scoped_symbols:
            manual_scope = sorted(scoped_symbols)

        scanner_scope = apply_scanner_mode(
            market_scope,
            mode=effective_selection_mode,
            selected_symbols=manual_scope,
            top_n=max(max_results, 120),
            volume_map=volume_lookup,
        )

    candidate_tiers = {
        "candidate_high": [],
        "candidate_medium": [],
        "candidate_low": [],
        "ignore_for_now": [],
        "decision_scope": [],
    }
    rollout_state = get_rollout_state(db)
    rollout_stage = str(rollout_state.current_stage or "top_volume_subset")
    dropped_symbol_count = 0
    duplicate_suppressed_count = 0
    acquired_symbol_locks: list[str] = []

    if scanner_scope:
        candidate_tiers = _build_candidate_tiers(
            user_open_symbols=open_symbols,
            scanner_scope=scanner_scope,
            advisory_lookup=advisory_lookup,
            volume_lookup=volume_lookup,
            event_hints=event_hints,
            normalized_selection_mode=effective_selection_mode,
        )
        decision_scope_raw = candidate_tiers.get("decision_scope") or []
        decision_scope: list[str] = []

        if effective_selection_mode != "manual_selection":
            if rollout_stage == "top_volume_subset":
                decision_scope_raw = decision_scope_raw[:60]
            elif rollout_stage == "mid_segment":
                decision_scope_raw = decision_scope_raw[:160]

        for symbol in decision_scope_raw:
            lock_key = f"scanner:symbol:lock:{symbol}"
            lock_acquired = _acquire_symbol_lock(lock_key, run_id, ttl_seconds=90)
            if lock_acquired:
                acquired_symbol_locks.append(lock_key)
                decision_scope.append(symbol)
            else:
                duplicate_suppressed_count += 1

        dropped_symbol_count = max(0, len(scanner_scope) - len(decision_scope))
        dropped_symbol_count += duplicate_suppressed_count
        if dropped_symbol_count > 0:
            warning_set.add("low_priority_symbols_deferred")
        if duplicate_suppressed_count > 0:
            warning_set.add("same_symbol_duplicate_suppressed")

        try:
            payload = scan_canonical_universe_for_signals(
                db,
                redis_client,
                max_symbols=max(len(decision_scope), max_results, 30),
                symbols_override=decision_scope,
            )
            ranked = payload.get("top_ranked", [])
            engine_version = str(payload.get("engine_version") or "canonical-engine.v3")
            schema_version = str(payload.get("schema_version") or "decision-card.v1")
            scan_performance = payload.get("performance") or {}
        finally:
            for key in acquired_symbol_locks:
                _release_symbol_lock(key)
    else:
        ranked = []
        scan_performance = {}

    selected = ranked[:max_results]
    selected_symbols = [str(item.get("symbol") or "").upper() for item in selected if str(item.get("symbol") or "").strip()]

    fallback_seed_symbols = normalized_selected_symbols[:max_results]
    if len(fallback_seed_symbols) == 0:
        fallback_seed_symbols = [str(symbol).upper() for symbol in (market_scope or []) if str(symbol).strip()][:max_results]

    if len(selected) == 0 and len(fallback_seed_symbols) > 0:
        fallback_symbols = fallback_seed_symbols
        selected = []
        for index, symbol in enumerate(fallback_symbols):
            fallback_signal = "long" if index % 2 == 0 else "short"
            selected.append(
                {
                    "symbol": symbol,
                    "strategy_code": "manual_selection_fallback",
                    "signal": fallback_signal,
                    "final_decision": "LONG" if fallback_signal == "long" else "SHORT",
                    "signal_strength": 0.62,
                    "signal_score": 62.0,
                    "reason_codes": ["manual_selection_fallback"],
                    "source_strategies": [
                        {
                            "strategy_code": "manual_selection_fallback",
                            "signal": fallback_signal,
                            "score": 62.0,
                            "status": "accepted",
                        }
                    ],
                }
            )
        selected_symbols = fallback_symbols
        warning_set.add("manual_selection_fallback_used")

    db.query(UserScannerResult).filter(UserScannerResult.user_id == user_id).delete()

    bot_market_type = normalized_market_type
    if normalized_market_type == "all":
        default_connection = _resolve_default_exchange_connection(db, user_id)
        bot_market_type = _normalize_scanner_market_type(getattr(default_connection, "market_type", None))
        if bot_market_type == "all":
            bot_market_type = "spot"

    bot = _default_bot_for_user(db, user_id, selected_symbols, bot_market_type)
    actionable_count = 0
    queued_count = 0
    symbol_direction_seen: dict[str, str] = {}
    stale_evaluation_count = 0
    stale_block_count = 0
    snapshot_age_total = 0.0
    snapshot_age_count = 0

    candidate_high_set = set(candidate_tiers.get("candidate_high") or [])
    candidate_medium_set = set(candidate_tiers.get("candidate_medium") or [])
    candidate_low_set = set(candidate_tiers.get("candidate_low") or [])
    ignore_set = set(candidate_tiers.get("ignore_for_now") or [])
    explainability_degrade = queue_backlog > 20

    risk_policy_row = db.query(RiskOrchestratorPolicy).filter(RiskOrchestratorPolicy.id == "global").first()
    reference_equity = float(risk_policy_row.reference_equity_usd) if risk_policy_row else 10000.0
    risk_per_trade_pct = float(GLOBAL_RISK_POLICY.get("risk_per_trade_pct", 1.5))
    per_trade_notional_cap = max(10.0, round(reference_equity * (risk_per_trade_pct / 100), 4))
    max_positions = min(3, int(GLOBAL_RISK_POLICY.get("max_positions", 5)))
    ignore_position_limit = str(os.getenv("LIVE_SCANNER_IGNORE_POSITION_LIMIT", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    cooldown_seconds = int(GLOBAL_RISK_POLICY.get("cooldown_symbol_seconds", 21600))

    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    closed_today_rows = (
        db.query(PaperPosition)
        .filter(
            PaperPosition.user_id == user_id,
            PaperPosition.status == "closed",
            PaperPosition.closed_at.isnot(None),
            PaperPosition.closed_at >= day_start,
        )
        .all()
    )
    realized_today = sum(float(row.realized_pnl or 0) for row in closed_today_rows)
    daily_loss_pct = max(0.0, (-realized_today / max(reference_equity, 1.0)) * 100)
    daily_loss_limit_pct = 1.0
    daily_loss_guard_blocked = daily_loss_pct >= daily_loss_limit_pct
    if daily_loss_guard_blocked:
        warning_set.add("daily_loss_limit_reached")

    open_positions_count = len(open_symbols)
    cooldown_since = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    recent_rows = (
        db.query(PendingSignal)
        .filter(
            PendingSignal.user_id == user_id,
            PendingSignal.created_at >= cooldown_since,
            PendingSignal.status.in_(["pending", "sent", "approved", "filled", "risk_blocked"]),
        )
        .all()
    )
    recent_signal_ids = [row.signal_id for row in recent_rows if row.signal_id]
    recent_signal_market_rows = (
        db.query(SignalEvent.id, SignalEvent.market_type)
        .filter(SignalEvent.id.in_(recent_signal_ids))
        .all()
        if recent_signal_ids
        else []
    )
    recent_signal_market_map = {
        str(signal_id): _normalize_scanner_market_type(market_type) for signal_id, market_type in recent_signal_market_rows
    }
    cooldown_symbols = {
        (
            str(row.symbol or "").upper(),
            recent_signal_market_map.get(str(row.signal_id), "spot"),
        )
        for row in recent_rows
        if row.symbol
    }

    runtime_strategy_code = str(getattr(bot, "strategy_type", "") or "").strip().lower()

    for item in selected:
        signal_value = str(item.get("signal", "none") or "none").lower()
        final_decision = str(item.get("final_decision") or ("LONG" if signal_value == "long" else "SHORT" if signal_value == "short" else "NO_TRADE")).upper()
        reason_codes = item.get("reason_codes") or []
        confidence = float(item.get("signal_strength") or 0)
        score = float(item.get("signal_score") or 0)
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            warning_set.add("symbol_missing_rejected")
            continue
        quote_asset = extract_quote_asset(symbol)
        if quote_asset is None:
            warning_set.add("invalid_quote_asset")
            continue
        strategy_code = str(item.get("strategy_code") or "canonical_unknown")
        normalized_strategy_code = strategy_code.strip().lower()
        if runtime_strategy_code and normalized_strategy_code in {"", "manual_selection_fallback", "canonical_unknown"}:
            strategy_code = runtime_strategy_code
            item = {
                **item,
                "strategy_code": runtime_strategy_code,
                "source_strategies": [
                    {
                        "strategy_code": runtime_strategy_code,
                        "signal": signal_value,
                        "score": float(item.get("signal_score") or 0),
                        "status": "accepted",
                    }
                ],
            }
        snapshot_age_sec = item.get("indicator_snapshot_age_sec")
        if snapshot_age_sec is None:
            snapshot_age_sec = _snapshot_age_seconds(symbol, "15m")
        if snapshot_age_sec is not None:
            snapshot_age_total += float(snapshot_age_sec)
            snapshot_age_count += 1

        freshness_threshold = _freshness_threshold_for_timeframe("15m")
        if _is_stale_snapshot(snapshot_age_sec, "15m"):
            stale_evaluation_count += 1
            stale_block_count += 1
            warning_set.add("stale_data_block")
            signal_value = "none"
            final_decision = "BLOCKED"
            reason_codes = list(dict.fromkeys([*(reason_codes or []), "stale_data_block", "data_unavailable"]))
            item = {
                **item,
                "final_decision": "BLOCKED",
                "signal": "none",
                "blocked_reason_current": "STALE_DATA_BLOCK",
                "risk_state": {"state": "blocked", "reason": "stale_data_block"},
                "cooldown_state": {"state": "clear"},
            }

        if daily_loss_guard_blocked:
            signal_value = "none"
            final_decision = "BLOCKED"
            reason_codes = list(dict.fromkeys([*(reason_codes or []), "daily_loss_limit_reached"]))

        candidate_class = "ignore_for_now"
        if symbol in candidate_high_set:
            candidate_class = "candidate_high"
        elif symbol in candidate_medium_set:
            candidate_class = "candidate_medium"
        elif symbol in candidate_low_set:
            candidate_class = "candidate_low"
        elif symbol in ignore_set:
            candidate_class = "ignore_for_now"

        row_payload = {
            **item,
            "quote_asset": quote_asset,
            "final_decision": final_decision,
            "schema_version": schema_version,
            "engine_version": engine_version,
            "indicator_snapshot_age_sec": snapshot_age_sec,
            "freshness_sla_seconds": freshness_threshold,
            "candidate_class": candidate_class,
            "explainability_degraded": explainability_degrade,
        }
        if explainability_degrade:
            row_payload["source_strategies"] = list((row_payload.get("source_strategies") or [])[:3])
            row_payload["blocked_reason_timeline"] = []
            row_payload["explanation_templates"] = list((row_payload.get("explanation_templates") or [])[:2])

        scanner_row = UserScannerResult(
            id=str(uuid.uuid4()),
            run_id=run_id,
            user_id=user_id,
            symbol=symbol,
            strategy_code=strategy_code,
            signal=signal_value,
            confidence=confidence,
            signal_score=score,
            reason_codes=reason_codes,
            payload=row_payload,
        )
        db.add(scanner_row)
        db.flush()

        record_decision_trace(
            db,
            user_id=user_id,
            trace_scope="signal",
            trace_type="symbol_decision_evaluated",
            entity_id=scanner_row.id,
            strategy_code=strategy_code,
            decision_status=final_decision,
            reason_codes=reason_codes or ["decision_evaluated"],
            feature_snapshot={
                "layer": "signal",
                "previous_state": "ANALYZED",
                "new_state": final_decision,
                "long_score": float(item.get("long_score") or 0),
                "short_score": float(item.get("short_score") or 0),
            },
            context_payload={
                "symbol": symbol,
                "run_id": run_id,
                "schema_version": schema_version,
                "engine_version": engine_version,
            },
        )

        gating_reason = next(
            (
                code
                for code in (reason_codes or [])
                if code
                in {
                    "regime_mismatch",
                    "breakout_condition_missing",
                    "pullback_trend_unclear",
                    "reversal_extra_confirmation_required",
                    "long_threshold_not_met",
                    "short_threshold_not_met",
                    "conflict_score_exceeded",
                    "family_disabled",
                    "family_gate_missing",
                }
            ),
            None,
        )
        if gating_reason is not None:
            record_decision_trace(
                db,
                user_id=user_id,
                trace_scope="signal",
                trace_type="family_gate_evaluated",
                entity_id=scanner_row.id,
                strategy_code=strategy_code,
                decision_status="BLOCKED" if final_decision == "BLOCKED" else final_decision,
                reason_codes=[gating_reason],
                feature_snapshot={"layer": "gating", "previous_state": "SCORED", "new_state": final_decision},
                context_payload={"symbol": symbol, "run_id": run_id},
            )

        if signal_value == "none":
            continue

        existing_direction = symbol_direction_seen.get(symbol)
        if existing_direction and existing_direction != signal_value:
            warning_set.add("symbol_direction_conflict_blocked")
            blocked_sources = [
                {**src, "status": "blocked" if src.get("status") == "accepted" else src.get("status")}
                for src in (scanner_row.payload or {}).get("source_strategies", [])
            ]
            scanner_row.payload = {
                **(scanner_row.payload or {}),
                "final_decision": "BLOCKED",
                "blocked_reason_current": "SYMBOL_DIRECTION_CONFLICT",
                "risk_state": {"state": "blocked", "reason": "symbol_direction_conflict"},
                "source_strategies": blocked_sources,
            }
            scanner_row.reason_codes = list(dict.fromkeys([*(scanner_row.reason_codes or []), "symbol_direction_conflict"]))
            record_decision_trace(
                db,
                user_id=user_id,
                trace_scope="signal",
                trace_type="risk_block",
                entity_id=scanner_row.id,
                strategy_code=strategy_code,
                decision_status="BLOCKED",
                reason_codes=["symbol_direction_conflict"],
                feature_snapshot={"layer": "risk", "previous_state": final_decision, "new_state": "BLOCKED"},
                context_payload={"symbol": symbol, "run_id": run_id},
            )
            continue

        if (symbol, bot_market_type) in cooldown_symbols:
            warning_set.add("symbol_cooldown_active")
            blocked_sources = [
                {**src, "status": "blocked" if src.get("status") == "accepted" else src.get("status")}
                for src in (scanner_row.payload or {}).get("source_strategies", [])
            ]
            scanner_row.payload = {
                **(scanner_row.payload or {}),
                "final_decision": "BLOCKED",
                "blocked_reason_current": "SYMBOL_COOLDOWN",
                "cooldown_state": {"state": "blocked", "reason": "symbol_cooldown", "seconds": cooldown_seconds},
                "source_strategies": blocked_sources,
            }
            scanner_row.reason_codes = list(dict.fromkeys([*(scanner_row.reason_codes or []), "symbol_cooldown"]))
            record_decision_trace(
                db,
                user_id=user_id,
                trace_scope="signal",
                trace_type="risk_block",
                entity_id=scanner_row.id,
                strategy_code=strategy_code,
                decision_status="BLOCKED",
                reason_codes=["symbol_cooldown"],
                feature_snapshot={"layer": "risk", "previous_state": final_decision, "new_state": "BLOCKED"},
                context_payload={"symbol": symbol, "run_id": run_id},
            )
            continue

        if (not ignore_position_limit) and (open_positions_count + queued_count >= max_positions):
            warning_set.add("max_positions_reached")
            blocked_sources = [
                {**src, "status": "blocked" if src.get("status") == "accepted" else src.get("status")}
                for src in (scanner_row.payload or {}).get("source_strategies", [])
            ]
            scanner_row.payload = {
                **(scanner_row.payload or {}),
                "final_decision": "BLOCKED",
                "blocked_reason_current": "MAX_POSITIONS_REACHED",
                "risk_state": {"state": "blocked", "reason": "max_positions_reached", "max_positions": max_positions},
                "source_strategies": blocked_sources,
            }
            scanner_row.reason_codes = list(dict.fromkeys([*(scanner_row.reason_codes or []), "max_positions_reached"]))
            record_decision_trace(
                db,
                user_id=user_id,
                trace_scope="signal",
                trace_type="risk_block",
                entity_id=scanner_row.id,
                strategy_code=strategy_code,
                decision_status="BLOCKED",
                reason_codes=["max_positions_reached"],
                feature_snapshot={"layer": "risk", "previous_state": final_decision, "new_state": "BLOCKED"},
                context_payload={"symbol": symbol, "run_id": run_id},
            )
            continue

        symbol_direction_seen[symbol] = signal_value

        requested_notional = min(max(10.0, round(score, 4)), per_trade_notional_cap)
        meta_summary = run_meta_strategy_engine(
            db,
            user_id=user_id,
            strategy_id=strategy_code,
            symbol=symbol,
            signal_confidence=max(confidence, round(score / 100, 4)),
            requested_notional=requested_notional,
        )
        meta_decision = str(meta_summary.get("meta_engine_decision") or "ALLOW")
        allocation_source = str(meta_summary.get("allocation_source") or "weight_based")
        strategy_weight = float(meta_summary.get("strategy_weight") or 1.0)
        allocation_reason = str(meta_summary.get("strategy_allocation_reason") or "normal_allocation")

        actionable_count += 1
        signal_event = SignalEvent(
            id=str(uuid.uuid4()),
            bot_profile_id=bot.id,
            user_id=user_id,
            symbol=symbol,
            market_type=bot_market_type,
            timeframe=bot.timeframe,
            strategy_id=strategy_code,
            signal=signal_value,
            direction="long" if signal_value == "long" else "short",
            confidence=max(confidence, round(score / 100, 4)),
            reason_codes=reason_codes,
        )
        db.add(signal_event)
        db.flush()

        pending_row = PendingSignal(
            id=str(uuid.uuid4()),
            signal_id=signal_event.id,
            user_id=user_id,
            symbol=symbol,
            strategy_code=strategy_code,
            confidence=signal_event.confidence,
            mode=mode,
            status="pending",
            strategy_weight=strategy_weight,
            allocation_source=allocation_source,
            meta_engine_decision=meta_decision,
            previous_state="DETECTED",
            current_state="DETECTED",
            bot_profile_id=bot.id,
            runtime_owner=bot.name,
            created_at=datetime.now(timezone.utc),
            decision_note=allocation_reason if meta_decision != "ALLOW" else "",
        )
        db.add(pending_row)
        db.flush()

        _refresh_pending_signal_snapshot(db, pending_row)
        pending_row.execution_mode_label = _execution_mode_label(mode)

        if pending_row.status == "pending":
            queued_count += 1

        if mode == "AUTO" and pending_row.execution_eligible:
            try:
                connection = _resolve_default_exchange_connection(db, user_id)
                _dispatch_signal_to_execution(
                    db,
                    row=pending_row,
                    signal=signal_event,
                    exchange_connection=connection,
                    actor_user_id=user_id,
                )
            except Exception as exc:
                _apply_order_precheck_failed(pending_row, error_detail=str(exc))

        record_decision_trace(
            db,
            user_id=user_id,
            trace_scope="signal",
            trace_type="scanner_signal_generated",
            entity_id=pending_row.id,
            strategy_code=strategy_code,
            decision_status=pending_row.current_state,
            reason_codes=[pending_row.blocked_reason_code] if pending_row.blocked_reason_code else (reason_codes or ["signal_generated_without_reason_code"]),
            strategy_allocation_reason=allocation_reason,
            meta_engine_decision=meta_decision,
            feature_snapshot={
                "confidence": float(signal_event.confidence or 0),
                "signal_score": score,
                "mode": mode,
                "signal": signal_value,
                "strategy_weight": strategy_weight,
                "execution_eligible": pending_row.execution_eligible,
            },
            context_payload={
                "run_id": run_id,
                "symbol": symbol,
                "signal_event_id": signal_event.id,
                "pending_status": pending_row.status,
                "current_state": pending_row.current_state,
                "allocation_source": allocation_source,
                "meta_strategy_summary": meta_summary,
                "requires_manual_approval": pending_row.requires_manual_approval,
            },
        )

    if actionable_count == 0 and selected:
        warning_set.add("no_actionable_signal_generated")

    cycle_duration_ms = round((perf_counter() - cycle_started) * 1000, 4)
    avg_snapshot_age_sec = round(snapshot_age_total / max(snapshot_age_count, 1), 4) if snapshot_age_count > 0 else None
    symbols_evaluated = int(scan_performance.get("symbols_evaluated") or len(candidate_tiers.get("decision_scope") or []))
    avg_symbol_eval_ms = float(scan_performance.get("avg_symbol_eval_ms") or (cycle_duration_ms / max(symbols_evaluated, 1)))
    top_slow_symbols = list(scan_performance.get("top_slow_symbols") or [])
    top_slow_strategies = list(scan_performance.get("top_slow_strategies") or [])

    scanner_perf_payload = {
        "schema_version": "scanner-perf.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "run_id": run_id,
        "total_active_symbols": len(scanner_scope),
        "decision_scope_symbols": len(candidate_tiers.get("decision_scope") or []),
        "candidate_high": len(candidate_tiers.get("candidate_high") or []),
        "candidate_medium": len(candidate_tiers.get("candidate_medium") or []),
        "candidate_low": len(candidate_tiers.get("candidate_low") or []),
        "ignore_for_now": len(candidate_tiers.get("ignore_for_now") or []),
        "cycle_duration_ms": cycle_duration_ms,
        "symbols_evaluated": symbols_evaluated,
        "avg_symbol_eval_ms": round(avg_symbol_eval_ms, 4),
        "snapshot_age_avg_sec": avg_snapshot_age_sec,
        "queue_backlog": queue_backlog,
        "dropped_symbol_count": int(dropped_symbol_count),
        "same_symbol_duplicate_suppression": int(duplicate_suppressed_count),
        "stale_evaluation_count": int(stale_evaluation_count),
        "stale_block_count": int(stale_block_count),
        "max_positions_guard": int(max_positions),
        "daily_loss_limit_pct": float(daily_loss_limit_pct),
        "daily_loss_pct": round(float(daily_loss_pct), 6),
        "daily_loss_guard_blocked": bool(daily_loss_guard_blocked),
        "freshness_sla_seconds": FRESHNESS_SLA_SECONDS,
        "backpressure_mode": "low_priority_defer + stale_drop + explainability_degrade",
        "requested_selection_mode": normalized_selection_mode,
        "market_type": bot_market_type,
        "effective_selection_mode": effective_selection_mode,
        "overload_fallback_applied": overload_fallback_applied,
        "fallback_trigger_metric": fallback_trigger_metric,
        "fallback_threshold_breach": fallback_threshold_breach,
        "fallback_exit_reason": fallback_exit_reason,
        "fallback_state": fallback_state,
        "rollout_stage": rollout_stage,
        "top_slow_symbols": top_slow_symbols,
        "top_slow_strategies": top_slow_strategies,
    }
    set_json(redis_client, f"scanner:perf:latest:{user_id}", scanner_perf_payload)
    set_json(redis_client, "scanner:perf:latest:global", scanner_perf_payload)
    if stale_block_count > 0:
        incr_counter(redis_client, "scanner:metrics:stale_blocks:day", stale_block_count)
    if dropped_symbol_count > 0:
        incr_counter(redis_client, "scanner:metrics:dropped_symbols:day", dropped_symbol_count)
    record_scanner_perf_snapshot(db, user_id=user_id, run_id=run_id, metrics=scanner_perf_payload)

    db.commit()
    pending_total = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id, PendingSignal.status == "pending")
        .count()
    )
    return {
        "run_id": run_id,
        "mode": mode,
        "market_type": bot_market_type,
        "result_count": len(selected),
        "actionable_count": actionable_count,
        "queued_count": queued_count,
        "pending_total": pending_total,
        "generated_at": datetime.now(timezone.utc),
        "selected_symbols": selected_symbols,
        "warnings": sorted(warning_set),
        "scanner_perf": scanner_perf_payload,
    }


def approve_pending_signal(db: Session, user_id: str, pending_signal_id: str, note: str = "") -> PendingSignal:
    row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == pending_signal_id, PendingSignal.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("pending_signal_not_found")
    if row.status not in {"pending", "ready", "blocked"}:
        raise ValueError("pending_signal_not_actionable")

    signal = db.query(SignalEvent).filter(SignalEvent.id == row.signal_id, SignalEvent.user_id == user_id).first()
    if signal is None:
        raise ValueError("signal_event_not_found")

    _refresh_pending_signal_snapshot(db, row)
    if row.blocked_reason_code and row.blocked_reason_code not in {"MANUAL_APPROVAL_REQUIRED", ""}:
        raise ValueError(f"signal_blocked:{row.blocked_reason_code}")

    decision_note = note or "approved"
    row.decision_note = decision_note
    row.decided_at = datetime.now(timezone.utc)

    exchange_connection = _resolve_default_exchange_connection(db, user_id)
    _dispatch_signal_to_execution(
        db,
        row=row,
        signal=signal,
        exchange_connection=exchange_connection,
        actor_user_id=user_id,
    )

    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="signal",
        trace_type="user_signal_decision",
        entity_id=row.id,
        strategy_code=row.strategy_code,
        decision_status="APPROVED",
        reason_codes=["user_signal_approved"],
        strategy_allocation_reason=row.decision_note or "user_signal_approved",
        meta_engine_decision=row.meta_engine_decision,
        feature_snapshot={
            "confidence": float(row.confidence or 0),
            "mode": row.mode,
            "decision_note": decision_note,
            "strategy_weight": float(row.strategy_weight or 1),
            "execution_eligible": row.execution_eligible,
            "current_state": row.current_state,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "position_id": row.order_position_id,
            "symbol": row.symbol,
            "allocation_source": row.allocation_source,
            "meta_engine_decision": row.meta_engine_decision,
            "created_order_intent_id": row.created_order_intent_id,
            "blocked_reason_code": row.blocked_reason_code,
        },
    )

    if row.order_position_id:
        position = db.query(PaperPosition).filter(PaperPosition.id == row.order_position_id).first()
        if position is not None:
            record_decision_trace(
                db,
                user_id=user_id,
                trace_scope="trade",
                trace_type="trade_opened_from_signal",
                entity_id=position.id,
                strategy_code=row.strategy_code,
                decision_status="OPENED",
                reason_codes=["trade_opened_from_signal"],
                strategy_allocation_reason=row.decision_note or "trade_opened_from_signal",
                meta_engine_decision=row.meta_engine_decision,
                feature_snapshot={
                    "entry_price": float(position.entry_price or 0),
                    "quantity": float(position.quantity or 0),
                    "side": position.side,
                    "strategy_weight": float(row.strategy_weight or 1),
                },
                context_payload={
                    "pending_signal_id": row.id,
                    "signal_id": row.signal_id,
                    "symbol": row.symbol,
                    "allocation_source": row.allocation_source,
                    "meta_engine_decision": row.meta_engine_decision,
                    "created_order_intent_id": row.created_order_intent_id,
                },
            )

    db.commit()
    db.refresh(row)
    row.execution_mode_label = _execution_mode_label(row.mode)
    return row


def reject_pending_signal(db: Session, user_id: str, pending_signal_id: str, note: str = "") -> PendingSignal:
    row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == pending_signal_id, PendingSignal.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("pending_signal_not_found")
    if row.status not in {"pending", "ready", "blocked"}:
        raise ValueError("pending_signal_not_actionable")

    _refresh_pending_signal_snapshot(db, row)
    decision_note = note or "rejected"
    row.status = "rejected"
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = decision_note
    _set_state(row, "REJECTED")

    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="signal",
        trace_type="user_signal_decision",
        entity_id=row.id,
        strategy_code=row.strategy_code,
        decision_status="REJECTED",
        reason_codes=["user_signal_rejected"],
        strategy_allocation_reason=decision_note,
        meta_engine_decision=row.meta_engine_decision,
        feature_snapshot={
            "confidence": float(row.confidence or 0),
            "mode": row.mode,
            "decision_note": decision_note,
            "strategy_weight": float(row.strategy_weight or 1),
            "blocked_reason_code": row.blocked_reason_code,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "symbol": row.symbol,
            "allocation_source": row.allocation_source,
            "meta_engine_decision": row.meta_engine_decision,
            "current_state": row.current_state,
        },
    )

    db.commit()
    db.refresh(row)
    row.execution_mode_label = _execution_mode_label(row.mode)
    return row


def diagnose_pending_signal(
    db: Session,
    user_id: str,
    pending_signal_id: str,
    auto_fix: bool = False,
) -> tuple[PendingSignal, list[str]]:
    row = (
        db.query(PendingSignal)
        .filter(PendingSignal.id == pending_signal_id, PendingSignal.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("pending_signal_not_found")

    actions_applied: list[str] = []
    _refresh_pending_signal_snapshot(db, row)

    if auto_fix and row.blocked_reason_code == "BOT_NOT_RUNNING" and row.bot_profile_id:
        bot = db.query(BotProfile).filter(BotProfile.id == row.bot_profile_id, BotProfile.is_deleted.is_(False)).first()
        if bot is not None and not bool(bot.is_running):
            bot.is_running = True
            bot.updated_at = datetime.now(timezone.utc)
            actions_applied.append("bot_runtime_started")

    if auto_fix and row.blocked_reason_code == "SYMBOL_NOT_ALLOWED" and row.bot_profile_id:
        bot = db.query(BotProfile).filter(BotProfile.id == row.bot_profile_id, BotProfile.is_deleted.is_(False)).first()
        if bot is not None:
            existing = [item.upper() for item in (bot.symbols or []) if item]
            symbol = str(row.symbol or "").upper()
            if symbol and symbol not in existing:
                bot.symbols = [*existing, symbol][:40]
                bot.updated_at = datetime.now(timezone.utc)
                actions_applied.append("symbol_added_to_bot_scope")

    if auto_fix and row.blocked_reason_code == "RISK_POLICY_MISSING":
        _, created = ensure_user_safe_default_risk_policy(db, row.user_id, commit=False)
        if created:
            actions_applied.append("safe_default_risk_policy_created")

    if auto_fix and row.blocked_reason_code == "MANUAL_APPROVAL_REQUIRED" and _has_active_bot(db, row.user_id):
        if row.mode != "AUTO":
            row.mode = "AUTO"
            actions_applied.append("signal_mode_switched_to_auto")

    if actions_applied:
        db.flush()

    _refresh_pending_signal_snapshot(db, row)

    if auto_fix and row.mode == "AUTO" and row.execution_eligible and row.status in {"pending", "ready", "blocked"}:
        signal = db.query(SignalEvent).filter(SignalEvent.id == row.signal_id, SignalEvent.user_id == row.user_id).first()
        if signal is not None:
            try:
                exchange_connection = _resolve_default_exchange_connection(db, user_id)
                _dispatch_signal_to_execution(
                    db,
                    row=row,
                    signal=signal,
                    exchange_connection=exchange_connection,
                    actor_user_id=user_id,
                )
                actions_applied.append("auto_dispatch_triggered")
            except Exception as exc:
                _apply_order_precheck_failed(row, error_detail=str(exc))
                actions_applied.append("auto_dispatch_precheck_failed")
    record_decision_trace(
        db,
        user_id=user_id,
        trace_scope="signal",
        trace_type="signal_runtime_diagnose",
        entity_id=row.id,
        strategy_code=row.strategy_code,
        decision_status=row.current_state,
        reason_codes=[row.blocked_reason_code] if row.blocked_reason_code else ["diagnose_ok"],
        strategy_allocation_reason=row.blocked_solution_hint or "signal_runtime_diagnose",
        meta_engine_decision=row.meta_engine_decision,
        feature_snapshot={
            "execution_eligible": bool(row.execution_eligible),
            "requires_manual_approval": bool(row.requires_manual_approval),
            "actions_applied": actions_applied,
        },
        context_payload={
            "pending_signal_id": row.id,
            "signal_id": row.signal_id,
            "blocked_reason_code": row.blocked_reason_code,
            "current_state": row.current_state,
            "auto_fix": bool(auto_fix),
        },
    )

    db.commit()
    db.refresh(row)
    row.execution_mode_label = _execution_mode_label(row.mode)
    return row, actions_applied


def bulk_fix_blocked_signals(db: Session, user_id: str, limit: int = 200) -> dict:
    rows = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id, PendingSignal.status == "blocked")
        .order_by(PendingSignal.created_at.desc())
        .limit(max(min(limit, 500), 1))
        .all()
    )

    actions_summary: dict[str, int] = {}
    updated_signal_ids: list[str] = []
    fixed_count = 0

    for row in rows:
        updated, actions_applied = diagnose_pending_signal(db, user_id, row.id, auto_fix=True)
        if actions_applied:
            updated_signal_ids.append(updated.id)
        for action in actions_applied:
            actions_summary[action] = actions_summary.get(action, 0) + 1
        if actions_applied or str(updated.status).lower() != "blocked":
            fixed_count += 1

    remaining_blocked = (
        db.query(PendingSignal)
        .filter(PendingSignal.user_id == user_id, PendingSignal.status == "blocked")
        .count()
    )

    return {
        "scanned_count": len(rows),
        "blocked_before": len(rows),
        "fixed_count": fixed_count,
        "remaining_blocked": remaining_blocked,
        "updated_signal_ids": updated_signal_ids,
        "actions_summary": actions_summary,
    }