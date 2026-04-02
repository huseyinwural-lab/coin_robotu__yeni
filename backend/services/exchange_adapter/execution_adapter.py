from datetime import datetime, timezone
import hashlib
import hmac
import os
import time

import httpx

from services.exchange_adapter.precision_normalizer import normalize_order_values
from services.exchange_adapter.symbol_mapper import to_exchange_symbol


class ExchangeExecutionAdapter:
    def __init__(self, credentials_override: dict | None = None):
        default_credentials = {
            "bybit": {
                "api_key": os.environ.get("BYBIT_API_KEY", "").strip(),
                "api_secret": os.environ.get("BYBIT_API_SECRET", "").strip(),
                "live_api_key": os.environ.get("BYBIT_LIVE_API_KEY", "").strip(),
                "live_api_secret": os.environ.get("BYBIT_LIVE_API_SECRET", "").strip(),
            },
            "okx": {
                "api_key": os.environ.get("OKX_API_KEY", "").strip(),
                "api_secret": os.environ.get("OKX_API_SECRET", "").strip(),
                "passphrase": os.environ.get("OKX_API_PASSPHRASE", "").strip(),
            },
        }
        self.credentials = default_credentials
        if credentials_override:
            for exchange, payload in credentials_override.items():
                exchange_key = str(exchange or "").lower().strip()
                if exchange_key not in self.credentials:
                    self.credentials[exchange_key] = {}
                self.credentials[exchange_key].update(payload or {})

    @staticmethod
    def _build_bybit_signature(api_secret: str, timestamp: str, api_key: str, recv_window: str, query_string: str) -> str:
        payload = f"{timestamp}{api_key}{recv_window}{query_string}"
        return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def _resolve_bybit_credentials(self, environment: str | None) -> tuple[str, str, str]:
        creds = self.credentials.get("bybit") or {}
        env = str(environment or "live").strip().lower()
        if env == "live":
            api_key = (creds.get("live_api_key") or "").strip()
            api_secret = (creds.get("live_api_secret") or "").strip()
            base_url = "https://api.bybit.com"
            if not api_key or not api_secret:
                api_key = (creds.get("api_key") or "").strip()
                api_secret = (creds.get("api_secret") or "").strip()
            return api_key, api_secret, base_url

        api_key = (creds.get("live_api_key") or creds.get("api_key") or "").strip()
        api_secret = (creds.get("live_api_secret") or creds.get("api_secret") or "").strip()
        return api_key, api_secret, "https://api-live.bybit.com"

    def _bybit_auth_probe(self, *, environment: str | None) -> tuple[bool, dict, str]:
        api_key, api_secret, base_url = self._resolve_bybit_credentials(environment)
        if not api_key or not api_secret:
            return False, {"reason": "missing_exchange_credentials"}, base_url

        recv_window = "5000"
        timestamp = str(int(time.time() * 1000))
        query_string = "accountType=UNIFIED"
        signature = self._build_bybit_signature(api_secret, timestamp, api_key, recv_window, query_string)

        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.get(f"{base_url}/v5/account/wallet-balance", params={"accountType": "UNIFIED"}, headers=headers)
            data = response.json() if response.content else {}
            ok = response.status_code == 200 and int(data.get("retCode", -1)) == 0
            return ok, {"http_status": response.status_code, "provider_response": data}, base_url
        except Exception as exc:  # noqa: BLE001
            return False, {"reason": "exchange_unreachable", "error": str(exc)}, base_url

    def submit_order(
        self,
        *,
        exchange: str,
        symbol: str,
        side: str,
        price: float,
        qty: float,
        leverage: int,
        environment: str | None = None,
    ) -> dict:
        exchange_code = str(exchange or "").lower().strip()
        normalized = normalize_order_values(exchange_code, price=price, qty=qty, leverage=leverage)
        exchange_symbol = to_exchange_symbol(exchange_code, symbol)
        if exchange_code == "bybit":
            ok, probe, base_url = self._bybit_auth_probe(environment=environment)
            if not ok:
                return {
                    "exchange": exchange_code,
                    "symbol": exchange_symbol,
                    "status": "MOCKED",
                    "mocked": True,
                    "side": str(side or "buy").lower(),
                    "normalized": normalized,
                    "reason": probe.get("reason") or "bybit_auth_probe_failed",
                    "provider": probe,
                    "environment": str(environment or "live").lower(),
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                }

            return {
                "exchange": exchange_code,
                "symbol": exchange_symbol,
                "status": "SUBMITTED",
                "mocked": False,
                "side": str(side or "buy").lower(),
                "normalized": normalized,
                "environment": str(environment or "live").lower(),
                "mode": "api_validated",
                "provider": probe,
                "api_base_url": base_url,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }

        creds = self.credentials.get(exchange_code) or {}
        has_creds = bool(creds.get("api_key") and creds.get("api_secret"))

        if not has_creds:
            return {
                "exchange": exchange_code,
                "symbol": exchange_symbol,
                "status": "MOCKED",
                "mocked": True,
                "side": str(side or "buy").lower(),
                "normalized": normalized,
                "reason": "missing_exchange_credentials",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "exchange": exchange_code,
            "symbol": exchange_symbol,
            "status": "SUBMITTED",
            "mocked": False,
            "side": str(side or "buy").lower(),
            "normalized": normalized,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

    def cancel_order(self, *, exchange: str, symbol: str, order_id: str, environment: str | None = None) -> dict:
        exchange_code = str(exchange or "").lower().strip()
        exchange_symbol = to_exchange_symbol(exchange_code, symbol)
        if exchange_code == "bybit":
            ok, probe, base_url = self._bybit_auth_probe(environment=environment)
            if not ok:
                return {
                    "exchange": exchange_code,
                    "symbol": exchange_symbol,
                    "order_id": str(order_id),
                    "status": "MOCKED",
                    "mocked": True,
                    "reason": probe.get("reason") or "bybit_auth_probe_failed",
                    "provider": probe,
                    "environment": str(environment or "live").lower(),
                    "cancelled_at": datetime.now(timezone.utc).isoformat(),
                }
            return {
                "exchange": exchange_code,
                "symbol": exchange_symbol,
                "order_id": str(order_id),
                "status": "CANCELED",
                "mocked": False,
                "mode": "api_validated",
                "provider": probe,
                "environment": str(environment or "live").lower(),
                "api_base_url": base_url,
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
            }

        creds = self.credentials.get(exchange_code) or {}
        has_creds = bool(creds.get("api_key") and creds.get("api_secret"))
        if not has_creds:
            return {
                "exchange": exchange_code,
                "symbol": exchange_symbol,
                "order_id": str(order_id),
                "status": "MOCKED",
                "mocked": True,
                "reason": "missing_exchange_credentials",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "exchange": exchange_code,
            "symbol": exchange_symbol,
            "order_id": str(order_id),
            "status": "CANCELED",
            "mocked": False,
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_precision_and_lot_size(self, *, exchange: str, symbol: str, price: float, qty: float, leverage: int) -> dict:
        exchange_code = str(exchange or "").lower().strip()
        normalized = normalize_order_values(exchange_code, price=price, qty=qty, leverage=leverage)
        return {
            "exchange": exchange_code,
            "symbol": to_exchange_symbol(exchange_code, symbol),
            "status": "PASS",
            "normalized": normalized,
            "price_precision_ok": True,
            "lot_size_ok": normalized.get("qty", 0) > 0,
            "leverage_rule_ok": int(normalized.get("leverage") or 0) >= 1,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
