#!/usr/bin/env python3
"""
Stage 1 Read-Only Verification - Direct API Tests
Quick verification of all Stage 1 endpoints
"""

import os
import sys
import json
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"

def get_auth_token():
    """Get authentication token"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        else:
            print(f"Login failed: {response.status_code} - {response.text[:200]}")
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def test_endpoint(session, endpoint, name, expected_fields=None):
    """Test a single endpoint"""
    try:
        response = session.get(f"{BASE_URL}{endpoint}", timeout=30)
        status = response.status_code
        
        if status == 200:
            data = response.json()
            
            # Check expected fields if provided
            missing_fields = []
            if expected_fields:
                for field in expected_fields:
                    if field not in data:
                        missing_fields.append(field)
            
            if missing_fields:
                print(f"⚠️  {name}: 200 OK but missing fields: {missing_fields}")
                return {"status": "partial", "code": status, "missing": missing_fields}
            else:
                print(f"✅ {name}: 200 OK")
                return {"status": "pass", "code": status, "data_type": type(data).__name__}
        else:
            print(f"❌ {name}: {status}")
            return {"status": "fail", "code": status, "error": response.text[:100]}
    except Exception as e:
        print(f"❌ {name}: ERROR - {e}")
        return {"status": "error", "error": str(e)}

def main():
    print("=" * 60)
    print("Stage 1 Read-Only Verification Tests")
    print(f"Base URL: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Get auth token
    print("\n1. Authentication...")
    token = get_auth_token()
    if not token:
        print("❌ Authentication failed - cannot proceed")
        sys.exit(1)
    print(f"✅ Authentication successful")
    
    # Create session with auth
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    
    results = {}
    
    # Test Market Data endpoints
    print("\n2. Market Data Endpoints...")
    results["market_candles"] = test_endpoint(
        session, "/api/market/candles?symbol=BTCUSDT&timeframe=1h&market_type=futures",
        "Market Candles"
    )
    
    # Test User Live Dashboard endpoints
    print("\n3. User Live Dashboard Endpoints...")
    results["live_summary"] = test_endpoint(
        session, "/api/user/live/summary",
        "Live Summary",
        ["window", "generated_at", "bots", "open_positions", "performance", "risk", "execution", "strategies", "trades", "alerts"]
    )
    
    results["runtime_snapshot"] = test_endpoint(
        session, "/api/user/live/runtime-snapshot",
        "Runtime Snapshot",
        ["summary", "positions", "strategies", "trades", "queue", "decision_cards", "alerts"]
    )
    
    results["live_queue"] = test_endpoint(
        session, "/api/user/live/queue",
        "Live Queue",
        ["pending_orders", "pending_decisions", "queue_depth", "generated_at"]
    )
    
    results["live_risk"] = test_endpoint(
        session, "/api/user/live/risk",
        "Live Risk",
        ["window", "own_portfolio_exposure", "daily_loss_limit_pct"]
    )
    
    results["live_positions"] = test_endpoint(
        session, "/api/user/live/positions",
        "Live Positions",
        ["positions", "positions_count", "total_positions_count", "generated_at"]
    )
    
    results["live_performance"] = test_endpoint(
        session, "/api/user/live/performance",
        "Live Performance",
        ["window", "trades_today", "win_rate", "pnl_today"]
    )
    
    results["live_strategies"] = test_endpoint(
        session, "/api/user/live/strategies",
        "Live Strategies",
        ["window", "items", "strategy_count"]
    )
    
    results["live_trades"] = test_endpoint(
        session, "/api/user/live/trades",
        "Live Trades",
        ["window", "items", "trades_count"]
    )
    
    results["strategy_performance"] = test_endpoint(
        session, "/api/user/live/strategy-performance",
        "Strategy Performance (Backtest/Live)",
        ["window", "items"]
    )
    
    results["scheduler_next_run"] = test_endpoint(
        session, "/api/user/live/scheduler/next-run",
        "Scheduler Next Run",
        ["source", "auto_enabled", "interval_seconds"]
    )
    
    results["daily_report"] = test_endpoint(
        session, "/api/user/live/daily-report",
        "Daily Report",
        ["report_id", "date", "trades_today"]
    )
    
    results["execution_quality"] = test_endpoint(
        session, "/api/user/live/execution-quality",
        "Execution Quality",
        ["window", "own_execution_quality_score"]
    )
    
    # Test Decision Cards & Signals
    print("\n4. Decision Cards & Signals Endpoints...")
    results["decision_cards"] = test_endpoint(
        session, "/api/user/decision-cards",
        "Decision Cards"
    )
    
    results["signals"] = test_endpoint(
        session, "/api/user/signals",
        "User Signals"
    )
    
    results["scanner"] = test_endpoint(
        session, "/api/user/scanner",
        "Scanner Overview",
        ["mode", "total_results", "pending_signals"]
    )
    
    results["scanner_results"] = test_endpoint(
        session, "/api/user/scanner/results",
        "Scanner Results"
    )
    
    results["scanner_automation"] = test_endpoint(
        session, "/api/user/scanner/automation",
        "Scanner Automation",
        ["auto_enabled"]
    )
    
    results["signal_mode"] = test_endpoint(
        session, "/api/user/signal-mode",
        "Signal Mode",
        ["mode"]
    )
    
    # Test Execution Intents
    print("\n5. Execution Endpoints...")
    results["execution_intents"] = test_endpoint(
        session, "/api/user/execution/intents",
        "Execution Intents"
    )
    
    results["execution_positions"] = test_endpoint(
        session, "/api/user/execution/positions",
        "Execution Positions"
    )
    
    results["execution_presets"] = test_endpoint(
        session, "/api/user/execution/presets",
        "Execution Presets"
    )
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results.values() if r.get("status") == "pass")
    partial = sum(1 for r in results.values() if r.get("status") == "partial")
    failed = sum(1 for r in results.values() if r.get("status") in ["fail", "error"])
    total = len(results)
    
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Partial: {partial}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed + partial) / total * 100:.1f}%")
    
    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "summary": {
            "total": total,
            "passed": passed,
            "partial": partial,
            "failed": failed,
            "success_rate": f"{(passed + partial) / total * 100:.1f}%"
        },
        "results": results
    }
    
    with open("/app/test_reports/stage1_readonly_verification.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to /app/test_reports/stage1_readonly_verification.json")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
