# CHANGELOG — Algorithmic Trading Platform

## 2026-03-12
### FB-01 + FB-02 — Research Isolation + Legacy Finalization
- Research namespace oluşturuldu: `/app/research/{formulas,experiments,notebooks,excluded}`.
- Artefact üretim pipeline’ı eklendi: `python -m cli.generate_research_legacy_artifacts`.
- Üretilen ana dosyalar:
  - `/app/research/research_namespace_manifest.json`
  - `/app/research/formula_decomposition_18M.json`
  - `/app/research/excluded_formula_report.json`
  - `/app/reports/excluded_formula_report.json`
  - `/app/reports/legacy_formula_strategy_matrix.json`
  - `/app/reports/legacy_formula_integration_report.json`
  - `/app/strategies/active_formula_registry.json`
- Production gate eklendi:
  - Runtime allowlist: `core/execution/production_formula_gate.py`
  - Static import scan: `services/formula_gate_service.py`
  - CLI gate check: `python -m cli.production_formula_gate_check`
  - CI fail-fast scriptleri: `run_formula_gate_check.sh`, `ci_formula_gate.sh`
  - `ci_stage_gate.sh` ve `ci_prod_gate.sh` formula gate adımıyla güncellendi.
- Strategy registry runtime’da active registry allowlist ile filtrelenir hale getirildi.
- Testler:
  - Local: `15 PASS` (`test_fb01_fb02_isolation_artifacts.py`, `test_fb01_production_gate_checks.py`, vb.)
  - Testing agent: `/app/test_reports/iteration_48.json` => `12/12 PASS`
  - Validation report: `/app/test_reports/fb01_fb02_validation_report.json`

## 2026-03-12
### Phase L1 Core (Faz 1-3-5-6) — Legacy Formula Native Entegrasyon
- `formül.rar` extraction + canonicalization tamamlandı; `legacy_formula_registry.json` üretildi (BC01-BC04 + scanner aileleri).
- 4 native legacy strategy eklendi: `momentum_volume_breakout_v3`, `volatility_breakout_v2`, `adaptive_level_breakout_v2`, `oscillator_composite_reversion_v2`.
- 4 prefilter/scanner entry eklendi: `crypto_universe_prefilter_v1`, `volatility_contraction_prefilter`, `relative_strength_cluster_scanner_v2`, `relative_strength_cluster_scanner_v2_alt`.
- Governance/runtime entegrasyonu: legacy set **DISABLED + SHADOW_ONLY** lock, lifecycle seed, `allowed_total=0` (aktif order yok).
- Admin görünürlük eklendi (4 panel): strategy-analytics, strategy-governance, capital-governance, tail-risk.
- Yeni metrik kolonları: `family_code`, `source_type`, `shadow_status`, `signal_frequency`, `shadow_pnl`, `false_breakout_rate`, `confidence_drift`.
- Testler: yeni L1 test paketi + regresyonlar geçti; testing agent `iteration_45.json` PASS.

## 2026-03-12
### Admin Kullanıcı Ayrımı + Admin Ekle + Açık Yeşil Koyu Buton Teması
- Admin sidebar’a iki ayrı menü satırı eklendi:
  - `Admin Kullanıcıları` (`/admin/users/admins`)
  - `User Kullanıcıları` (`/admin/users/customers`)
- `AdminUsersPage` scope bazlı hale getirildi, user listesi onaylı user hesaplarıyla sınırlandı.
- Yeni backend endpoint: `POST /api/admin/users/admin-create` (admin panelden admin/ops oluşturma).
- `GET /api/admin/users` endpointine `scope=admin|user` desteği eklendi.
- Admin panelde siyah aksiyon butonları açık yeşil tona geçirildi (özellikle Yenile / Admin Ekle / Bulk Approve).
- Testler:
  - Backend: `test_phase6_admin_user_menu_scope.py` + phase6 regressions => **36 PASS**
  - Frontend otomasyon: menü ayrımı, admin create formu, buton rengi doğrulaması => **PASS**

## 2026-03-12
### Phase 6 / Faz-1 Görev-1 — User Registry + Auth Integration + Data Isolation
- `backend/core/users/user_registry.py` eklendi ve auth akışına entegre edildi.
- Self-register kullanıcılar için varsayılan policy kesinleşti: `role=user`, `approval_status=pending`, `is_active=false`.
- `/api/auth/*` login/register/approval akışı registry katmanına taşındı (davranış korunarak refactor).
- Backend owner-scope enforcement normalize edildi (admin rolleri + user veri izolasyonu):
  - `bot_profiles`, `risk_policies`, `paper_positions`, `pipeline`, `exchange`, `dashboard`
- `get_current_user` içinde approval-state doğrulaması defense-in-depth olarak güçlendirildi.
- Testler: `test_user_approval_flow.py` + yeni `test_phase6_user_registry_owner_scope.py` => **16 PASS**.

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

## 2026-03-12
### Phase 5.1B — Market Microstructure Guard
- Yeni microstructure modülleri eklendi (`core/futures/microstructure/*`)
- Yeni endpoint: `GET /api/admin/futures/microstructure/status`
- Strategy paper decision flow microstructure guard ile birleştirildi
- Yeni admin sayfası: `/admin/futures/microstructure-guard`
- Risk monitor/strategy akışı regression korunarak çalışır halde bırakıldı

### 5.1B Test Sonuçları
- Self test: `31/31 PASS`
- Testing agent: `/app/test_reports/iteration_32.json` -> **PASS**

## 2026-03-12
### Phase 5.2 — Futures Decision Trace Standard
- Decision core eklendi: trace model + reason taxonomy + attribution engine
- Paper decision flow tek standart chain ve tek reason_code üretimiyle güncellendi
- Yeni endpoint: `GET /api/admin/futures/decision-diagnostics`
- `/admin/futures/risk-monitor` içine diagnostics widgetları eklendi
  - false allow/reject
  - gate reason distribution
  - confidence vs outcome scatter
  - decision layer distribution

### 5.2 Test Sonuçları
- Self test: `74/74 PASS`
- Testing agent: `/app/test_reports/iteration_33.json` -> **PASS**

## 2026-03-12
### Phase 5.4 — Dynamic Leverage Model
- Leverage çekirdeği eklendi: confidence/microstructure/liquidation/funding/portfolio guard + birleşik leverage engine
- Paper decision flow chain’e `dynamic_leverage_engine` adımı eklendi
- Decision trace leverage alanlarıyla genişletildi (7 alan)
- Yeni endpoint: `GET /api/admin/futures/leverage/status`
- `/admin/futures/risk-monitor` leverage observability widgetları eklendi

### 5.4 Test Sonuçları
- Self test: `119 PASS`
- Testing agent: `/app/test_reports/iteration_34.json` -> **PASS**

## 2026-03-12
### Phase 5.5 — Controlled Testnet Hook (Initial Delivery)
- 10 execution çekirdek modülü + execution audit modülü eklendi
- Yeni endpointler: `/api/admin/futures/testnet/status`, `/api/admin/futures/testnet/release-gate`
- Yeni admin panel: `/admin/futures/testnet-control`
- Testnet default-off + release-gate enforced + live endpoint blocked davranışı doğrulandı

### 5.5 Test Sonuçları
- Self test: yeni testnet paketi + regression PASS
- Testing agent: `/app/test_reports/iteration_35.json` -> **PASS** (46/46)

## 2026-03-12
### Phase 5.5A — Execution Quality Analytics
- Yeni endpointler eklendi:
  - `GET /api/admin/futures/testnet/execution-quality`
  - `GET /api/admin/futures/testnet/execution-quality/rolling-7d`
- Execution analytics katmanı eklendi: slippage, fill latency, reject-rate, partial-fill quality, placement success, symbol quality
- 5 zorunlu çapraz geliştirme bu faza entegre edildi:
  - rolling 7d tuning score
  - symbol drift alarmı
  - false allow/reject karşılaştırma
  - gate reason trend analizi
  - 15 mimari hata checklist’i
- `/admin/futures/testnet-control` paneline tüm yeni analytics kartları eklendi

### 5.5A Test Sonuçları
- Testing agent: `/app/test_reports/iteration_36.json` -> **PASS** (25/25 backend, frontend panel PASS)
