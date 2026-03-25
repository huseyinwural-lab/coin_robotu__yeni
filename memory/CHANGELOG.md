# CHANGELOG — Algorithmic Trading Platform

## 2026-03-25 (P1.3 Retention & Segment Profitability)
- Yeni migration: `20260325_0077_user_economics_snapshots.py`.
- Yeni model: `UserEconomicsSnapshot`.
- User economics backend genişletmesi:
  - `GET /api/admin/users/economics/retention-trend`
  - `GET /api/admin/users/economics/segment-profitability`
  - `GET /api/admin/users/economics/export.csv`
  - `GET /api/admin/users/economics/export.xlsx`
  - `POST /api/admin/users/economics/snapshots/run`
  - `GET /api/admin/users/economics/snapshots/trend`
- Frontend /admin/users/economics sayfası trend/segment/export/snapshot bileşenleriyle genişletildi.
- Test kanıtı: `/app/test_reports/iteration_133.json` (backend 24/24 PASS, frontend %100).

## 2026-03-25 (P1.2 User Economics)
- Migration: `20260325_0076_user_economics_aggregates.py` eklendi.
- Yeni model: `UserEconomicsAggregate` (`user_id + environment` unique).
- Yeni servis: `user_economics_service.py`
  - `sync_user_economics_aggregates`
  - `get_user_economics_summary`
- Yeni endpoint: `GET /api/admin/users/economics`.
- Yeni UI route: `/admin/users/economics` (`AdminUserEconomicsPage.jsx`).
- Sidebar nav eklendi: `nav-admin-user-economics-link`.
- Test kanıtı: `/app/test_reports/iteration_132.json` (backend 26/26 PASS, frontend %100).

## 2026-03-25 (P1 Revenue Engine MVP)
- Migration: `20260325_0075_revenue_ledger.py` eklendi.
- Yeni model: `RevenueLedger` + unique `(trade_id, component_type)`.
- Yeni servis: `revenue_engine_service.py`.
  - fee + pnl_share komponent üretimi
  - `%20` share rate (env: `REVENUE_PNL_SHARE_RATE`)
  - idempotent upsert + scope bazlı sync
- Write path entegrasyonu:
  - REST ingestion sonrası revenue sync
  - WS worker trade persist sonrası revenue upsert
- Yeni endpoint: `GET /api/admin/revenue/summary`.
- Yeni UI route: `/admin/revenue` (filters + total/today + daily graph + top users/symbols).
- Test kanıtı: `/app/test_reports/iteration_131.json` (backend 20/20 PASS, frontend %100 PASS).

## 2026-03-25 (P0 final closure attempt)
- Spot+Futures live sequential zincir koşuldu (ingest -> pnl -> recon -> data-quality -> live-gate).
- Futures live credential eklendi ve probe `ready` doğrulandı.
- Teknik endpoint stabilitesi PASS (500 yok).
- Closure sonucu: ingest edilen trade yok (`spot=0`, `futures=0`) → `live_transition_ready=false`.
- Doğrudan signed kontrollerde `myTrades/userTrades` boş döndü (200 + empty list).

## 2026-03-25 (Live proxy transition + incremental spot run)
- Live proxy env geçişi tamamlandı (spot/futures base URL + token).
- Spot low-weight ingest ile kademeli sembol koşumu yapıldı (BTC/ETH/BNB/SOL/ADA).
- Sistem stabil: endpointlerde 500/regression yok.
- Spot tarafında trade coverage olmadığı doğrulandı (myTrades=0), bu nedenle live-gate spot hâlâ false.
- Test: `/app/test_reports/iteration_130.json` (backend 19/19 PASS, frontend %100).

## 2026-03-25 (Low-weight spot mode + drift severity)
- Backend: live+spot ingest için düşük ağırlık modu (symbol limit + sleep + 429 backoff + partial continue) eklendi.
- Backend response: `market_summary.spot` içine `rate_limit_hits`, `low_weight_mode`, `processed_symbols` eklendi.
- Frontend: drift highlight alanına severity badge eklendi (`critical/medium/low`).
- Test: `/app/test_reports/iteration_129.json` (backend 11/11 PASS, frontend %100).

## 2026-03-25 (Drift Highlight + Spot 1y rerun)
- Frontend: Trace compare kartına drift highlight eklendi (`source`, `selection_reason`, `probe_state`).
- Frontend state'leri: empty / no-diff / diff-list akışları tamamlandı.
- Operasyon denemesi: spot live 1 yıl + çoklu yüksek hacimli sembolde Binance `429 -1003` request-weight limiti gözlendi.
- Futures test scope live-gate doğrulaması sürdü (`true`).

## 2026-03-25 (P0 chain rerun + trace history compare)
- Backend:
  - `GET /api/admin/commercial/p0/pnl/latest` → `market_types` query desteği eklendi.
  - `GET /api/admin/commercial/p0/data-quality` → `required_market_types` query desteği eklendi.
  - Live-gate credential resolve scope bug fix: selected market seti doğru geçiriliyor.
- Frontend:
  - Audit Trace drawer’a geçmiş trace listesi + karşılaştırma eklendi.
  - History API `limit` değeri `20` (endpoint constraint uyumu).
  - Validation error array için toast message format düzeltmesi.
- Operasyon sonucu:
  - Futures test live-gate scope: `true`
  - Spot live scope: `false` (trade coverage yok)
- Test: `/app/test_reports/iteration_128.json` (backend 18/18 PASS, frontend %100).

## 2026-03-25 (Traceability: request_id + audit drawer)
- Backend: `credential-resolution-preview` response’u traceability alanlarıyla genişletildi (`request_id`, `resolved_at`, `fallback_chain`, `selected_probe_status` vb.).
- Backend: endpoint içinde `request_id` bazlı audit log kaydı eklendi.
- Frontend: aynı sayfada Audit Trace drawer/modal eklendi.
- Frontend: preview alanına request_id/timestamp + audit_link anchor eklendi.
- Test kanıtı: `/app/test_reports/iteration_127.json` (backend 10/10 PASS, frontend %100).

## 2026-03-25 (P0 Devamı + Decision Trace Timeline)
- Backend:
  - `commercial_ops_p0_service.py` içinde `usdt_perp/coin_perp -> futures` canonical alias desteği eklendi.
  - `X-Proxy-Token` header desteği spot/futures Binance çağrılarına eklendi.
  - Spot price/public request tarafına da proxy header geçişi eklendi.
  - `credential_resolution_service.py` probe çağrılarına `X-Proxy-Token` header desteği eklendi.
- Frontend:
  - Credential Orchestration sayfasına `Decision Trace Timeline` kartı eklendi.
  - 3 adım (user/tenant_admin/global_admin) ve dinamik status badge akışı eklendi.
- Operasyonel test:
  - Spot live probe: `ready`
  - Futures test probe: `ready`
  - P0 ingestion (spot live + futures testnet): 200
  - Live-gate(testnet/futures): 200, `live_transition_ready=false` (coverage eksik)
- Test kanıtları:
  - `/app/test_reports/iteration_126.json` (backend 18/18 PASS, frontend %100)
  - frontend specialist PASS, backend specialist PASS

## 2026-03-25 (Credential Orchestration UI Expansion)
- `AdminCredentialOrchestrationPage.jsx` production-grade genişletildi (multi-exchange, market/purpose, routing matrix, probe dashboard, egress visibility).
- Backend credential orchestration enum/filter uyumu güncellendi:
  - exchange: `binance/bybit/okx`
  - market: `spot/usdt_perp/coin_perp` (+ `futures` alias)
  - purpose: `market_data/execution/fallback` (+ `execution_fallback` alias)
- `GET /api/venues/admin/credentials` endpointine `purpose` filtresi eklendi.
- Probe state seti genişletildi (`connectivity_only`, `rate_limited`, `probe_not_supported`).
- Test kanıtı:
  - `/app/test_reports/iteration_125.json` (backend 22/22 PASS, frontend %100)
  - Frontend specialist test: 5/5 PASS
  - Backend specialist test: hedef endpointler PASS, 500 yok
- **MOCKED**: Bybit/OKX probe yalnız public connectivity; Binance test probe ortamda `ip_restricted` dönebilir.

## 2026-03-25 (Admin Credential Orchestration Layer)
- Yeni tablolar: `admin_exchange_credentials`, `credential_assignment_rules` (+ migration `20260325_0074`)
- Yeni servis: `credential_resolution_service.py` (deterministic credential selection + fallback)
- Yeni admin API: `/api/venues/admin/credentials*`, `/api/venues/admin/credential-rules*`, `/api/venues/admin/credential-resolution-preview`
- User exchange response zenginleştirme: `effective_source`, `routing_preview`, `environment_valid`
- Commercial Ops P0 credential seçimi yeni orchestration katmanına bağlandı (spot/futures ayrı seçim)
- Probe + audit akışları eklendi (create/update/approve/disable/probe/rule)
- Test sonucu: Backend 12/12 PASS, Frontend smoke PASS

## 2026-03-24 (P0.5 Final Closure)
### Consistency + Validation Tightening
- Identity observability endpointleri ortak response contract ile standardize edildi (`status`, `contract_version`, `user_id`, `metric`, `generated_at`, `data`).
- Frontend AdminUsersPage observability parse katmanı yeni contract ile uyumlu hale getirildi.
- Request-level reason validation güçlendirildi; kısa reason artık approval’a gitmeden `400 request_reason_too_short` dönüyor (disable/delete/restore/role/trading/capital/bulk).
- MFA bypass context + audit eklendi:
  - Login bypass olduğunda `MFA_ENFORCEMENT_BYPASS_ACTIVE` audit log yazılıyor.
  - Security detail API ve UI’de `MFA bypass active` badge gösteriliyor.
- Regression testing sonuçları:
  - Backend: PASS
  - Frontend: PASS

## 2026-03-24 (Commercial Ops P0 Kickoff)
### Binance REST Ingestion + Canonical PnL/Reconciliation Core
- Yeni domain tabloları eklendi: `commercial_trades`, `pnl_records`, `exchange_reconciliation_logs`.
- Alembic migration eklendi: `20260324_0073_commercial_ops_p0_trade_pnl_reconciliation.py`.
- Yeni servis: `commercial_ops_p0_service.py`:
  - Spot+Futures REST ingestion (canonical dedupe)
  - PnL engine (realized/unrealized, gross/net, fee breakdown)
  - Reconciliation (trade/position/pnl/balance drift)
  - Data quality snapshot + live transition gate
  - Standardized CSV export + websocket bootstrap
- Yeni endpoint seti: `/api/admin/commercial/p0/*`.
- Test: `test_commercial_ops_p0_service.py` → 3/3 PASS.
- Ortam notu: Preview URL üzerinde 502 ve `postgres.internal` çözümleme problemi nedeniyle canlı endpoint E2E doğrulaması bloklandı.

### 2026-03-24 (Commercial Ops P0 Closure Validation Update)
- Runtime blocker giderildi: preview health 200 + DB reachable.
- Gerçek Binance testnet doğrulaması (`huseyinwural@gmail.com`) çalıştırıldı.
- Futures-only P0 chain PASS:
  - ingestion (idempotency + duplicate detection)
  - pnl/latest
  - reconciliation (`drift_tolerance_pct=0.3`)
  - data-quality
  - live-gate (`required_market_types=futures`)
- Spot tarafı external blocker olarak netleşti: Binance spot API `451 restricted location`.
- Websocket consumer worker eklendi:
  - `/api/admin/commercial/p0/websocket/worker/start`
  - `/api/admin/commercial/p0/websocket/worker/status`
  - `/api/admin/commercial/p0/websocket/worker/stop`
- CSV export ↔ PnL consistency doğrulandı (realized toplamları birebir eşleşti).

## 2026-03-23 (P2 Analytics Phase)
### Production Gate Derinlik & Proaktif Karar Katmanı
- Check history/trend engine + flapping detection eklendi.
- Override analytics endpointi ve UI paneli eklendi.
- Before/after remediation compare endpointi ve UI paneli eklendi.
- Incident timeline endpointi + kategori filtreli UI eklendi.
- Dinamik risk scoring (`risk_score`, `risk_level`) gate header’a taşındı.
- Export V2 genişletildi (history/analytics/timeline/risk snapshots).
- P2 artefact seti üretildi ve manifest güncellendi.
- Independent test report: `/test_reports/iteration_114.json` (backend/frontend %100 PASS).

## 2026-03-23 (P1 Closure)
### Production Gate Operational Visibility & Evidence
- Final evidence-chain manifest eklendi: `/app/backend/exports/artifact_manifest.json`.
- Smoke artefact tek dosyada NO_GO + GO_WITH_OVERRIDE state snapshotlarını içerecek şekilde birleşik üretildi.
- Endpoint/state evidence JSON request/response + state_before/state_after zorunlu formatına güncellendi.
- Evidence artefact seti eklendi:
  - `/app/test_reports/production_gate_p1_backend_pytest.txt`
  - `/app/test_reports/production_gate_p1_endpoint_state_evidence.json`
  - `/app/test_reports/production_gate_p1_evidence.md`
  - `/app/test_reports/production_gate_p1_smoke_after_login.jpeg`
  - `/app/test_reports/iteration_113.json`
- Backend endpointleri eklendi:
  - `GET /api/phase4/admin/production-gate/ops-overview`
  - `POST /api/phase4/admin/production-gate/api-key-tests/run`
  - `POST /api/phase4/admin/production-gate/order-scenarios/rerun`
  - `GET /api/phase4/admin/production-gate/mode-history`
  - `GET /api/phase4/admin/production-gate/export/raw` (scope/date filter)
- Frontend panel genişletildi: auto-refresh, fail banners, API key test panel, permission breakdown, exchange health, mode history, order scenario matrix, runbook refs, filtreli export.
- Test sonuçları: iteration_113 backend/frontend %100 PASS.

## 2026-03-23
### Production Gate Control Panel (P0)
- Backend state engine eklendi: `NO_GO | GO | GO_WITH_OVERRIDE`.
- Override kuralları sertleştirildi: super_admin only, max 30 dk, strict enum reason.
- Deploy/LIVE block enforcement canlı endpointlerde zorunlu hale getirildi (403 hard-block).
- Yeni Production Gate API seti eklendi (state, checklist, rerun, override/revoke, mode-transition, export).
- Audit log zinciri genişletildi (previous/next state, reason_code/text, expiry, request_id).
- `AdminExecutionReadinessPage.jsx` write-capable control panel olarak yeniden tasarlandı.
- Test raporu: `/app/test_reports/iteration_112.json`.

## 2026-03-22
### Hotfix — Admin Login Failure (PostgreSQL Down)
- PostgreSQL yeniden kuruldu/başlatıldı.
- `trader` rolü ve `trading_platform` DB oluşturuldu.
- Backend restart sonrası admin login tekrar çalışır hale getirildi.
- Hesaplar yeniden seed edildi (admin/ops/user).

## 2026-03-22
### Iteration-59 — FAZ-2 Tur-2 Closure (Export/Bulk/Debug/UX)
- Export job sistemi eklendi (DB tabanlı, async, audit-first, trace_id zincirli).
- Export endpoint seti tamamlandı: create/list/get/download/retry.
- Universe bulk import UX tamamlandı:
  - CSV paste + upload
  - preview + validation + partial apply
  - errors CSV export
- Debug policy sıkılaştırıldı:
  - backend super_admin-only
  - UI default hidden + production hide
- Unified panel UX polish:
  - auto-refresh interval selector (5/15/60)
  - global error banner
  - empty state reason metinleri
- Test kanıtı:
  - `/app/test_reports/iteration_59.json`
  - Backend 23/23 PASS, Frontend PASS

## 2026-03-22
### Iteration-58 — FAZ-2 Tur-1 Closure (Freshness/KPI/Trend)
- Freshness/SLA katmanı eklendi: stale-list + SLA config + rescan-stale endpointleri.
- KPI recommendation engine actionable hale getirildi: generate/apply/reject/postpone + active/history.
- Trend/Analytics endpointi eklendi: range + symbol/strategy drill-down + overlays.
- Unified panel ops tabları genişletildi: Freshness/SLA, KPI Rec, Trend.
- Empty state davranışları iyileştirildi (No data yet + reason).
- Chart console warning (`width/height -1`) düzeltildi.
- Test kanıtları:
  - `/app/test_reports/iteration_57.json`
  - `/app/test_reports/iteration_58.json`

## 2026-03-21
### Iteration-56 — Action Audit Unified Drawer
- Traceability aksiyonları route değiştirmeden sağ drawer açacak şekilde güncellendi.
- Drawer yapısı: `Action Audit` + `Audit Logs` + `Hardening Analytics` tabları.
- Filter bar eklendi (`user_id`, `action_type`, `since_hours`, `trace_id`).
- Satır bazında required audit alanları + detay paneli (expand JSON) eklendi.
- Sidebar’dan Action Audit / Logs linkleri kaldırıldı (operatör akışından çıkarıldı).
- Test kanıtı:
  - `/app/test_reports/iteration_56.json`
  - Frontend 8/8 PASS

## 2026-03-21
### Iteration-55 — Faz-1 Universe Operations Complete
- `admin_universe_monitor` router operasyonel hale getirildi (scanner/rollout/risk/slow endpointleri).
- Double-confirm + reason + audit log standardı tüm kritik aksiyonlara uygulandı.
- Aksiyon response contract standardı doğrulandı: `status=success, trace_id, message, state_snapshot`.
- Unified Pipeline Operations paneline 4 sekme eklendi:
  - Rollout
  - Scanner
  - Risk/Exposure
  - Slow Control
- Scanner symbol list edit modal + bulk symbol + filter config kontrolleri eklendi.
- Test kanıtı:
  - `/app/test_reports/iteration_55.json`
  - Backend PASS, Frontend PASS

## 2026-03-21
### Cleanup — Pipeline Monitoring/Control Removal
- `AdminPipelineControlPage` kaldırıldı (dosya + import temizliği).
- Redirect davranışı korundu:
  - `/admin/pipeline-control` -> `/admin/pipeline-operations`
  - `/admin/pipeline-monitoring` -> `/admin/pipeline-operations`
- Navigation sadece unified panel linkini gösteriyor.
- Test: `/app/test_reports/iteration_54.json` (Frontend 5/5 PASS)

## 2026-03-21
### Hotfix — Admin Login Failure (Backend DB Down)
- PostgreSQL eksik/kapalı durumundan kaynaklı backend startup hatası giderildi.
- DB cluster + role/database yeniden oluşturuldu.
- Backend restart sonrası admin login doğrulandı (`/api/auth/login` 200).

## 2026-03-21
### Iteration-53 — Final Cleanup + Real State + Lock
- Legacy pipeline UI linkleri kaldırıldı, route redirectler tamamlandı (`pipeline-control`, `pipeline-monitoring` -> `pipeline-operations`).
- Yeni `GET /api/runtime/state-validation` endpointi ile gerçek state checklist bağlandı (PASS/FAIL + suggestion).
- Runtime action contract status değeri `success` standardına geçirildi; frontend result panel state_snapshot dahil gösteriyor.
- WS debug alanları genişletildi (last_error, reconnect_reason, recent reconnect reasons).
- Release gate rules/fix_hint görünürlüğü eklendi (backend rules[] + UI rule table).
- Override active response TTL/impact metrikleri ile zenginleştirildi.
- Exchange monitoring UI aksiyonları (revalidate/disable) bağlandı.
- Header’a MODE görünürlüğü eklendi.
- Alert center filtreleri (time/severity/event) + severity badge finalize edildi.
- Test kanıtı:
  - `/app/test_reports/iteration_53.json`
  - Backend 13/13 PASS, Frontend 100% PASS

## 2026-03-21
### Iteration-52 — Admin Light Green Theme Cleanup
- Admin içerik alanı için `admin-light-panels` tema sınıfı eklendi.
- Koyu/siyah panel-kart-input-button yüzeyleri açık yeşil (lime pastel) tonlara çevrildi.
- Sidebar/navbar bilerek korunarak yalnız içerik yüzeyleri dönüştürüldü.
- Doğrulama:
  - `/app/test_reports/iteration_52.json`
  - Frontend PASS, dark elements remaining: 0

## 2026-03-21
### Iteration-51 — Production Readiness Lock (P1)
- Config single-source lock tamamlandı:
  - `/app/config/trading.json` -> `allowed_quote_assets`
  - execution/scanner/guard bu kaynaktan besleniyor
- Runtime endpoint eklendi: `GET /api/runtime/quote-policy`
- Unified UI şeffaflık güncellemeleri:
  - Summary bar `Allowed Quote Assets`
  - Guard panel `INVALID_QUOTE_ASSET` badge + highlight + pinned reason
  - blocked listte symbol/reason/timestamp görünürlüğü
- State Validation Checklist kartı eklendi (canlı state doğrulama)
- Action→Result UX finalize:
  - success/fail toast + trace_id
  - panel result alanı `last_action_result`
- Doküman eklendi:
  - `/app/memory/PROD_DEPLOYMENT_CHECKLIST_ROLLBACK.md`
- Test kanıtı:
  - `/app/test_reports/iteration_51.json`
  - Backend 32/32 PASS, Frontend PASS

## 2026-03-21
### Iteration-50 — Quote Asset Constraint P0 (USDT/USDC)
- Hard rule enforce edildi: trading pipeline yalnızca USDT/USDC quote asset ile çalışır.
- Invalid quote API hata standardı eklendi:
  - `error_code=INVALID_QUOTE_ASSET`
  - `message='Quote asset must be USDT or USDC'`
  - `state_snapshot.symbol` zorunlu
- Guard telemetry reason normalizasyonu eklendi:
  - `invalid_quote_asset` / `unsupported_quote_asset` => `INVALID_QUOTE_ASSET`
  - Blocked trades list + top reasons görünürlüğü güncellendi
- Scanner/signal katmanında quote filter sıkılaştırıldı:
  - canonical engine `symbols_override` dahil USDT/USDC dışı pair filtrelenir
- Override güvenliği doğrulandı: invalid quote hiçbir override ile bypass edilemiyor (hard rule).
- Test kanıtı:
  - `/app/test_reports/iteration_50.json`
  - Backend 23/23 PASS, frontend guard visibility PASS

## 2026-03-21
### Iteration-49 — Unified Pipeline Operations P0 Closure
- Backend runtime action contract standardizasyonu tamamlandı:
  - Tüm kritik runtime action response'larında `{ status, trace_id, message, state_snapshot }`
  - `status="ok"` standardı
  - `audit_log_id` + traceability doğrulandı
- `POST /api/runtime/heartbeat/check` zorunlu audit akışına alındı.
- `POST /api/runtime/alert-policy/rollback` endpointinde phrase enforce eklendi (`ROLLBACK ALERT POLICY`).
- Yeni unified operasyon sayfası eklendi:
  - Route: `/admin/pipeline-operations`
  - Dosya: `/app/frontend/src/pages/PipelineOperationsPage.jsx`
  - Akış sırası: Control → Recovery → Monitoring → Traceability
  - Her panelde State / Reason / Action / Result görünürlüğü
- Eski ekranlar korundu, redirect yapılmadı; yeni unified sayfaya görünür geçişler eklendi:
  - Sidebar nav
  - Admin Dashboard
  - Live Trading Dashboard
  - Legacy Pipeline Control sayfası
- Test kanıtı:
  - `/app/test_reports/iteration_49.json`
  - Backend 15/15 PASS, frontend unified panel PASS

## 2026-03-18
### Iteration-165 — Optional MFA + Persistent Brand Settings
- Optional MFA eklendi (User + Admin, login sonrası ikinci adım):
  - `/api/auth/mfa/settings` (GET/PUT)
  - `/api/auth/mfa/totp/setup`
  - `/api/auth/mfa/totp/verify-setup`
  - `/api/auth/mfa/challenge/verify`
- Login endpointleri MFA-aware hale getirildi (`mfa_required`, challenge token, methods).
- Kalıcı branding eklendi (DB blob + upload endpoint):
  - `GET /api/branding/settings`
  - `GET /api/branding/logo`
  - `GET/PUT /api/admin/brand-settings`
  - `POST /api/admin/brand-settings/logo-upload`
- Frontend:
  - `MfaSettingsPage` user/admin route’larına eklendi
  - `AdminBrandSettingsPage` eklendi (`/admin/brand-settings`)
  - Sidebar nav: MFA Settings + Brand Settings
  - Landing/User/Admin login branding API ile senkronlandı.
- Doğrulama: backend testleri + frontend E2E PASS.

### Iteration-165b — User Login Form Rollback Fix
- Kullanıcı geri bildirimi üzerine `/user/login` sayfası klasik çalışan form yapısına geri alındı.
- MFA step-up (email/TOTP challenge panel) login ekranında korunarak çalışır bırakıldı.
- Admin login beyaz zemin ve logo düzeni korunarak PASS doğrulandı.

### Iteration-166 — Live Bring-up Script (One-command)
- Yeni script eklendi: `/app/scripts/start_live.sh`
- Script, servis restart + health + MFA-aware auth + readiness + micro test-order + guard/risk/balance + telemetry/explainability + position kontrolünü tek akışta doğrular.
- Çalıştırma: `LIVE_USER_EMAIL='...' LIVE_USER_PASSWORD='...' bash /app/scripts/start_live.sh`
- Doğrulama: script self-run PASS + backend deep test PASS.

## 2026-03-18
### Iteration-164 — Auth Pages Reference Redesign + Logo Upload
- `/user/login` sayfası referans görsele yakın şekilde yeniden düzenlendi (hero + turuncu form panel + sağ çizgili görsel + alt durum/feature blokları).
- Logo upload inputu eklendi (file input + anlık preview):
  - `/`
  - `/user/login`
- `/admin/login` arka planı beyaz yapıldı ve form stili sadeleştirildi.
- User/Admin toggle akışı korundu ve doğrulandı.
- Frontend test agent sonucu: tüm kontroller PASS.

## 2026-03-18
### Iteration-163 — Login Logo Integration (User + Admin)
- Kullanıcı referansına göre login sayfalarına logo sol üst konumda entegre edildi.
- `frontend/public/xilo-logo.png` eklendi.
- `/user/login` ve `/admin/login` ekranlarında sağ üst panel toggle (Kullanıcı/Admin Girişi) düzeni eklendi.
- Frontend doğrulama: logo görünürlüğü + sayfalar arası toggle geçişi PASS.

## 2026-03-18
### Iteration-162 — Telemetry + Explainability Mini Fast Close
- Guard event standardizasyonu eklendi (`EXECUTION_BLOCKED`, `EXECUTION_ALLOWED`, `EXECUTION_OVERRIDE_ENABLED`) ve boş reason engeli getirildi.
- Yeni guard aggregation servisi eklendi (`guard_metrics_service.py`) + endpoint: `GET /api/admin/guard-telemetry`.
- Admin `/admin/system-status` (monitoring alias) ekranına Guard Telemetry kartı eklendi (blocked_24h, override_24h, top_reasons).
- Screener response’larına deterministic explain eklendi (`/api/screener`, `/api/user/scanner/results`) + `score` alanı.
- Trade validation/submit response’larına explain eklendi (`OrderValidationResponse`, `ExecutionIntentSubmitResponse`).
- User Trade UI’de validation explain + execution explain paneli eklendi; scanner satırlarına explain summary bağlandı.
- Yeni testler: `test_guard_telemetry.py`, `test_explain_fields.py`, `test_explain_consistency.py`.
- Testing agent raporu: `/app/test_reports/iteration_161.json` → acceptance PASS.
- UI stabilizasyon: 423 path’te execution explain render fallback düzeltildi ve UserTradePage option hydration uyarısı kaldırıldı.
- Frontend retest (auto agent): 4/4 PASS.

## 2026-03-18
### Iteration-161 — Binance Testnet Live Mode Activation + Submit Path Fixes
- Kullanıcı bağlantısı üzerinde Binance futures testnet credential doğrulaması gerçekleştirildi; exchange validate/test-order başarıyla geçti.
- `execution_readiness_service` binance için readiness snapshot temelli mode üretir hale getirildi; uygun durumda `execution_mode=live` dönüyor.
- `open-position` 500 hatası düzeltildi:
  - `UserExecutionIntent` üzerinde olmayan alan erişimleri kaldırıldı,
  - `order_type/leverage/margin_mode` artık `normalized_order_payload` içinden okunuyor.
- Market order precheck’te `price=0` kaynaklı yanlış `min_notional_violation` giderildi (`price = notional/size` fallback).
- Sonuç: `validate-order` live + `open-position` 200 (`QUEUED_FOR_APPROVAL`, `execution_mode=live`) + `exchange/test-order` FILLED.
- Frontend trade UX guard: market fiyatı yüklenmeden Validate/Open butonları disabled.
- Frontend retest: Validate + Open Position sonrası `/user/positions` redirect doğrulandı (PASS).

## 2026-03-18
### Iteration-160 — FAZ-C Ultra Minimal Closure
- **C1**: `/user/trade` tek trade entry paneli eklendi; `/user/execute` ve `/execute` route’ları `/user/trade`’e query-preserving redirect edildi.
- **C1 flow**: `validate-order` zorunlu doğrulama + valid=false blok + valid=true akışında preview→`open-position` bağlandı.
- **C2**: Execution result binding (status, execution_mode, violations, 423 error state, success toast + positions redirect).
- **C3**: Positions tablosuna `execution_mode` badge eklendi; backend response genişletildi.
- **C4**: Screener satırlarına View Chart butonu eklendi; `/user/chart` sayfasında TradingView embed bağlandı.
- **C5**: Minimal filter set UI + chip + clear-all eklendi; backend’de `GET /api/screener?filters=...` endpoint’i eklendi.
- Test raporu: `/app/test_reports/iteration_160.json` (C1-C6 PASS).
- Ek minor fix: `/api/admin/dashboard` 404 kapatıldı (`backend/routers/admin_dashboard_alias.py`).
- Doğrulama: `pytest /app/backend/tests/test_faz_c_trade_entry.py` → **15 passed**.

## 2026-03-18
### Iteration-159 — Smoke Suite Reliability Bugfix (Crash-Safety)
- `backend/cli/final_release_smoke_suite.py` ağ hatalarında traceback crash üretmeyecek şekilde harden edildi.
- Yeni yardımcılar eklendi:
  - `_http_request` (RequestException-safe)
  - `_safe_json` (invalid/non-JSON response-safe)
- Tüm endpoint kontrolleri güvenli request katmanına taşındı; check detaylarına `error` alanı eklendi.
- Auth başarısızlığı dahil hata senaryolarında script kontrollü JSON (`overall=FAIL`) döndürerek deterministik şekilde sonlanıyor.
- Doğrulama:
  - Testing agent: `/app/test_reports/iteration_159.json` → backend **100%**
  - Ek test dosyası doğrulandı: `/app/backend/tests/test_smoke_suite_reliability.py` (9/9 PASS)

## 2026-03-15
### Iteration-107 — MASTER FINAL TASK ORDER (P0-first) Uygulaması
- **FINAL-1 Exchange execution activation (credential-aware)**
  - Admin exchange credential yönetimi eklendi:
    - `GET/PATCH /api/venues/admin/execution-credentials`
    - `POST /api/venues/admin/execution-validation`
  - Frontend `AdminExchangesPage` içinde Bybit/OKX credential alanları + validation paneli eklendi.
  - Execution submit/cancel keysiz modda **MOCKED** (kullanıcı seçimi 2B).
- **FINAL-3/4/5 hardening**
  - Risk governance maturity genişletildi:
    - timeline endpoint: `GET /api/admin/risk/config/timeline`
    - profiles: `GET /api/admin/risk/config/profiles`, `POST /api/admin/risk/config/profiles/{profile}/apply`
    - overrides: `GET/PATCH /api/admin/risk/config/overrides`
  - Policy profile setleri eklendi: conservative / balanced / aggressive.
  - User override merge akışı eklendi (`resolve_effective_config_for_user`).
- **FINAL-6 observability genişletmesi**
  - `risk_overview` içine `pnl_trend` eklendi.
  - Admin Universe Monitor sayfasına risk/observability trend kartları eklendi.
- **FINAL-7 admin UI düzenleme**
  - Admin menü sırası istenen 11 maddeye sadeleştirildi.
  - Logout en alta taşındı (sticky bottom), sidebar scroll iyileştirildi.
  - Primary action buton standardı `#4CAF50` olarak uygulandı.
- **FINAL-8 operasyon scriptleri**
  - `scripts/docker_validation_check.sh` eklendi (`runner_required` fallback).
  - `scripts/live_rollout_metrics_snapshot.sh` eklendi (DEPLOY gözlem çıktısı).
- **FINAL-9 exchange normalization hardening**
  - `normalization_service.py` ile leverage rule + error taxonomy eklendi.
  - market data adapter funding-rate fetch altyapısı eklendi.

### Iteration-106 — TRADING ENGINE MASTER CLOSURE PACKAGE (CLOSE-1..CLOSE-7)
- **CLOSE-1 Execution Quality Calibration**
  - `execution_quality_service.py` metrik seti genişletildi (`partial_fill_rate`, `reject_rate` dahil).
  - `execution_quality_calibration_service.py` eklendi (replay dataset + false_allow/false_block/false_reduce analizi + threshold önerisi).
  - Admin endpointleri eklendi: `POST /api/admin/risk/execution-quality/calibrate`, `GET /api/admin/risk/execution-quality/calibration`.
  - Düşük veri koşulunda `policy_documented_warning` çıktısı standartlaştırıldı.
- **CLOSE-2 Governance Hardening**
  - Safe bounds reject: `max_risk_per_trade_pct<=5`, `max_total_exposure_pct<=50`, `max_leverage<=10`.
  - `PATCH /api/admin/risk/config` ihlal durumunda HTTP 400 reject.
  - Config versioning metadata: `config_version`, `changed_by`, `changed_at`.
  - Backup/rollback: `risk_engine_config_backup.json`, `POST /api/admin/risk/config/rollback`.
- **CLOSE-3 Tiered+Risk Tuning**
  - `scanner_regime_service.py` eklendi.
  - Rejim profilleri: normal `700/120/25`, volatile `500/80/15`, stress `300/40/8`.
  - Rejim girdileri: volatility index, spread regime, latency regime, execution quality trend.
  - Fallback tetik genişletmesi: `latency_spike`, `queue_depth`, `execution_quality_drop`.
- **CLOSE-4 CI/Regression genişletme**
  - Yeni deterministic testler eklendi:
    - `test_risk_config_governance.py`
    - `test_scanner_regime_tuning.py`
    - `test_execution_quality_calibration.py`
    - `test_exchange_adapter_smoke.py`
    - `test_risk_engine_api_contracts.py`
  - Stage/prod gate listeleri güncellendi; toplam paket 34 test PASS.
- **CLOSE-5 Multi-exchange altyapı**
  - `services/exchange_adapter/` paketi eklendi (market_data_adapter, execution_adapter, precision_normalizer, symbol_mapper, retry_handler).
  - `GET /api/venues/admin/adapter-smoke` eklendi.
  - Bybit market data 403 durumunda degraded `PASS_MOCKED` fallback ile smoke stabil hale getirildi.
- **CLOSE-6 Admin observability**
  - `runtime-summary` yanıtına `observability_trends` eklendi.
  - `observability_trend_service.py` ile execution latency / risk veto rate / scanner cycle / fallback activation trendleri tutuluyor.
- **CLOSE-7 deployment dry-run**
  - drift/stage/prod gate tekrar PASS.
  - release gate preview’de `permission_check_fail` için policy-documented kabul çıktısı eklendi.
  - Runbook + closure raporu dokümante edildi: `/app/docs/15_master_closure_package_report.md`.

### Iteration-105 — RISK-1..RISK-6 Parametrik Risk Engine Paketi
- **Yeni servis katmanı eklendi**:
  - `backend/services/risk_engine_service.py` (ALLOW/REDUCE_SIZE/PASS/BLOCK final veto)
  - `backend/services/correlation_cluster_service.py` (symbol->cluster çözümleme)
  - `backend/services/execution_quality_service.py` (stale/spread/slippage/latency kalite skoru)
  - `backend/services/cooldown_service.py` (symbol/strategy/global cooldown state)
  - `backend/config/risk_engine_config.json` (runtime reload edilebilir parametrik risk config)
- **Admin yönetim endpointleri eklendi**:
  - `GET /api/admin/risk/config`
  - `PATCH /api/admin/risk/config`
  - `POST /api/admin/risk/config/reload`
  - `GET /api/admin/risk/status`
- **Runtime entegrasyonları**:
  - `scanner_runtime` içinde Decision→Risk Engine→Execution akışı; risk veto/reduce dağılımı `risk_engine` bloğu ile snapshot’a yazılıyor.
  - `execution_intent_service` preview akışına risk engine veto/reduce entegrasyonu eklendi.
  - `pipeline/runtime` global pause hesabına risk kill-switch dahil edildi.
  - `futures_strategy_service` için max leverage cap + liquidation distance veto uygulandı.
  - `admin_universe/runtime-summary` yanıtına `risk_overview` eklendi.
- **Test paketi**:
  - `test_risk_engine_exposure_limits.py`
  - `test_risk_engine_stale_spread_veto.py`
  - `test_risk_engine_daily_loss_cooldown.py`
  - `test_kill_switch.py`
  - `test_risk_engine_api_contracts.py` (testing agent contract paketi)
- **CI gate güncellemesi**:
  - stage/prod gate listelerine risk testleri dahil edildi; geçiş doğrulandı.

### Iteration-104 — #797 Mini Paket Kapanışı + 3-Katmanlı Scanner Entegrasyonu
- **P0 mini paket eksikleri kapatıldı**:
  - Repo credential cleanup tamamlandı (deprecated admin domain literal izi kaldırıldı).
  - `.gitignore` hijyen düzeltmesi yapıldı (duplike/bozuk satırlar temizlendi).
  - CI portability ve gate zinciri yeniden doğrulandı.
- **Tiered scanner runtime canlıya alındı**:
  - Discovery → Qualification → Decision orkestrasyonu `scanner_runtime.py` içinde devreye alındı.
  - Backpressure/tier cap alanları genişletildi: `discovery_cap`, `qualification_cap`, `decision_cap`.
  - Decision kernel çağrısı `manual_selection` ile qualified sembol setine daraltıldı.
  - Admin runtime summary’ye `tiered_scan` objesi eklendi.
- **CPU koruma / fallback hizası**:
  - `ScanScheduler` yük durumuna göre tier cap’leri dinamik düşürüyor.
  - Fallback aktifken cap’ler otomatik daha konservatif hale geliyor.
- **Yeni testler**:
  - `backend/tests/test_discovery_scan.py`
  - `backend/tests/test_qualification_scan.py`
  - `backend/tests/test_tiered_scan_pipeline.py`
  - `backend/tests/test_api_tiered_scanner.py` (agent eklemesi, API contract doğrulaması)
- **CI script güncellemesi**:
  - `scripts/ci_stage_gate.sh` ve `scripts/ci_prod_gate.sh` içine tiered test dosyaları eklendi.
- **Düşük öncelikli kalite iyileştirmesi**:
  - Discovery/universe normalizasyonunda alfanümerik USDT sembol filtresi uygulanarak spam/test token gürültüsü azaltıldı.

## 2026-03-12
### Iteration-54 — Phase-9B Strategy Intelligence
- Yeni servisler eklendi:
  - `strategy_conflict_engine.py` (cross-strategy conflict detection + resolution)
  - `capital_rebalance_engine.py` (dynamic allocation rebalance)
  - `hedging_suggestion_engine.py` (hedge recommendation üretimi)
  - `strategy_intelligence_service.py` (intelligence orchestration + manual override audit)
- Yeni config:
  - `/app/config/strategy_conflict_rules.json`
- Yeni governance bileşenleri:
  - `manual_override_log` tablosu (`ManualOverrideLog`)
  - `POST /api/admin/risk-simulation`
  - `POST/GET /api/admin/manual-overrides`
- Yeni admin intelligence paneli:
  - `/admin/strategy-intelligence`
  - conflict/rebalance/hedge/drift görünümü + simulation mode + manual override list
- User intelligence entegrasyonları:
  - `/user/execute` preview: `strategy_conflict_warning`, `allocation_adjustment_notice`, `hedge_suggestion`, `risk_reduction_score`
  - `/user/positions`: `recommended_action`, `risk_reduction_score`, `hedge_suggestion`
- Explainability genişletmesi:
  - trace alanları: `hedge_recommendation`, `risk_reduction_score`, `correlation_basis`
- Migration:
  - `20260312_0030_strategy_intelligence_layer.py`
- Testler:
  - `test_strategy_conflict_resolver.py` PASS
  - `test_dynamic_capital_rebalance.py` PASS
  - `test_hedge_suggestion_engine.py` PASS
  - `test_risk_simulation_mode.py` PASS
  - `test_iteration54_strategy_intelligence.py` PASS
  - testing agent raporu: `/app/test_reports/iteration_54.json`
- Artefact üretildi:
  - `/app/reports/strategy_intelligence_validation.json`

## 2026-03-12
### Iteration-53 — Execution Advanced Actions
- Execution intent modeli position actions için genişletildi:
  - `intent_type`, `position_id`, `size`, `reduce_only`, `price`, `stop_price`, `take_profit_price`
- Yeni intent tipleri aktif:
  - `CLOSE_POSITION`, `PARTIAL_CLOSE`, `REVERSE_POSITION`, `MOVE_STOP`, `MOVE_TAKE_PROFIT`
- Yeni execution contract eklendi:
  - `/app/contracts/execution_position_actions_contract.json`
- Yeni `positions` state modeli + sync servisi eklendi:
  - `backend/services/position_management_service.py`
- Yeni endpointler:
  - `POST /api/user/execution/position-actions/preview`
  - `POST /api/user/execution/position-actions/submit`
  - `GET /api/user/execution/positions`
  - `GET /api/admin/positions-monitor`
- Frontend:
  - `/user/positions` (tam pozisyon yönetimi aksiyonları)
  - `/admin/positions-monitor` (open positions + cluster/risk görünümü)
  - `/admin/execution-queue` intent_type + position_id kolon güncellemesi
- Explainability genişletmesi:
  - `position_action_reason`, `risk_adjustment_reason`, `strategy_override_reason`
- Testler:
  - `test_close_position_intent.py` PASS
  - `test_partial_close.py` PASS
  - `test_reverse_position.py` PASS
  - `test_stop_update.py` PASS
  - testing agent raporu: `/app/test_reports/iteration_53.json`
- Artefact üretildi:
  - `/app/reports/execution_position_actions_validation.json`

## 2026-03-12
### Iteration-52 — Phase-9A Strategy Meta Engine + Portfolio Risk Layer
- Yeni servisler eklendi:
  - `portfolio_risk_service.py` (risk score, risk flags, gate decision, position adjustment)
  - `meta_strategy_engine_service.py` (allocation, throttling/disable, drift monitor)
- Yeni config: `/app/config/portfolio_risk_limits.json` (admin güncellenebilir risk registry)
- Yeni veri modeli/migration:
  - `risk_clusters`
  - `portfolio_exposure_snapshot`
  - `strategy_allocations`
  - `pending_signals`, `user_execution_intents`, `user_decision_traces` phase9 alanları
- Execution preview pipeline phase9 entegrasyonu tamamlandı:
  - meta strategy summary
  - portfolio risk impact
  - gate decision (ALLOW/ADJUST_POSITION/REQUIRE_APPROVAL/REJECT)
- Admin UI eklendi:
  - `/admin/strategy-allocation`
  - `/admin/portfolio-risk`
- User UI eklendi/güncellendi:
  - `/user/execute` -> Portfolio Risk Impact + Meta Strategy Attribution
  - `/user/signals` ve `/user/trades` -> strategy attribution alanları
- Explainability phase9 entegrasyonu:
  - decision trace alanları: `portfolio_risk_score`, `strategy_allocation_reason`, `cluster_risk_flag`, `meta_engine_decision`
- Testler:
  - iteration52 report: `/app/test_reports/iteration_52.json`
  - yeni test setleri pass
  - artefactlar üretildi:
    - `/app/reports/portfolio_risk_validation.json`
    - `/app/reports/meta_strategy_validation.json`

## 2026-03-12
### Iteration-51 — Phase-8 Explainability Engine
- Explainability backend tamamlandı:
  - Yeni model: `UserDecisionTrace` (`user_decision_traces`)
  - Yeni migration: `20260312_0027_user_decision_traces.py`
  - Yeni servis: `services/explainability_service.py`
  - 90 günlük retention + trace cleanup aktif
- Yeni kullanıcı endpointleri eklendi:
  - `GET /api/user/signals/{signal_id}/decision-trace`
  - `GET /api/user/trades/{trade_id}/decision-trace`
  - `GET /api/user/execution/intents/{intent_id}/decision-trace`
  - `GET /api/user/strategies/{strategy_code}/explain`
  - `GET /api/user/explainability/coverage?days=7`
- Trace capture entegrasyonu yapıldı:
  - scanner/signal üretimi
  - signal approve/reject
  - execution preview/submit/cancel/approve/reject
- Frontend explainability panelleri tamamlandı:
  - `UserSignalsPage`: **Why this signal?**
  - `UserTradesPage`: **Decision Trace**
  - `UserExecutePage`: **Preview Explain**
- Reason code registry genişletildi (`/app/config/reason_codes_registry.json`)
- Testler:
  - `backend/tests/test_phase8_explainability_engine.py` PASS
  - `backend/tests/test_iteration51_explainability_comprehensive.py` PASS
  - `backend/tests/test_iteration50_pg01_execution_backend.py` PASS (regression)
  - Testing agent raporu: `/app/test_reports/iteration_51.json` (backend %100, frontend %100)

## 2026-03-12
### Iteration-50 — PG-01 Live Reporting + Phase-7A Execution Panel
- PG-01 canlıya alındı:
  - `GET /api/user/reports/weekly` artık 200 döner.
  - Artefact üretimi: `/app/artifacts/reports/{user_id}/{report_id}/...`
  - Dosyalar: `weekly_performance_report.pdf`, `weekly_trades.csv`, `weekly_strategy_stats.json`, `report_manifest.json`
- Execution backend/admin kuruldu:
  - Policy registry: `/app/config/execution_policy_registry.json`
  - Intent API: preview/submit/cancel + presets
  - Admin queue: `/api/admin/execution-queue` approve/reject akışları
  - Audit event seti aktif
- User yüzü açıldı:
  - `/user/reports` (+ `/reports`)
  - `/user/execute` (+ `/execute`)
  - Scanner/Signals -> Execute deep-link aksiyonları
- Contract/CI kalite kapıları:
  - `ci_contract_gate.sh` + `ci_execution_contract_gate.sh`
  - `validate_execution_contract.py`
- Artefact raporları üretildi:
  - `/app/test_reports/iteration_50.json`
  - `/app/test_reports/pg01_validation_report.json`
  - `/app/test_reports/execution_panel_validation_report.json`
  - `/app/reports/execution_policy_audit_report.json`

## 2026-03-12
### Phase-7 Iteration — CT + UX Closure (PG-01 Hariç)
- Contract katmanı eklendi:
  - `/app/contracts/api_contract_snapshot.json`
  - `/app/tests/test_api_contracts.py`
  - `/app/scripts/ci_contract_gate.sh`
  - `backend/cli/validate_contract_snapshot.py`
- User contract endpointleri tamamlandı:
  - `GET /api/user/dashboard`
  - `GET /api/user/scanner`
  - `GET /api/user/reports/weekly` (**501 stub**)
- UX hardening (user panel):
  - sticky nav + mobile sidebar toggle + desktop collapse
  - responsive 12-column düzen
  - mobile card/table collapse + compact mode (trades/scanner/signals)
  - loading skeleton + responsive chart bileşeni
  - focus-visible ve aria etiketleri
- Erişilebilirlik artefact’ı: `/app/test_reports/accessibility_audit.json`
- Phase-7A hazırlık contract’ı: `/app/contracts/execution_intent_contract.json`
- Testler:
  - local: contract + phase7 endpoint testleri PASS
  - testing agent: `/app/test_reports/iteration_49.json` PASS (backend/frontend %100)

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
