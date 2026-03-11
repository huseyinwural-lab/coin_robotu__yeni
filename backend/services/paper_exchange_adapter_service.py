import hashlib


class PaperExchangeAdapter:
    def submit_order(self, intent_payload: dict) -> dict:
        intent_hash = intent_payload["intent_hash"]
        seed = int(hashlib.sha256(intent_hash.encode("utf-8")).hexdigest()[:8], 16)

        lifecycle = ["NEW"]
        if seed % 5 == 0:
            lifecycle.append("REJECTED")
            status = "rejected"
        elif seed % 3 == 0:
            lifecycle.extend(["PARTIALLY_FILLED", "CANCELED"])
            status = "cancelled"
        else:
            lifecycle.extend(["PARTIALLY_FILLED", "FILLED"])
            status = "filled"

        external_order_id = f"paper-{intent_hash[:16]}"
        return {
            "external_order_id": external_order_id,
            "lifecycle": lifecycle,
            "status": status,
            "avg_fill_price": intent_payload.get("price_reference", {}).get("value"),
            "filled_qty": intent_payload.get("quantity"),
        }

    def cancel_order(self, external_order_id: str) -> dict:
        return {"external_order_id": external_order_id, "status": "cancelled"}

    def fetch_order(self, external_order_id: str) -> dict:
        return {"external_order_id": external_order_id, "status": "filled"}


paper_exchange_adapter = PaperExchangeAdapter()
