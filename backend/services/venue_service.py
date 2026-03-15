import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import AllowedMarket, ExchangeCapability, ExchangeRegistry, UserVenueAssignment


def seed_binance_venue_registry(db: Session):
    exchanges = [
        {
            "exchange_code": "binance",
            "exchange_name": "Binance",
            "supported_market_types": ["spot", "futures"],
            "supports_testnet": True,
            "supports_live": False,
            "adapter_version": "v1",
        },
        {
            "exchange_code": "bybit",
            "exchange_name": "Bybit",
            "supported_market_types": ["spot", "futures"],
            "supports_testnet": True,
            "supports_live": False,
            "adapter_version": "v1-alpha",
        },
        {
            "exchange_code": "okx",
            "exchange_name": "OKX",
            "supported_market_types": ["spot", "futures"],
            "supports_testnet": True,
            "supports_live": False,
            "adapter_version": "v1-alpha",
        },
    ]
    for exchange_payload in exchanges:
        exchange = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange_payload["exchange_code"]).first()
        if exchange is None:
            exchange = ExchangeRegistry(
                id=str(uuid.uuid4()),
                exchange_code=exchange_payload["exchange_code"],
                exchange_name=exchange_payload["exchange_name"],
                status="active",
                supported_market_types=exchange_payload["supported_market_types"],
                supports_testnet=exchange_payload["supports_testnet"],
                supports_live=exchange_payload["supports_live"],
                health_status="healthy",
                rate_limit_status="ok",
                adapter_version=exchange_payload["adapter_version"],
                updated_at=datetime.now(timezone.utc),
            )
            db.add(exchange)

    defaults = [
        {
            "market_type": "spot",
            "supports_spot": True,
            "supports_futures": False,
            "supports_test_order": True,
            "supports_quote_qty": True,
            "supports_reduce_only": False,
            "supports_leverage": False,
            "supports_margin_mode": False,
            "supports_hedge_mode": False,
        },
        {
            "market_type": "futures",
            "supports_spot": False,
            "supports_futures": True,
            "supports_test_order": True,
            "supports_quote_qty": True,
            "supports_reduce_only": True,
            "supports_leverage": True,
            "supports_margin_mode": True,
            "supports_hedge_mode": True,
        },
    ]
    for exchange_payload in exchanges:
        for payload in defaults:
            row = (
                db.query(ExchangeCapability)
                .filter(
                    ExchangeCapability.exchange_code == exchange_payload["exchange_code"],
                    ExchangeCapability.market_type == payload["market_type"],
                )
                .first()
            )
            if row is None:
                db.add(
                    ExchangeCapability(
                        id=str(uuid.uuid4()),
                        exchange_code=exchange_payload["exchange_code"],
                        updated_at=datetime.now(timezone.utc),
                        **payload,
                    )
                )

    allowed_defaults = [
        ("spot", "testnet", True),
        ("spot", "live", False),
        ("futures", "testnet", True),
        ("futures", "live", False),
    ]
    for exchange_payload in exchanges:
        for market_type, environment, enabled in allowed_defaults:
            row = (
                db.query(AllowedMarket)
                .filter(
                    AllowedMarket.exchange_code == exchange_payload["exchange_code"],
                    AllowedMarket.market_type == market_type,
                    AllowedMarket.environment == environment,
                )
                .first()
            )
            if row is None:
                db.add(
                    AllowedMarket(
                        id=str(uuid.uuid4()),
                        exchange_code=exchange_payload["exchange_code"],
                        market_type=market_type,
                        environment=environment,
                        enabled=enabled,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

    db.commit()


def user_allowed_venue_options(db: Session, user_id: str) -> list[dict]:
    assignments = db.query(UserVenueAssignment).filter(UserVenueAssignment.user_id == user_id).all()
    if not assignments:
        return []

    options: list[dict] = []
    for assignment in assignments:
        exchange = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == assignment.exchange_code).first()
        if not exchange or exchange.status != "active":
            continue

        for market_type in ["spot", "futures"]:
            if market_type == "spot" and not assignment.spot_allowed:
                continue
            if market_type == "futures" and not assignment.futures_allowed:
                continue
            capability = (
                db.query(ExchangeCapability)
                .filter(
                    ExchangeCapability.exchange_code == assignment.exchange_code,
                    ExchangeCapability.market_type == market_type,
                )
                .first()
            )
            if capability is None:
                options.append(
                    {
                        "exchange": assignment.exchange_code,
                        "market_type": market_type,
                        "environment": "testnet",
                        "venue_state": "capability_mismatch",
                    }
                )
                continue

            for environment in ["testnet", "live"]:
                if environment == "testnet" and not assignment.testnet_allowed:
                    continue
                if environment == "live" and not assignment.live_allowed:
                    continue
                allowed_market = (
                    db.query(AllowedMarket)
                    .filter(
                        AllowedMarket.exchange_code == assignment.exchange_code,
                        AllowedMarket.market_type == market_type,
                        AllowedMarket.environment == environment,
                    )
                    .first()
                )
                if not allowed_market or not allowed_market.enabled:
                    continue
                options.append(
                    {
                        "exchange": assignment.exchange_code,
                        "market_type": market_type,
                        "environment": environment,
                        "venue_state": "venue_ready",
                    }
                )
    return options


def check_user_venue_access(db: Session, user_id: str, exchange: str, market_type: str, environment: str) -> tuple[bool, str, bool, list[str]]:
    assignments = (
        db.query(UserVenueAssignment)
        .filter(UserVenueAssignment.user_id == user_id, UserVenueAssignment.exchange_code == exchange)
        .all()
    )
    if not assignments:
        return False, "no_assigned_venues", False, ["assignment_required"]

    exchange_row = db.query(ExchangeRegistry).filter(ExchangeRegistry.exchange_code == exchange).first()
    if exchange_row is None or exchange_row.status != "active":
        return False, "venue_blocked", False, ["inactive_exchange"]

    assignment = assignments[0]
    if market_type == "spot" and not assignment.spot_allowed:
        return False, "venue_blocked", False, ["spot_not_allowed"]
    if market_type == "futures" and not assignment.futures_allowed:
        return False, "venue_blocked", False, ["futures_not_allowed"]
    if environment == "testnet" and not assignment.testnet_allowed:
        return False, "venue_blocked", False, ["testnet_not_allowed"]
    if environment == "live" and not assignment.live_allowed:
        return False, "venue_blocked", False, ["live_not_allowed"]

    allowed_market = (
        db.query(AllowedMarket)
        .filter(
            AllowedMarket.exchange_code == exchange,
            AllowedMarket.market_type == market_type,
            AllowedMarket.environment == environment,
        )
        .first()
    )
    if not allowed_market or not allowed_market.enabled:
        return False, "venue_blocked", False, ["market_disabled"]

    capability = (
        db.query(ExchangeCapability)
        .filter(ExchangeCapability.exchange_code == exchange, ExchangeCapability.market_type == market_type)
        .first()
    )
    if capability is None:
        return False, "capability_mismatch", False, ["capability_missing"]

    capability_match = (market_type == "spot" and capability.supports_spot) or (market_type == "futures" and capability.supports_futures)
    if not capability_match:
        return False, "capability_mismatch", False, ["capability_mismatch"]

    return True, "venue_ready", True, []


def venue_health_summary(db: Session) -> dict:
    exchanges = db.query(ExchangeRegistry).all()
    allowed = db.query(AllowedMarket).all()
    capabilities = db.query(ExchangeCapability).all()

    exchange_health = {item.exchange_code: item.health_status for item in exchanges}
    market_availability = {
        f"{item.exchange_code}:{item.market_type}:{item.environment}": bool(item.enabled)
        for item in allowed
    }
    capability_mismatch: list[str] = []
    for cap in capabilities:
        if cap.market_type == "spot" and not cap.supports_spot:
            capability_mismatch.append(f"{cap.exchange_code}:spot")
        if cap.market_type == "futures" and not cap.supports_futures:
            capability_mismatch.append(f"{cap.exchange_code}:futures")

    adapter_error_status = {
        item.exchange_code: ("adapter_error" if item.health_status not in {"healthy", "degraded"} else "ok")
        for item in exchanges
    }
    return {
        "exchange_health": exchange_health,
        "market_availability": market_availability,
        "capability_mismatch": capability_mismatch,
        "adapter_error_status": adapter_error_status,
    }