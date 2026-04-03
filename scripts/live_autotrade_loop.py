import json
import os
import time
from collections import Counter
from datetime import datetime, timezone

import requests


class _RespLite:
    def __init__(self, status_code: int):
        self.status_code = status_code


BASE_URL = os.getenv("LIVE_LOOP_BASE_URL", "http://127.0.0.1:8001/api").rstrip("/")
ADMIN_EMAIL = os.getenv("LIVE_LOOP_ADMIN_EMAIL", "canary.admin@platform.local")
ADMIN_PASSWORD = os.getenv("LIVE_LOOP_ADMIN_PASSWORD", "CanaryAdmin123!")
USER_EMAIL = os.getenv("LIVE_LOOP_USER_EMAIL", "review.user@platform.local")
USER_PASSWORD = os.getenv("LIVE_LOOP_USER_PASSWORD", "ReviewUser123!")
SLEEP_SECONDS = int(os.getenv("LIVE_LOOP_SLEEP_SECONDS", "75"))
STOP_FILE = os.getenv("LIVE_LOOP_STOP_FILE", "/tmp/stop_live_autotrade")
STATE_FILE = os.getenv("LIVE_LOOP_STATE_FILE", "/tmp/live_autotrade_state.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"spot_idx": 0, "futures_idx": 0, "cycle": 0}


def _save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception:
        pass


def _login(path: str, email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}{path}",
        json={"email": email, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"token_missing:{path}")
    return token


def _pick_symbols(symbols: list[str], start_idx: int, count: int = 2) -> tuple[list[str], int]:
    if not symbols:
        return [], 0
    n = len(symbols)
    start = start_idx % n
    selected = [symbols[(start + offset) % n] for offset in range(min(count, n))]
    next_idx = (start + count) % n
    return selected, next_idx


def _request(method: str, path: str, headers: dict, timeout: int = 120, **kwargs):
    try:
        response = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=timeout, **kwargs)
        try:
            body = response.json()
        except Exception:
            body = response.text[:400]
        return response, body
    except Exception as exc:
        return _RespLite(599), {"error": str(exc)}


def _run_cycle() -> None:
    state = _load_state()
    state["cycle"] = int(state.get("cycle") or 0) + 1
    _log({"ts": _now(), "event": "cycle_start", "cycle": state["cycle"]})

    admin_token = _login("/auth/login/admin", ADMIN_EMAIL, ADMIN_PASSWORD)
    user_token = _login("/auth/login/user", USER_EMAIL, USER_PASSWORD)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}

    uni_resp, uni_body = _request(
        "GET",
        "/admin/universe/runtime-summary",
        admin_headers,
        timeout=20,
        params={"scanner_mode": "all_market_symbols", "top_n": 200},
    )
    if uni_resp.status_code != 200 or not isinstance(uni_body, dict):
        raise RuntimeError(f"universe_fetch_failed:{uni_resp.status_code}")

    exchange = (((uni_body.get("exchange_snapshot") or {}).get("exchanges") or {}).get("binance") or {})
    all_spot = [str(item).upper() for item in (exchange.get("spot_symbols") or []) if str(item).upper().endswith("USDT")]
    all_futures = [str(item).upper() for item in (exchange.get("futures_symbols") or []) if str(item).upper().endswith("USDT")]
    if not all_futures:
        all_futures = list(all_spot)

    spot_symbols, next_spot_idx = _pick_symbols(all_spot, int(state.get("spot_idx") or 0), count=2)
    futures_symbols, next_futures_idx = _pick_symbols(all_futures, int(state.get("futures_idx") or 0), count=2)

    _request("PUT", "/user/signal-mode", user_headers, timeout=20, json={"mode": "AUTO"})

    if state["cycle"] % 5 == 0:
        _request(
            "POST",
            "/user/signals/cleanup-stale-intents",
            user_headers,
            timeout=20,
            params={"stale_minutes": 25, "signal_stale_minutes": 180},
        )

    spot_run_resp, spot_run = _request(
        "POST",
        "/user/scanner/run",
        user_headers,
        timeout=35,
        json={
            "mode": "AUTO",
            "max_results": 6,
            "symbol_source": "crypto",
            "market_type": "spot",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": spot_symbols,
        },
    )

    futures_run_resp, futures_run = _request(
        "POST",
        "/user/scanner/run",
        user_headers,
        timeout=35,
        json={
            "mode": "AUTO",
            "max_results": 6,
            "symbol_source": "crypto",
            "market_type": "futures",
            "symbol_selection_mode": "manual_selection",
            "selected_symbols": futures_symbols,
        },
    )

    fix_resp, fix_body = _request(
        "POST",
        "/user/signals/fix-all-blockers",
        user_headers,
        timeout=30,
        params={"limit": 200},
    )

    signals_resp, signals_body = _request("GET", "/user/signals", user_headers, timeout=25, params={"limit": 20})
    trades_resp, trades_body = _request("GET", "/user/trades", user_headers, timeout=25, params={"limit": 40})

    signals = signals_body if isinstance(signals_body, list) else []
    trades = trades_body if isinstance(trades_body, list) else []

    _log(
        {
            "ts": _now(),
            "cycle": state["cycle"],
            "spot_symbols": spot_symbols,
            "futures_symbols": futures_symbols,
            "spot_run_status": spot_run_resp.status_code,
            "spot_run": {
                "run_id": (spot_run or {}).get("run_id") if isinstance(spot_run, dict) else None,
                "result_count": (spot_run or {}).get("result_count") if isinstance(spot_run, dict) else None,
                "actionable_count": (spot_run or {}).get("actionable_count") if isinstance(spot_run, dict) else None,
                "queued_count": (spot_run or {}).get("queued_count") if isinstance(spot_run, dict) else None,
            },
            "futures_run_status": futures_run_resp.status_code,
            "futures_run": {
                "run_id": (futures_run or {}).get("run_id") if isinstance(futures_run, dict) else None,
                "result_count": (futures_run or {}).get("result_count") if isinstance(futures_run, dict) else None,
                "actionable_count": (futures_run or {}).get("actionable_count") if isinstance(futures_run, dict) else None,
                "queued_count": (futures_run or {}).get("queued_count") if isinstance(futures_run, dict) else None,
            },
            "fix_all_blockers_status": fix_resp.status_code,
            "fix_all_blockers_summary": (fix_body or {}).get("summary") if isinstance(fix_body, dict) else None,
            "signals_status": signals_resp.status_code,
            "signals_market_count": dict(Counter([str(item.get("market_type") or "spot").lower() for item in signals])),
            "signals_state_count": dict(Counter([str(item.get("status") or "").lower() for item in signals])),
            "trades_status": trades_resp.status_code,
            "trades_market_count": dict(Counter([str(item.get("market_type") or "spot").lower() for item in trades])),
            "trades_state_count": dict(Counter([str(item.get("status") or "").upper() for item in trades])),
            "trades_sample": [
                {
                    "symbol": item.get("symbol"),
                    "market_type": item.get("market_type"),
                    "status": item.get("status"),
                    "quantity": item.get("quantity"),
                    "opened_at": item.get("opened_at"),
                }
                for item in trades[:6]
            ],
        }
    )

    state["spot_idx"] = next_spot_idx
    state["futures_idx"] = next_futures_idx
    _save_state(state)


def main() -> None:
    _log({"ts": _now(), "event": "live_autotrade_loop_started", "base_url": BASE_URL, "sleep_seconds": SLEEP_SECONDS})
    while True:
        if os.path.exists(STOP_FILE):
            _log({"ts": _now(), "event": "stop_file_detected", "stop_file": STOP_FILE})
            break
        try:
            _run_cycle()
        except Exception as exc:
            _log({"ts": _now(), "event": "loop_error", "error": str(exc)})
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
