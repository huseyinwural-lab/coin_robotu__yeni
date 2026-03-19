"""
Indicator Query Engine Comprehensive Test - IQ-01 to IQ-06 + IQ-10
=================================================================
Test Scope:
- IQ-01: POST /run - rsi14<30, rsi7<30, combined AND/OR/() query
- IQ-02: Invalid query parse (drop table, unknown indicator, parenthesis error)
- IQ-03: Determinism - same payload returns consistent results
- IQ-04: GET /presets endpoint
- IQ-05: Saved Query CRUD
- IQ-06: Watchlist CRUD
- IQ-10: Response contract validation (query_valid/query_error/evaluated_count/match_count)
"""
import requests
from pathlib import Path
import sys
import uuid

sys.path.append(str(Path(__file__).resolve().parent))

from indicator_screener_test_utils import ensure_user_headers, resolve_base_url, random_suffix


BASE_URL = resolve_base_url()
USER_HEADERS = ensure_user_headers(BASE_URL, suffix="iq_comprehensive")


class TestIQ01RunEndpointQueryExecution:
    """IQ-01: POST /api/user/indicator-screener/run - Query Execution"""

    def test_iq01_rsi14_single_condition(self):
        """rsi14 < 30 single condition query"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 30",
            "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
            "limit": 50,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response.status_code == 200, f"Status: {response.status_code}, Body: {response.text}"
        data = response.json()
        
        # IQ-10 Response contract validation
        assert "query_valid" in data
        assert "query_error" in data
        assert "evaluated_count" in data
        assert "match_count" in data
        assert data["query_valid"] is True
        assert data["query_error"] is None
        
        # All matched rows should have rsi14 < 30
        for row in data["rows"]:
            assert row["rsi14"] < 30, f"Row rsi14={row['rsi14']} should be < 30"

    def test_iq01_rsi7_single_condition(self):
        """rsi7 < 30 single condition query"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi7 < 30",
            "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"],
            "limit": 50,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is True
        for row in data["rows"]:
            assert row["rsi7"] < 30

    def test_iq01_combined_and_condition(self):
        """Combined AND query: rsi14 < 30 AND rsi7 < 30"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "1h",
            "query_expression": "rsi14 < 30 AND rsi7 < 30",
            "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
            "limit": 50,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is True
        for row in data["rows"]:
            assert row["rsi14"] < 30 and row["rsi7"] < 30

    def test_iq01_combined_or_condition(self):
        """Combined OR query: rsi14 < 30 OR rsi7 < 25"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "1h",
            "query_expression": "rsi14 < 30 OR rsi7 < 25",
            "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
            "limit": 50,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is True
        for row in data["rows"]:
            assert row["rsi14"] < 30 or row["rsi7"] < 25

    def test_iq01_parenthesis_grouped_condition(self):
        """Parenthesis grouped query: (rsi14 < 30 OR rsi7 < 25) AND volume > 1000"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "1h",
            "query_expression": "(rsi14 < 30 OR rsi7 < 25) AND volume > 1000",
            "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
            "limit": 50,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is True
        for row in data["rows"]:
            assert (row["rsi14"] < 30 or row["rsi7"] < 25) and row["volume"] > 1000


class TestIQ02InvalidQueryParse:
    """IQ-02: Invalid query parsing with explanatory errors"""

    def test_iq02_drop_table_sql_injection_attempt(self):
        """SQL injection attempt should return explanatory error"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "drop table",
            "symbol_universe": ["BTCUSDT"],
            "limit": 10,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is False
        assert data["query_error"] is not None
        assert len(data["query_error"]) > 0

    def test_iq02_unknown_indicator_field(self):
        """Unknown indicator field should return explanatory error"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "unknown_field < 30",
            "symbol_universe": ["BTCUSDT"],
            "limit": 10,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is False
        assert data["query_error"] is not None
        assert "Desteklenmeyen alan adı" in data["query_error"]

    def test_iq02_unclosed_parenthesis_error(self):
        """Unclosed parenthesis should return explanatory error"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "(rsi14 < 30 AND rsi7 < 30",
            "symbol_universe": ["BTCUSDT"],
            "limit": 10,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is False
        assert data["query_error"] is not None
        assert "parantez" in data["query_error"].lower() or ")" in data["query_error"]

    def test_iq02_empty_query_expression(self):
        """Empty query expression should run filter-only mode"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "",
            "symbol_universe": ["BTCUSDT"],
            "limit": 10,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["query_valid"] is True
        assert data["query_error"] is None


class TestIQ03Determinism:
    """IQ-03: Determinism - same payload returns consistent results"""

    def test_iq03_same_payload_consistent_results(self):
        """Same payload should return consistent matched_symbols and match_count"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "4h",
            "query_expression": "rsi14 < 80 AND rsi7 < 85",
            "symbol_universe": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"],
            "limit": 50,
        }
        
        response1 = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response1.status_code == 200, response1.text
        data1 = response1.json()
        
        response2 = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response2.status_code == 200, response2.text
        data2 = response2.json()
        
        assert data1["query_valid"] is True
        assert data2["query_valid"] is True
        assert data1["matched_symbols"] == data2["matched_symbols"]
        assert data1["match_count"] == data2["match_count"]


class TestIQ04PresetsEndpoint:
    """IQ-04: GET /api/user/indicator-screener/presets"""

    def test_iq04_presets_returns_expected_keys(self):
        """Presets endpoint should return expected preset keys"""
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/presets",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= 3
        
        preset_keys = {item["preset_key"] for item in data}
        assert "oversold_rsi14" in preset_keys
        assert "oversold_rsi7" in preset_keys
        assert "double_oversold" in preset_keys
        
        for preset in data:
            assert "preset_key" in preset
            assert "title" in preset
            assert "query_expression" in preset


class TestIQ05SavedQueryCRUD:
    """IQ-05: Saved Query CRUD - /saved-queries GET/POST/DELETE"""

    def test_iq05_saved_query_create_list_delete(self):
        """Full CRUD flow for saved queries"""
        unique_name = f"test_iq05_{random_suffix()}"
        
        # CREATE
        create_payload = {
            "name": unique_name,
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 30 AND rsi7 < 30",
            "symbol_universe": ["BTCUSDT", "ETHUSDT"],
            "result_limit": 25,
        }
        create_response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/saved-queries",
            json=create_payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert create_response.status_code == 200, create_response.text
        created = create_response.json()
        query_id = created["id"]
        assert created["name"] == unique_name
        assert created["query_expression"] == "rsi14 < 30 AND rsi7 < 30"
        
        # READ (List)
        list_response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/saved-queries",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert list_response.status_code == 200, list_response.text
        items = list_response.json()
        assert any(item["id"] == query_id for item in items)
        
        # DELETE
        delete_response = requests.delete(
            f"{BASE_URL}/api/user/indicator-screener/saved-queries/{query_id}",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert delete_response.status_code == 200, delete_response.text
        delete_data = delete_response.json()
        assert delete_data.get("deleted") is True

    def test_iq05_saved_query_delete_nonexistent_returns_404(self):
        """Delete non-existent query should return 404"""
        fake_id = str(uuid.uuid4())
        response = requests.delete(
            f"{BASE_URL}/api/user/indicator-screener/saved-queries/{fake_id}",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 404


class TestIQ06WatchlistCRUD:
    """IQ-06: Watchlist CRUD - /watchlist GET/POST/DELETE"""

    def test_iq06_watchlist_add_list_delete(self):
        """Full CRUD flow for watchlist"""
        # CREATE
        create_payload = {
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "BTCUSDT",
            "note": f"test_iq06_{random_suffix()}",
        }
        create_response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            json=create_payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert create_response.status_code == 200, create_response.text
        created = create_response.json()
        watch_id = created["id"]
        assert created["symbol"] == "BTCUSDT"
        
        # READ (List)
        list_response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert list_response.status_code == 200, list_response.text
        items = list_response.json()
        assert any(item["id"] == watch_id for item in items)
        
        # DELETE
        delete_response = requests.delete(
            f"{BASE_URL}/api/user/indicator-screener/watchlist/{watch_id}",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert delete_response.status_code == 200, delete_response.text
        delete_data = delete_response.json()
        assert delete_data.get("deleted") is True

    def test_iq06_watchlist_delete_nonexistent_returns_404(self):
        """Delete non-existent watchlist item should return 404"""
        fake_id = str(uuid.uuid4())
        response = requests.delete(
            f"{BASE_URL}/api/user/indicator-screener/watchlist/{fake_id}",
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 404

    def test_iq06_watchlist_empty_symbol_returns_400(self):
        """Empty symbol should return 400"""
        create_payload = {
            "exchange": "binance",
            "market_type": "spot",
            "symbol": "",
            "note": "invalid",
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            json=create_payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 400


class TestIQ10ResponseContract:
    """IQ-10: Response contract validation"""

    def test_iq10_run_response_has_required_fields(self):
        """Run response should contain all required contract fields"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "1h",
            "query_expression": "rsi14 < 100",
            "symbol_universe": ["BTCUSDT", "ETHUSDT"],
            "limit": 10,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=120,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        # Contract fields
        assert "query_valid" in data
        assert "query_error" in data
        assert "evaluated_count" in data
        assert "match_count" in data
        assert "matched_symbols" in data
        assert "rows" in data
        
        # Row structure
        if data["rows"]:
            row = data["rows"][0]
            required_row_fields = [
                "index", "exchange", "market_type", "symbol", "timeframe",
                "close", "rsi14", "rsi7", "ema20", "ema50", "sma20", "sma50",
                "fibo_161_8", "fibo_127_2", "fibo_100", "fibo_78_6",
                "matched_rules", "matched_fields", "updated_at"
            ]
            for field in required_row_fields:
                assert field in row, f"Missing field: {field}"

    def test_iq10_invalid_query_still_returns_200_with_error_info(self):
        """Invalid query should return 200 with query_valid=False and query_error set"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "invalid_field < 10",
            "symbol_universe": ["BTCUSDT"],
            "limit": 10,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            headers=USER_HEADERS,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["query_valid"] is False
        assert data["query_error"] is not None
        assert data["match_count"] == 0
        assert data["evaluated_count"] == 0


class TestAuthRequired:
    """Authentication requirement tests"""

    def test_run_endpoint_requires_auth(self):
        """Run endpoint should require authentication"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "timeframe": "15m",
            "query_expression": "rsi14 < 30",
            "symbol_universe": ["BTCUSDT"],
            "limit": 10,
        }
        response = requests.post(
            f"{BASE_URL}/api/user/indicator-screener/run",
            json=payload,
            timeout=30,
        )
        assert response.status_code in [401, 403]

    def test_presets_endpoint_requires_auth(self):
        """Presets endpoint should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/presets",
            timeout=30,
        )
        assert response.status_code in [401, 403]

    def test_saved_queries_endpoint_requires_auth(self):
        """Saved queries endpoint should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/saved-queries",
            timeout=30,
        )
        assert response.status_code in [401, 403]

    def test_watchlist_endpoint_requires_auth(self):
        """Watchlist endpoint should require authentication"""
        response = requests.get(
            f"{BASE_URL}/api/user/indicator-screener/watchlist",
            timeout=30,
        )
        assert response.status_code in [401, 403]
