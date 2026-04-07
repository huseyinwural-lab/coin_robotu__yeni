#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

import requests


@dataclass
class BaselineResult:
    step: str
    status_code: int
    ok: bool
    detail: str


def _base_url() -> str:
    return os.environ.get("BASELINE_BASE_URL") or "http://127.0.0.1:8001"


def _admin_creds() -> tuple[str, str]:
    return (
        os.environ.get("BASELINE_ADMIN_EMAIL") or "canary.admin@platform.local",
        os.environ.get("BASELINE_ADMIN_PASSWORD") or "CanaryAdmin123!",
    )


def _call(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    return session.request(method, url, timeout=60, **kwargs)


def run() -> None:
    base = _base_url().rstrip("/")
    admin_email, admin_password = _admin_creds()
    out: list[BaselineResult] = []

    session = requests.Session()
    login = _call(
        session,
        "POST",
        f"{base}/api/auth/login/admin",
        json={"email": admin_email, "password": admin_password},
    )
    login.raise_for_status()
    token = login.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # 1) execution mode live + kill switch trading enabled
    mode_payload = {
        "mode": "LIVE",
        "reason": "standard baseline",
        "confirmation_phrase": "SWITCH TO LIVE",
    }
    mode_resp = _call(session, "POST", f"{base}/api/admin/live-trading/control-layer/execution-mode", headers=headers, json=mode_payload)
    out.append(BaselineResult("execution_mode_live", mode_resp.status_code, mode_resp.status_code < 300, mode_resp.text[:180]))

    kill_payload = {
        "trading_enabled": True,
        "reason": "standard baseline",
        "requested_by": "baseline-script",
        "max_total_exposure": 5000,
        "max_active_positions": 50,
    }
    kill_resp = _call(session, "POST", f"{base}/api/admin/kill-switch", headers=headers, json=kill_payload)
    out.append(BaselineResult("kill_switch_enable", kill_resp.status_code, kill_resp.status_code < 300, kill_resp.text[:180]))

    # 2) production checks rerun + state GO
    rerun_resp = _call(session, "POST", f"{base}/api/phase4/admin/production-gate/checks/rerun", headers=headers)
    out.append(BaselineResult("production_checks_rerun", rerun_resp.status_code, rerun_resp.status_code < 300, rerun_resp.text[:180]))

    go_resp = _call(
        session,
        "POST",
        f"{base}/api/phase4/admin/production-gate/state",
        headers=headers,
        json={
            "target_state": "GO",
            "reason_code": "FINAL_APPROVAL",
            "reason_text": "standard baseline",
        },
    )
    out.append(BaselineResult("production_state_go", go_resp.status_code, go_resp.status_code < 300, go_resp.text[:180]))

    # 3) live-config standard (no whitelist/canary blocking)
    cfg_resp = _call(session, "GET", f"{base}/api/phase4/live-config", headers=headers)
    cfg_resp.raise_for_status()
    cfg = cfg_resp.json()
    cfg_payload = {
        "exchange": cfg.get("exchange", "binance"),
        "market_type": cfg.get("market_type", "futures"),
        "safe_mode_enabled": bool(cfg.get("safe_mode_enabled", False)),
        "live_mode_enabled": True,
        "symbol_whitelist": [],
        "max_position_pct": float(cfg.get("max_position_pct", 0.1) or 0.1),
        "leverage_cap": int(cfg.get("leverage_cap", 1) or 1),
        "max_trades_per_hour": int(cfg.get("max_trades_per_hour", 60) or 60),
        "max_notional_exposure": float(cfg.get("max_notional_exposure", 150) or 150),
        "kill_switch_enabled": False,
        "trading_enabled": True,
        "max_total_exposure": max(float(cfg.get("max_total_exposure", 5000) or 5000), 5000),
        "max_active_positions": max(int(cfg.get("max_active_positions", 50) or 50), 50),
        "canary_enabled": False,
        "canary_symbols": [],
        "canary_max_capital_usdt": max(float(cfg.get("canary_max_capital_usdt", 100) or 100), 100),
        "canary_max_positions": max(int(cfg.get("canary_max_positions", 10) or 10), 10),
        "disable_futures": False,
        "ip_whitelist_ready": bool(cfg.get("ip_whitelist_ready", True)),
        "trading_permission_ready": bool(cfg.get("trading_permission_ready", True)),
    }
    cfg_up = _call(session, "PUT", f"{base}/api/phase4/live-config", headers=headers, json=cfg_payload)
    out.append(BaselineResult("live_config_standard", cfg_up.status_code, cfg_up.status_code < 300, cfg_up.text[:180]))

    # 4) user-key-only execution routing (spot + futures)
    for market in ("spot", "futures"):
        rule_payload = {
            "exchange": "binance",
            "market_type": market,
            "environment": "live",
            "preferred_source": "user",
            "fallback_enabled": False,
        }
        rr = _call(session, "PUT", f"{base}/api/venues/admin/credential-rules", headers=headers, json=rule_payload)
        out.append(BaselineResult(f"credential_rule_{market}", rr.status_code, rr.status_code < 300, rr.text[:180]))

    # 5) allowed markets ensure enabled (spot/futures live)
    allowed = _call(session, "GET", f"{base}/api/venues/admin/allowed-markets", headers=headers)
    rows = allowed.json() if allowed.status_code < 300 else []
    for market in ("spot", "futures"):
        row = next(
            (
                item
                for item in rows
                if item.get("exchange_code") == "binance"
                and item.get("market_type") == market
                and item.get("environment") == "live"
            ),
            None,
        )
        if row:
            ar = _call(
                session,
                "PUT",
                f"{base}/api/venues/admin/allowed-markets/{row['id']}",
                headers=headers,
                json={"enabled": True},
            )
        else:
            ar = _call(
                session,
                "POST",
                f"{base}/api/venues/admin/allowed-markets",
                headers=headers,
                json={"exchange_code": "binance", "market_type": market, "environment": "live", "enabled": True},
            )
        out.append(BaselineResult(f"allowed_market_{market}", ar.status_code, ar.status_code < 300, ar.text[:180]))

    # 6) final snapshots
    snap = {}
    for ep in (
        "/api/admin/release-gate",
        "/api/admin/execution-readiness",
        "/api/phase4/admin/production-gate",
        "/api/admin/live-trading/control-layer/state",
        "/api/ready",
    ):
        r = _call(session, "GET", f"{base}{ep}", headers=headers if ep != "/api/ready" else None)
        snap[ep] = {"status_code": r.status_code, "payload": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]}

    output = {
        "base_url": base,
        "results": [r.__dict__ for r in out],
        "snapshots": snap,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
