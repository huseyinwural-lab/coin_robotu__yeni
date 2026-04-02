from core.exchanges.binance_adapter import BinanceExecutionAdapter


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | list | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return self._payload


def test_signed_request_adds_proxy_header(monkeypatch):
    monkeypatch.setenv("BINANCE_LIVE_API_KEY", "k")
    monkeypatch.setenv("BINANCE_LIVE_API_SECRET", "s")
    monkeypatch.setenv("BINANCE_SPOT_LIVE_BASE_URL", "http://proxy.local/p/inferred-token")
    monkeypatch.delenv("BINANCE_SPOT_LIVE_PROXY_TOKEN", raising=False)
    monkeypatch.delenv("BINANCE_SPOT_PROXY_TOKEN", raising=False)
    monkeypatch.delenv("BINANCE_PROXY_TOKEN", raising=False)

    captured_headers = {}

    def _fake_request(method, url, headers=None, timeout=20.0):
        captured_headers.update(headers or {})
        return _FakeResponse(payload={"balances": []})

    monkeypatch.setattr("core.exchanges.binance_adapter.httpx.request", _fake_request)

    adapter = BinanceExecutionAdapter(mode="live")
    adapter._signed_request("GET", "/api/v3/account", {})

    assert captured_headers.get("X-MBX-APIKEY") == "k"
    assert captured_headers.get("X-Proxy-Token") == "inferred-token"


def test_public_request_uses_explicit_proxy_token(monkeypatch):
    monkeypatch.setenv("BINANCE_LIVE_API_KEY", "k")
    monkeypatch.setenv("BINANCE_LIVE_API_SECRET", "s")
    monkeypatch.setenv("BINANCE_SPOT_LIVE_BASE_URL", "http://proxy.local/p/ignored-token")
    monkeypatch.setenv("BINANCE_SPOT_LIVE_PROXY_TOKEN", "explicit-token")

    captured_headers = {}

    def _fake_request(method, url, headers=None, timeout=20.0):
        captured_headers.update(headers or {})
        return _FakeResponse(payload={})

    monkeypatch.setattr("core.exchanges.binance_adapter.httpx.request", _fake_request)

    adapter = BinanceExecutionAdapter(mode="live")
    adapter._public_request("GET", "/api/v3/ping")

    assert captured_headers.get("X-Proxy-Token") == "explicit-token"
    assert "X-MBX-APIKEY" not in captured_headers