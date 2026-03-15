from services import universe_service


def test_full_market_scan_combines_spot_and_futures(monkeypatch):
    def fake_debug_effective_universe(db, cache, *, market_type, scanner_mode, selected_symbols, top_n):
        _ = (db, cache, scanner_mode, selected_symbols, top_n)
        if market_type == "spot":
            return {"final_symbols": ["BTCUSDT", "ETHUSDT"], "after_scanner_mode": 2}
        return {"final_symbols": ["BTCUSDT", "SOLUSDT"], "after_scanner_mode": 2}

    monkeypatch.setattr(universe_service, "debug_effective_universe", fake_debug_effective_universe)
    monkeypatch.setattr(universe_service, "get_json", lambda cache, key: {})

    payload = universe_service.get_full_market_universe(None, None, scanner_mode="all_market_symbols", selected_symbols=[], top_n=50)

    assert payload["combined_universe_size"] == 3
    assert set(payload["combined_symbols"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
