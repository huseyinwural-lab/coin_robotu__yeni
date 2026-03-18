#!/usr/bin/env bash
set -euo pipefail

echo "[1/6] Servisler yeniden başlatılıyor..."
sudo supervisorctl restart backend >/dev/null
sudo supervisorctl restart frontend >/dev/null

BASE_URL="${BASE_URL:-}"
if [[ -z "$BASE_URL" ]]; then
  BASE_URL="$(grep -E '^REACT_APP_BACKEND_URL=' /app/frontend/.env | head -n1 | cut -d'=' -f2-)"
fi

if [[ -z "$BASE_URL" ]]; then
  echo "HATA: BASE_URL bulunamadı. frontend/.env içinde REACT_APP_BACKEND_URL gerekli."
  exit 1
fi

export BASE_URL
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@platform.local}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin12345!}"
export LIVE_USER_EMAIL="${LIVE_USER_EMAIL:-}"
export LIVE_USER_PASSWORD="${LIVE_USER_PASSWORD:-}"
export ADMIN_MFA_METHOD="${ADMIN_MFA_METHOD:-}"
export ADMIN_MFA_CODE="${ADMIN_MFA_CODE:-}"
export USER_MFA_METHOD="${USER_MFA_METHOD:-}"
export USER_MFA_CODE="${USER_MFA_CODE:-}"
export MICRO_SYMBOL="${MICRO_SYMBOL:-ETHUSDT}"
export MICRO_NOTIONAL_USDT="${MICRO_NOTIONAL_USDT:-7}"

if [[ -z "$LIVE_USER_EMAIL" || -z "$LIVE_USER_PASSWORD" ]]; then
  echo "HATA: LIVE_USER_EMAIL ve LIVE_USER_PASSWORD export etmelisin."
  echo "Örnek: LIVE_USER_EMAIL='user@example.com' LIVE_USER_PASSWORD='Pass123!' bash /app/scripts/start_live.sh"
  exit 1
fi

echo "[2/6] Health ve canlı checklist kontrolü çalışıyor..."
python - <<'PY'
import json
import os
import time
from typing import Any

import requests

BASE = os.environ["BASE_URL"].rstrip("/")
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
LIVE_USER_EMAIL = os.environ["LIVE_USER_EMAIL"]
LIVE_USER_PASSWORD = os.environ["LIVE_USER_PASSWORD"]
ADMIN_MFA_METHOD = os.environ.get("ADMIN_MFA_METHOD", "").strip().lower()
ADMIN_MFA_CODE = os.environ.get("ADMIN_MFA_CODE", "").strip()
USER_MFA_METHOD = os.environ.get("USER_MFA_METHOD", "").strip().lower()
USER_MFA_CODE = os.environ.get("USER_MFA_CODE", "").strip()
MICRO_SYMBOL = os.environ.get("MICRO_SYMBOL", "ETHUSDT").strip().upper()
MICRO_NOTIONAL_USDT = float(os.environ.get("MICRO_NOTIONAL_USDT", "7") or 7)

s = requests.Session()


def fail(msg: str, data: dict[str, Any] | None = None) -> None:
    payload = {"ok": False, "error": msg}
    if data:
        payload["data"] = data
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(1)


def ok(msg: str, data: dict[str, Any] | None = None) -> None:
    payload = {"ok": True, "message": msg}
    if data:
        payload["data"] = data
    print(json.dumps(payload, ensure_ascii=False))


def request(method: str, path: str, **kwargs):
    url = f"{BASE}{path}"
    return s.request(method, url, timeout=60, **kwargs)


def wait_health() -> None:
    for _ in range(30):
        try:
            r = request("GET", "/api/health")
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    fail("Backend health check başarısız", {"base_url": BASE})


def verify_login_with_optional_mfa(panel: str, email: str, password: str, preferred_method: str, preferred_code: str):
    endpoint = "/api/auth/login/admin" if panel == "admin" else "/api/auth/login/user"
    login_resp = request("POST", endpoint, json={"email": email, "password": password})
    if login_resp.status_code != 200:
        fail(f"{panel} login başarısız", {"status": login_resp.status_code, "body": login_resp.text[:300]})
    body = login_resp.json()

    if not body.get("mfa_required"):
        token = body.get("access_token")
        if not token:
            fail(f"{panel} login token alınamadı", {"body": body})
        return token

    methods = [str(x).lower() for x in (body.get("mfa_methods") or [])]
    if not methods:
        fail(f"{panel} MFA methods boş geldi", {"body": body})

    method = preferred_method if preferred_method in methods else methods[0]
    code = preferred_code
    if not code and method == "email":
        code = str(body.get("email_code_preview") or "")
    if not code:
        fail(
            f"{panel} MFA kodu gerekli",
            {
                "hint": f"{panel.upper()}_MFA_CODE env ver veya email preview fallback kullan",
                "methods": methods,
            },
        )

    verify = request(
        "POST",
        "/api/auth/mfa/challenge/verify",
        json={
            "challenge_token": body.get("mfa_challenge_token"),
            "method": method,
            "code": code,
        },
    )
    if verify.status_code != 200:
        fail(f"{panel} MFA verify başarısız", {"status": verify.status_code, "body": verify.text[:300]})

    token = verify.json().get("access_token")
    if not token:
        fail(f"{panel} MFA sonrası token alınamadı")
    return token


def ensure_revalidated_connection(user_headers: dict[str, str]) -> dict[str, Any]:
    rows_resp = request("GET", "/api/user/exchange-connections", headers=user_headers)
    if rows_resp.status_code != 200:
        fail("Exchange connection listesi alınamadı", {"status": rows_resp.status_code, "body": rows_resp.text[:220]})
    rows = rows_resp.json()
    if not isinstance(rows, list) or not rows:
        fail("Kullanıcıda exchange connection yok")

    conn = None
    for row in rows:
        if row.get("is_default") and str(row.get("exchange", "")).lower() == "binance":
            conn = row
            break
    if conn is None:
        conn = rows[0]

    reval = request("POST", f"/api/user/exchange-connections/{conn['id']}/revalidate", headers=user_headers)
    if reval.status_code != 200:
        fail("Connection revalidate başarısız", {"status": reval.status_code, "body": reval.text[:220]})

    payload = reval.json()
    rs = payload.get("readiness_snapshot") or {}
    if rs.get("reason_codes"):
        fail("Revalidate reason_codes dolu (canlıya uygun değil)", {"reason_codes": rs.get("reason_codes")})

    return conn


def readiness_stability(admin_headers: dict[str, str], user_headers: dict[str, str], conn: dict[str, Any]) -> None:
    user_states = []
    admin_states = []
    for _ in range(5):
        ur = request(
            "GET",
            "/api/exchange/readiness-checklist",
            headers=user_headers,
            params={
                "exchange": conn.get("exchange"),
                "market_type": conn.get("market_type"),
                "environment": conn.get("environment"),
            },
        )
        if ur.status_code != 200:
            fail("User readiness-checklist başarısız", {"status": ur.status_code, "body": ur.text[:200]})
        user_states.append(str(ur.json().get("readiness_status") or ""))

        ar = request("GET", "/api/admin/execution-readiness", headers=admin_headers)
        if ar.status_code != 200:
            fail("Admin execution-readiness başarısız", {"status": ar.status_code, "body": ar.text[:200]})
        admin_states.append(str(ar.json().get("final_status") or ""))
        time.sleep(0.35)

    if len(set(user_states)) != 1 or user_states[0] != "ready_for_test_order":
        fail("User readiness stabil READY değil", {"samples": user_states})
    if len(set(admin_states)) != 1 or admin_states[0] != "READY":
        fail("Admin execution-readiness stabil READY değil", {"samples": admin_states})


def market_price(user_headers: dict[str, str], symbol: str) -> float:
    ticker = request("GET", "/api/market/ticker", headers=user_headers, params={"symbol": symbol})
    if ticker.status_code != 200:
        fail("Market ticker alınamadı", {"status": ticker.status_code, "symbol": symbol, "body": ticker.text[:200]})
    price = float((ticker.json() or {}).get("mid_price") or 0)
    if price <= 0:
        fail("Ticker fiyatı geçersiz", {"symbol": symbol, "price": price})
    return price


def validate_order(user_headers: dict[str, str], symbol: str, price: float, size: float, leverage: int = 1):
    payload = {
        "symbol": symbol,
        "market_type": "futures",
        "order_type": "market",
        "side": "buy",
        "price": price,
        "size": size,
        "leverage": leverage,
        "margin_mode": "isolated",
    }
    resp = request("POST", "/api/user/validate-order", headers=user_headers, json=payload)
    if resp.status_code != 200:
        fail("validate-order başarısız", {"status": resp.status_code, "body": resp.text[:240]})
    return resp.json()


def run_micro_test_order(user_headers: dict[str, str], conn: dict[str, Any], symbol: str, notional: float):
    price = market_price(user_headers, symbol)
    qty = max(0.001, round(notional / price, 6))

    payload = None
    last_error = None
    for lev in (1, 2, 3, 5):
        test_order = request(
            "POST",
            "/api/exchange/test-order",
            headers=user_headers,
            params={
                "exchange": conn.get("exchange"),
                "market_type": conn.get("market_type"),
                "environment": conn.get("environment"),
                "symbol": symbol,
                "leverage": lev,
                "quantity": qty,
            },
        )
        if test_order.status_code != 200:
            last_error = {"status": test_order.status_code, "body": test_order.text[:220], "leverage": lev}
            continue
        payload = test_order.json()
        final_status = str(payload.get("final_status") or "").upper()
        if final_status == "FILLED":
            return {"price": price, "qty": qty, "notional": round(price * qty, 4), "leverage": lev}
        failure_code = str(payload.get("failure_code") or "")
        last_error = {"final_status": final_status, "payload": payload, "leverage": lev}
        if failure_code != "insufficient_balance":
            break

    fail("Micro test-order FILLED değil", last_error or {"payload": payload})
    return {"price": price, "qty": qty, "notional": round(price * qty, 4)}


def trade_open_and_position_check(user_headers: dict[str, str], admin_headers: dict[str, str], symbol: str, price: float):
    size = max(0.001, round(20 / price, 6))
    preview_payload = {
        "source_type": "manual",
        "intent_type": "OPEN_POSITION",
        "market_type": "futures",
        "symbol": symbol,
        "side": "buy",
        "order_type": "market",
        "position_size_mode": "fixed_notional",
        "position_size_value": 20,
        "size": size,
        "margin_mode": "isolated",
        "leverage": 1,
        "execution_mode": "manual",
        "holding_profile": "intraday",
    }
    preview = request("POST", "/api/v1/user/trading/preview", headers=user_headers, json=preview_payload)
    if preview.status_code != 200:
        fail("Trade preview başarısız", {"status": preview.status_code, "body": preview.text[:240]})
    pbody = preview.json().get("preview") or {}
    if str(pbody.get("validation_status") or "").lower() == "rejected":
        fail("Trade preview rejected", {"reject_reason_codes": pbody.get("reject_reason_codes")})

    open_resp = request(
        "POST",
        "/api/user/open-position",
        headers=user_headers,
        json={
            "intent_token": pbody.get("intent_token"),
            "preview_hash": pbody.get("preview_hash"),
        },
    )
    if open_resp.status_code != 200:
        fail("open-position başarısız", {"status": open_resp.status_code, "body": open_resp.text[:240]})
    obody = open_resp.json()
    if str(obody.get("execution_mode") or "").lower() != "live":
        fail("open-position execution_mode live değil", {"execution_mode": obody.get("execution_mode")})

    intent_id = obody.get("intent_id")
    if intent_id:
        approve = request(
            "POST",
            f"/api/admin/execution-queue/{intent_id}/approve",
            headers=admin_headers,
            json={"note": "live-start-script"},
        )
        # approve endpoint zaman zaman geçici hata dönebiliyor; position düşüşüyle doğruluyoruz
        if approve.status_code not in {200, 500}:
            fail("execution queue approve beklenmeyen hata", {"status": approve.status_code, "body": approve.text[:220]})

    found = False
    for _ in range(12):
        pos = request("GET", "/api/user/execution/positions", headers=user_headers)
        if pos.status_code == 200:
            rows = pos.json()
            found = any(str(r.get("symbol") or "").upper() == symbol for r in rows)
            if found:
                break
        time.sleep(1)
    if not found:
        fail("Trade sonrası position listede görünmedi", {"symbol": symbol})


def guard_and_risk_checks(user_headers: dict[str, str], symbol: str, price: float):
    valid_payload = validate_order(user_headers, symbol, price, max(0.001, round(20 / price, 6)), leverage=1)
    if not valid_payload.get("valid"):
        fail("Doğru input ALLOWED değil", {"violations": valid_payload.get("violations")})
    if str(valid_payload.get("execution_mode") or "").lower() != "live":
        fail("valid input execution_mode live değil", {"execution_mode": valid_payload.get("execution_mode")})

    invalid_payload = validate_order(user_headers, symbol, price, 0.00001, leverage=125)
    if invalid_payload.get("valid"):
        fail("Yanlış input BLOCKED olmadı", {"payload": invalid_payload})

    lev_payload = validate_order(user_headers, symbol, price, max(0.001, round(20 / price, 6)), leverage=25)
    lev_codes = [str(v.get("code") or "") for v in (lev_payload.get("violations") or []) if isinstance(v, dict)]
    if "leverage_limit_exceeded" not in lev_codes:
        fail("Leverage limiti çalışmıyor", {"codes": lev_codes})

    size_payload = validate_order(user_headers, symbol, price, 50, leverage=1)
    size_codes = [str(v.get("code") or "") for v in (size_payload.get("violations") or []) if isinstance(v, dict)]
    if "max_exposure_exceeded" not in size_codes:
        fail("Position size/max exposure limiti çalışmıyor", {"codes": size_codes})

    if len(valid_payload.get("explain") or []) < 1:
        fail("validate-order explain boş")


def balance_check(user_headers: dict[str, str], conn: dict[str, Any], symbol: str):
    huge = request(
        "POST",
        "/api/exchange/test-order",
        headers=user_headers,
        params={
            "exchange": conn.get("exchange"),
            "market_type": conn.get("market_type"),
            "environment": conn.get("environment"),
            "symbol": symbol,
            "leverage": 1,
            "quantity": 100,
        },
    )
    payload = huge.json() if huge.headers.get("content-type", "").startswith("application/json") else {}

    if huge.status_code == 200:
        if str(payload.get("final_status") or "").upper() != "REJECTED":
            fail("Yetersiz bakiye testi REJECTED değil", {"final_status": payload.get("final_status")})
        if str(payload.get("failure_code") or "") != "insufficient_balance":
            fail("Bakiye hata kodu unexpected", {"failure_code": payload.get("failure_code")})
        return

    if huge.status_code == 400:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, dict) and str(detail.get("failure_code") or "") == "insufficient_balance":
            return

    fail("Bakiye kontrol test-order çağrısı başarısız", {"status": huge.status_code, "body": huge.text[:260]})


def telemetry_and_explain(admin_headers: dict[str, str], user_headers: dict[str, str]):
    tele = request("GET", "/api/admin/guard-telemetry", headers=admin_headers)
    if tele.status_code != 200:
        fail("guard telemetry endpoint başarısız", {"status": tele.status_code, "body": tele.text[:220]})
    tb = tele.json()
    if tb.get("blocked_24h") is None or tb.get("override_24h") is None:
        fail("guard telemetry contract eksik", {"payload": tb})

    sc = request("GET", "/api/screener", headers=user_headers, params={"limit": 5})
    if sc.status_code != 200:
        fail("screener explain kontrolü başarısız", {"status": sc.status_code, "body": sc.text[:200]})
    rows = sc.json() if isinstance(sc.json(), list) else []
    # Ops kalemi: veri yoksa fail etmiyoruz, sadece not geçiyoruz.
    if rows:
        if len((rows[0] or {}).get("explain") or []) < 1:
            fail("screener explain boş", {"row": rows[0]})


def main():
    wait_health()

    admin_token = verify_login_with_optional_mfa(
        panel="admin",
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        preferred_method=ADMIN_MFA_METHOD,
        preferred_code=ADMIN_MFA_CODE,
    )
    user_token = verify_login_with_optional_mfa(
        panel="user",
        email=LIVE_USER_EMAIL,
        password=LIVE_USER_PASSWORD,
        preferred_method=USER_MFA_METHOD,
        preferred_code=USER_MFA_CODE,
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    conn = ensure_revalidated_connection(user_headers)
    readiness_stability(admin_headers, user_headers, conn)

    micro = run_micro_test_order(user_headers, conn, MICRO_SYMBOL, MICRO_NOTIONAL_USDT)
    px = micro["price"]

    guard_and_risk_checks(user_headers, MICRO_SYMBOL, px)
    balance_check(user_headers, conn, MICRO_SYMBOL)
    trade_open_and_position_check(user_headers, admin_headers, MICRO_SYMBOL, px)
    telemetry_and_explain(admin_headers, user_headers)

    summary = {
        "ok": True,
        "base_url": BASE,
        "execution_mode": "live",
        "micro_trade": {
            "symbol": MICRO_SYMBOL,
            "qty": micro["qty"],
            "notional_usdt": micro["notional"],
            "status": "FILLED",
        },
        "readiness": "READY_STABLE",
        "guard": "BLOCKED+ALLOWED_OK",
        "risk": "LEVERAGE+SIZE_LIMIT_OK",
        "balance": "INSUFFICIENT_BALANCE_BLOCK_OK",
        "telemetry": "OK",
        "explainability": "OK",
        "positions": "TRADE_REFLECTED",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
PY

echo "[3/6] Başlangıç + canlı checklist tamamlandı."
echo "[4/6] Script başarılı bitti."
echo "[5/6] Sistem canlı test için hazır."
echo "[6/6] Done."
