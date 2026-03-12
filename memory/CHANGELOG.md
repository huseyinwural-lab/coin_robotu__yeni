# CHANGELOG — Algorithmic Trading Platform

## 2026-03-12
### Phase 5.1A — Futures Liquidation Protection + ADL Risk Shield
- Liquidation protection çekirdeği güncellendi ve contract-sınıf tabanlı hale getirildi:
  - LiquidationRiskAggregator
  - CascadeDetector
  - ProtectionPolicyEngine
  - EmergencyDeleverageExecutor
  - MarginUtilizationGuard
  - LiquidationGate
- ADL risk katmanı sıfırdan eklendi:
  - ADLRiskDetector
  - ADLPressureAggregator
  - ADLProtectionPolicy
  - ADLExposureReducer
  - ADLGate
- Servis zinciri deterministik karar akışına güncellendi:
  - snapshot -> liquidation -> cascade -> adl -> policy -> gate -> execution -> observability
- Yeni endpoint: `GET /api/admin/futures/adl/status`
- Genişleyen endpoint contractları:
  - `GET /api/admin/futures/risk/status` -> `policy_state`, `liquidation_risk_score`, `adl_risk_score`, `decision_trace`
  - `GET /api/admin/futures/liquidation-protection/status` -> ADL alanları + decision trace
- Frontend admin sayfası (`/admin/futures/liquidation-protection`) tamamlandı:
  - read-only badge
  - loading / empty / error state
  - ADL widgetları (gauge, pressure side, symbols, policy state)
  - decision trace paneli
- Sidebar'a `Liquidation Protection` linki eklendi.

### Test Sonuçları
- Self test: `pytest -q /app/backend/tests/test_phase5_liquidation_protection_adl.py` -> **7/7 PASS**
- Testing agent: `/app/test_reports/iteration_30.json` -> **PASS** (backend + frontend + regression)

### P1 — Futures Strategy Integration (Paper Mode)
- Yeni strategy contract: `FuturesStrategy` + `StrategySignal`
- Yeni strateji: `futures_trend_follow_v1` (signal-only)
- Yeni strategy engine chain: strategy -> microstructure -> risk -> liquidation -> ADL -> policy -> paper decision
- Yeni paper executor: synthetic lifecycle + paper pnl
- Yeni servis: `services/futures_strategy_service.py`
- Yeni admin endpointleri:
  - `POST /api/admin/futures/strategy/run-paper-cycle`
  - `GET /api/admin/futures/strategy/status`
- Admin `/admin/futures/risk-monitor` strategy section eklendi:
  - signal feed, decision trace, paper pnl chart, reject reasons, confidence distribution

### P1 Test Sonuçları
- Self test: `15/15 PASS`
- Testing agent: `/app/test_reports/iteration_31.json` -> **PASS** (backend + frontend + regression)
