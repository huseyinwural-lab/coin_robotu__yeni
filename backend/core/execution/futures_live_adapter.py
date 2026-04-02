from core.execution.futures_execution_contract import FuturesExecutionRequest
from services.live_mode_service import BinanceFuturesLiveAdapter


class FuturesLiveAdapter:
    def __init__(self, adapter: BinanceFuturesLiveAdapter | None = None):
        self.adapter = adapter or BinanceFuturesLiveAdapter()

    def submit_market_order(self, api_key: str, api_secret: str, request: FuturesExecutionRequest) -> dict:
        payload, status_code = self.adapter._signed_post(
            api_key,
            api_secret,
            "/fapi/v1/order",
            {
                "symbol": request.symbol,
                "side": request.side,
                "type": "MARKET",
                "quantity": round(float(request.quantity), 6),
                "reduceOnly": "true" if request.reduce_only else "false",
                "newClientOrderId": request.client_order_id,
            },
        )
        return {
            "status_code": status_code,
            "payload": payload,
            "accepted": status_code in {200, 201},
            "order_id": payload.get("orderId"),
        }

    def cancel_order(self, api_key: str, api_secret: str, *, symbol: str, order_id: int) -> dict:
        payload, status_code = self.adapter.cancel_order(api_key, api_secret, symbol, int(order_id), market_type="futures")
        return {"status_code": status_code, "payload": payload, "cancelled": status_code == 200}

    def order_status(self, api_key: str, api_secret: str, *, symbol: str, order_id: int) -> dict:
        payload, status_code = self.adapter.query_order(api_key, api_secret, symbol, int(order_id))
        return {"status_code": status_code, "payload": payload}

    def fill_status(self, api_key: str, api_secret: str, *, symbol: str, order_id: int) -> dict:
        payload, status_code, _ = self.adapter._signed_get(
            api_key,
            api_secret,
            "/fapi/v1/userTrades",
            {
                "symbol": symbol,
                "orderId": int(order_id),
                "limit": 50,
            },
        )
        fills = payload if isinstance(payload, list) else []
        filled_qty = sum(float(item.get("qty", 0.0) or 0.0) for item in fills)
        avg_price = 0.0
        if fills and filled_qty > 0:
            total_quote = sum(float(item.get("qty", 0.0) or 0.0) * float(item.get("price", 0.0) or 0.0) for item in fills)
            avg_price = total_quote / filled_qty
        return {
            "status_code": status_code,
            "fills": fills,
            "filled_qty": round(filled_qty, 8),
            "avg_fill_price": round(avg_price, 8),
            "has_fill": filled_qty > 0,
        }
