# PRD — Algorithmic Trading Platform (Phase 1 Başlangıç)

## 1) Original Problem Statement (Özet)
- Çok kullanıcılı, web tabanlı, otomatik çalışan algoritmik trading platformu
- İlk fazda Binance odaklı ama adapter tabanlı (gelecekte Bybit/OKX eklenebilir)
- Tek strateji değil, modüler strategy engine yaklaşımı
- Risk yönetimi + execution + admin emergency kontrol + audit/monitoring
- Kullanıcı seçimi: **1-b, 2-a, 3-b, 4-b, 5-b**
  - Dokümantasyon + çalışan temel iskelet
  - JWT email/şifre + user/admin rol
  - Binance adapter arayüzü + **MOCK** execution
  - Docker-compose ile PostgreSQL + Redis + servisler
  - Landing turuncu, panel nötr; admin normal alanlar mavi, kritik alanlar kırmızı
  - Mongo kullanılmayacak

## 2) Architecture Decisions
- Backend: FastAPI + SQLAlchemy tabanlı modüler router mimarisi
- DB hedefi: PostgreSQL (docker-compose ile standart)
- Cache/state hedefi: Redis (docker-compose ile standart)
- Runtime dayanıklılığı: Bu ortamda PostgreSQL/Redis yoksa local fallback ile uygulama ayakta kalır (geliştirme/test sürekliliği için)
- Auth: JWT, role-based access control (user/admin)
- Exchange: Adapter contract + BinanceMockAdapter (canlı emir yok)
- Frontend: React + Tailwind + shadcn/ui + Sonner + Router tabanlı çok sayfa panel

## 3) User Personas
- **Trader User**: Bot profili, risk policy, strategy görüntüleme, mock execution takibi
- **Admin Operator**: Sistem özetini izler, template yönetir, audit log denetler, kritik aksiyonları kontrol eder

## 4) Core Requirements (Static)
- Multi-user auth ve rol ayrımı
- User/Admin dashboard shell
- Bot profile create/update/list
- Risk policy create/update/list
- Strategy template yönetimi
- Audit log tablosu
- Exchange mock execution akışı
- Dokümantasyon çıktıları (sayfa haritaları, mimari, şema, policy, adapter sözleşmesi)

## 5) What Has Been Implemented
### 2026-03-10
- JWT auth (register/login/me) + role kontrolü
- Bot profile CRUD (create/update/list)
- Risk policy CRUD (create/update/list)
- Strategy template yönetimi (admin write, user read)
- Audit log endpoint + admin table görünümü
- Binance mock adapter + mock execute/state/events endpointleri
- User dashboard shell + Admin dashboard shell + kritik aksiyon UI (double confirmation)
- Landing + split-screen login tasarımı (turuncu vurgu, panel nötr/dense)
- Docker compose altyapısı (postgres/redis/backend/frontend)
- Faz-1 dokümantasyon seti `/app/docs/phase1/*`
- Testler:
  - Backend API akışları curl ile doğrulandı
  - Frontend route ve panel akışları Playwright screenshot ile doğrulandı
  - Testing agent raporu: `/app/test_reports/iteration_1.json`

### 2026-03-10 (Faz-2 Sprint b — Omurga)
- **Market Universe Engine**: Admin kontrol API/ekranı (`/api/admin-control`) + effective universe preview
- **Market Data Engine**: Binance WebSocket denemesi + reconnect/heartbeat; erişim engelinde synthetic fallback ile candle event üretimi
- **Signal Orchestration + Strategy Engine**: Trend Following, Mean Reversion, Breakout, Volatility Expansion modülleri ile sinyal üretimi
- **Risk Engine**: merkezi onay/reddet katmanı (spread, open position, leverage cap, volatility, emergency mode)
- **Paper Trading Pipeline**: signal -> risk -> paper execution -> position ledger akışı
- **Position Engine**: open / stop_hit / tp_hit / manual_close ve unrealized-realized PnL takibi
- **Monitoring Core**: websocket status, signal rate, paper trade sayısı, queue depth, latency
- **Audit Genişletme**: bot_start, bot_stop, signal_generated, risk_rejection, trade_open, trade_close eventleri
- **Socket Gateway**: `/api/socket.io` endpointi eklendi (404 sorunu giderildi)
- Faz-2 test raporu: `/app/test_reports/iteration_2.json` (backend+frontend doğrulandı)

### 2026-03-11 (Faz-3 İterasyon-1 — Güçlendirme Başlangıcı)
- Seçim setine göre uygulandı: **1-b, 2-b, 3-a, 4-c, 5-a**
- **Alembic versiyonlu migration altyapısı** kuruldu (`/app/backend/migrations/*`, revision: `20260311_0001`)
- Yeni çekirdek tablolar eklendi: `execution_policies`, `risk_exposure_groups`, `failed_events`, `state_rebuild_logs`, `backtest_result_cards`
- Execution policy layer ilk çalışan versiyonu devrede (Breakout=aggressive, MeanReversion=passive, TrendFollowing=balanced, VolatilityExpansion=balanced)
- Risk engine exposure kontrolü tek-grup başlangıç modeli ile genişletildi (`all_symbols` unified exposure pool)
- Failed event queue/retry/resolve altyapısı eklendi ve recovery loop çalışır hale getirildi
- Restart sonrası state rebuild log mekanizması eklendi (startup + manual tetikleme)
- Admin minimum yönetim ekranları eklendi:
  - Execution Policies
  - Exposure Groups
  - Failed Events
  - State Rebuild Logs
  - Backtest Cards
- Failed-events UI için deterministik test akışı eklendi (`seed` endpoint + panel butonu)
- Testler:
  - `/app/test_reports/iteration_3.json`
  - `/app/backend/tests/test_phase3_admin_policy_engine.py`
  - Retest: `/app/test_reports/iteration_4.json` (UI/API scope: temiz)

### 2026-03-11 (Faz-3 İterasyon-2 — Çoklu Exposure + State Machine Görünürlüğü)
- Kullanıcı kararı: **kapanış seviyesi c** (backend motorlar + adminde minimum işlevsel görünürlük)
- Risk motoru çoklu exposure group modeline genişletildi:
  - `majors` (BTC, ETH)
  - `high_beta_alts` (SOL, AVAX, LINK)
  - `mid_cap` (fallback)
- Global directional crowding + group open limit + group directional limit + group risk budget kontrolleri eklendi
- Execution state machine için `execution_state_transitions` tablosu eklendi (Alembic revision `20260311_0002`)
- Paper execution akışında state path kaydı aktif: `created -> submitted -> acknowledged -> ...`
- Hardening çekirdek metrikleri genişletildi:
  - idempotency keys /5m
  - duplicate blocked /5m
  - websocket reconnect /5m
  - execution transitions /5m
  - failed events pending/dead
- Admin görünürlüğü artırıldı:
  - **Execution States** sayfası eklendi (state transition tablosu + hardening özet kartları)
  - Simülasyon endpointi eklendi: `/api/admin-phase3/execution-state-transitions/simulate`
  - Monitoring ekranı hardening metrikleriyle genişletildi
- Testler:
  - `/app/test_reports/iteration_5.json` (backend+frontend, %100 pass)

### 2026-03-11 (Faz-3 İterasyon-3 — Policy Branching + Hardening Gate)
- Kullanıcı seçimleri: **1-d, 2-b, 3-a**
- Policy-driven state machine branch davranışları derinleştirildi:
  - filled
  - timeout -> fallback_submitted -> filled
  - rejected
  - failed
- Admin simulate endpointi outcome bazlı hale getirildi (`filled/timeout/rejected/failed`) ve allow-list doğrulaması eklendi
- Yeni model/migration: `hardening_checklist_runs` (Alembic revision `20260311_0003`)
- Hardening checklist kritik kapı mantığı aktif:
  - kritik maddelerden biri fail ise skor `<=59` sınırına kilitlenir
  - readiness status `blocked`
- Yeni admin ekranı: **Hardening Checklist**
  - run butonu
  - score/readiness/critical blocked kartları
  - item bazlı pass/fail tablo görünümü
- Execution States ekranı outcome bazlı simülasyon butonları ile genişletildi
- Test raporları:
  - `/app/test_reports/iteration_6.json`
  - minor bulgular giderildi (threshold iyileştirmesi + simulate allow-list validation)

### 2026-03-11 (Faz-3 İterasyon-4 — Hibrit Korelasyon + Trend Alarm + User Read-only)
- Kullanıcı seçimleri: **1-a, 2-c, 3-c**
- Korelasyon hibrit modeli eklendi:
  - statik risk grupları (majors/high_beta/mid_cap)
  - rolling korelasyon puanı (window destekli)
  - risk engine içinde correlation tabanlı cluster rejection etiketleri
- Admin correlation matrix endpoint + ekranı eklendi (`/api/admin-phase3/correlation-matrix`)
- Execution state simülasyonu genişletildi:
  - partial-fill + retry budget desteği
  - simulate endpoint outcome seçenekleri: filled/partial/timeout/rejected/failed
- Hardening checklist trend/alarm katmanı eklendi:
  - kritik fail varsa anlık alarm
  - son 5 run ortalaması < 70 ise trend alarm
  - admin ekranında trend metrikleri + alert listesi + recent runs tablosu
- User tarafında minimum karar destek görünümü eklendi:
  - `/api/backtest/cards` read-only endpoint
  - `Backtest Insights` user sayfası
- Test raporu:
  - `/app/test_reports/iteration_7.json` (backend+frontend doğrulandı)
  - belirtilen UI eksikliği (simulate failed butonu) giderildi

### 2026-03-11 (Faz-4 İterasyon-1 — Controlled Live Activation Hazırlığı)
- Admin panel teması operasyonel mavi/kırmızı çizgide kesinleştirildi (user turuncu/black ayrımı korunarak)
- Admin sidebar’a **Phase-4 Live Control** eklendi ve route aktif edildi (`/app/phase4-live`)
- Binance Futures Testnet hazırlık katmanı güçlendirildi:
  - Testnet connectivity probe (`/api/phase4/testnet-connectivity`)
  - Permission check artık missing/invalid/exchange error senaryolarını 500 atmadan yönetiyor
  - API key/secret için request+environment çözümleme ve mask/fingerprint güvenli gösterim
- Safety layer sıkılaştırıldı (safe mode):
  - yalnızca `BTCUSDT`
  - leverage cap `<=1`
  - max position `%0.1`
  - max notional exposure `<=150`
  - kill-switch / disable-futures / kritik readiness fail durumlarında live mode otomatik kapatma
- Readiness raporu genişletildi:
  - `testnet_endpoint_reachable`
  - `safe_limits_locked`
  - no-key fail-safe ve docs referansları
- Testler:
  - `/app/test_reports/iteration_8.json` (backend 22/22 pass, frontend 100%)
  - `/app/backend/tests/test_phase4_live_activation.py`

### 2026-03-11 (Faz-4 İterasyon-2 — Panel Ayrımı + Kullanıcı Onay Akışı)
- Kullanıcı kararları uygulandı: **1A, 2A, 3A, 4A**
- Admin panel teması turuncu + koyu siyah yapıldı; sidebar menüsüne taşma için `overflow-y-auto` eklendi.
- Admin/User yapısı ayrıldı:
  - Login ekranları: `/admin/login` ve `/user/login`
  - Panel rotaları: `/admin/*` ve `/user/*`
  - Role mismatch durumunda otomatik doğru panele yönlendirme
- User giriş ekranı referans görsele yakın şekilde yeniden tasarlandı (Bireysel seçeneği, e-posta/şifre alanları, checkbox, forgot-password linki, turuncu CTA).
- Backend user approval workflow eklendi:
  - Register sonrası user: `approval_status=pending`, `is_active=false`
  - Admin onay API’leri:
    - `GET /api/auth/admin/user-approval-requests?status=pending`
    - `POST /api/auth/admin/user-approval-requests/{id}/approve`
    - `POST /api/auth/admin/user-approval-requests/{id}/reject`
  - Rol bazlı login endpointleri:
    - `POST /api/auth/login/admin`
    - `POST /api/auth/login/user`
- DB migration eklendi: `20260311_0005_user_approval_flow.py` (approval kolonları)
- Testler:
  - `/app/test_reports/iteration_9.json` (backend 13/13 pass, frontend 100%)
  - `/app/backend/tests/test_user_approval_flow.py`

### 2026-03-11 (Faz-4 İterasyon-2B — Testnet Validation + Execution Quality)
- User panelde **Exchange Settings** akışı eklendi (`/user/exchange-settings`):
  - `exchange`, `mode`, `api_key`, `api_secret` alanları
  - API key/secret backend’de şifreli saklama (Fernet, plaintext response yok)
- Permission doğrulama detayları eklendi:
  - `can_trade`, `can_futures`, `timestamp_sync`, `rate_limit_ok`
  - standart çıktı: `status`, `reason`, `timestamp`
  - fail durumunda `live_activation=blocked`
- Hard safety layer test order için zorlandı (override edilemez):
  - `symbol=BTCUSDT`, `leverage=1x`, `notional<=150`, `%0.1` güvenli sınır yaklaşımı
- İlk kontrollü test order altyapısı eklendi:
  - `order_type=LIMIT`, fallback `IOC`
  - lifecycle path: `created -> submitted -> acknowledged -> partial_fill|filled|cancelled|failed`
  - state machine path loglanır
- Execution kalite metrikleri eklendi:
  - `expected_price`, `fill_price`, `slippage`, `execution_latency`, `execution_quality_score`
  - User dashboard’da sade score, admin panelde detay tablo
- Admin panel Phase-4 genişletildi:
  - Live Readiness Score kartı
  - Release Gate Status paneli (`PASS|WARNING|BLOCKED`)
  - Permission Status paneli
  - Execution Quality Metrics tablosu
- Dry-run release gate aktif:
  - BLOCKED ise `live_activation=disabled`
  - kritik blokajlar readiness skorunu 80 üstüne çıkarmayı engeller
- Yeni DB migration:
  - `20260311_0006_exchange_settings_and_test_logs.py`
  - `user_exchange_settings`, `testnet_execution_logs`
- Testler:
  - `/app/test_reports/iteration_10.json` (backend 23/23 pass, frontend 100%)
  - `/app/backend/tests/test_phase4_iter2_exchange_settings.py`
  - Not: valid testnet key olmadan gerçek test order bilinçli olarak BLOCKED kaldı (beklenen davranış)

### 2026-03-11 (Faz-4 İterasyon-2C — A→B→C İlerlemesi)
- Kullanıcı tercihi uygulandı: **A→B→C**
- **A (Test Order + Slippage doğrulama altyapısı):**
  - User panel exchange settings üzerinden key yönetimi akışı korundu
  - Test order path valid key yoksa `400` ile güvenli bloklanır
  - Valid key geldiğinde ilk kontrollü order lifecycle + slippage/latency/quality ölçümü hazır
- **B (Release Gate otomasyon pipeline):**
  - Runtime içine 30 sn döngüyle release gate guard loop eklendi
  - `BLOCKED => live_mode_enabled=False` otomatik zorlanır
  - Monitoring endpointine `release_gate_status`, `release_gate_last_checked` eklendi
- **C (Execution quality normalizasyonu):**
  - Quality score strategy + volatility rejimine göre normalize edildi
  - `strategy_type`, `volatility_regime`, `volatility_pct` alanları execution quality response’larına eklendi
- Bu iterasyonda kullanıcı talebine göre **permission drift trend grafiği eklenmedi** (sonraki iterasyona bırakıldı).
- Testler:
  - `/app/test_reports/iteration_11.json` (backend 23/23 pass, frontend 100%)
  - `/app/backend/tests/test_phase4_iter2_release_gate_pipeline.py`

### 2026-03-11 (Faz-4 İterasyon-3 — Controlled Test Order Contract + Drift Monitoring + CI Gate)
- Endpoint contract kararları uygulandı (geriye uyumlu):
  - `GET /api/exchange/validate`
  - `POST /api/exchange/test-order`
  - `GET /api/market/ticker`
- `validate` çıktısı dinamik permission modeliyle üretildi:
  - `exchange`, `environment`, `is_valid`, `permissions`, `can_trade`, `can_withdraw`, `reason_codes`
  - hata mapping: missing/invalid key `400`, permission/IP kısıtı `403`
- User exchange settings üzerinden key girişi korunarak test-order eligibility doğrulandı (chatten key paylaşımı gerekmez).
- Execution metrikleri için yeni kalıcı tablo eklendi:
  - `execution_metrics` (order_id, exchange_order_id, price_avg, executed_qty, slippage_pct, execution_time_ms, status, state_machine_path, strategy/volatility alanları)
- Slippage referansı market ticker mid-price ile hesaplandı:
  - `mid_price = (bid + ask) / 2`
  - snapshot timestamp kaydı
- Permission drift izleme altyapısı eklendi:
  - `permission_drift_events` tablosu
  - `/api/phase4/admin/permission-drift-trend?days=7|30` aggregation + summary
- Admin `/admin/monitoring` genişletildi:
  - Permission Drift Trend line chart
  - 7/30 gün toggle
  - summary: affected users, latest timestamp, critical drift count
- Release gate deploy runner eklendi:
  - `/app/scripts/run_release_gate_check.sh` (executable)
  - backend CLI orchestrator: `backend/cli/release_gate_check.py`
  - `BLOCKED` durumunda non-zero exit code ile deploy bloklama kuralı
- Migration:
  - `20260311_0007_execution_metrics_and_permission_drift.py`
- Testler:
  - `/app/test_reports/iteration_12.json` (backend 24/24 pass, frontend 100%)
  - `/app/backend/tests/test_phase4_iter3_endpoints.py`
  - `/app/test_reports/pytest/pytest_results_iter12_phase4_iter3.xml`
  - Not: valid Binance testnet key olmadan gerçek fill doğrulaması bu turda **BLOCKED** bırakıldı (beklenen güvenli davranış)

### 2026-03-11 (Faz-4 İterasyon-4 — Override + Readiness + UI Sertleştirme)
- Admin manual override mekanizması eklendi (admin-only):
  - `POST /api/phase4/admin/release-gate/override`
  - `reason_code` enum zorunlu: `false_positive | exchange_incident | ops_emergency | manual_review`
  - `reason_note` zorunlu, min 12 karakter
  - default TTL 30 dk, max 60 dk
  - sadece `BLOCKED` gate durumunda override açılabilir
- Override audit trail tamamlandı:
  - yeni tablo: `release_gate_overrides`
  - alanlar: `override_id, admin_user_id, release_gate_snapshot, override_reason(code+note), created_at, expires_at, revoked_at, deploy_context, used_deploy_count`
  - revoke endpoint: `POST /api/phase4/admin/release-gate/override/{override_id}/revoke`
- Release gate sonucu override-aware hale getirildi:
  - aktif override varsa `PASS_WITH_OVERRIDE`
  - deploy runner script bu durumda exit `0`, BLOCKED’de exit `2`
  - CLI deploy kullanımında active override `used_deploy_count` artırılır
- User readiness checklist tamamlandı:
  - endpoint: `GET /api/exchange/readiness-checklist`
  - stale threshold: **10 dk**
  - durumlar: `awaiting_valid_key`, `ready_for_test_order`, `blocked`
- User test-order güvenli bloklama korunarak sertleştirildi:
  - `POST /api/exchange/test-order` readiness uygun değilse detaylı `status` ile 400 döner
  - valid key yoksa net mesaj: *awaiting valid key*
- Admin monitoring genişletildi (tek panel yaklaşımı):
  - Release Gate Override Status
  - Override History
  - Override Analytics (günlük blocked/override/override-deploy)
  - Hardening Checklist Trend
  - Alert History
  - Permission Drift Trend (7/30 toggle) korunarak devam
- User panel görsel/etkileşim sertleştirme:
  - readiness checklist card
  - failure reason banner
  - action state machine (`disabled/validating/ready/blocked/executing`)
  - test-order sonuç kartı (status, exchange order id, fill, qty, slippage, time, volatility, strategy, validation timestamp)
- Migration:
  - `20260311_0008_release_gate_override_and_validation_snapshot.py`
- Testler:
  - `/app/test_reports/iteration_13.json` (backend 26/26 pass, frontend 100%)
  - `/app/backend/tests/test_phase4_iter4_override_readiness.py`
  - Not: valid Binance key olmadığı için gerçek fill lifecycle bu turda **MOCKED/BLOCKED** doğrulandı.

### 2026-03-11 (Faz-4 İterasyon-5 — Env-aware Gate + Evidence Lifecycle + Operability)
- **A1 Environment-aware release gate** tamamlandı:
  - `run_release_gate_check.sh` artık `--env=stage|prod` zorunlu alır
  - `--env` verilmezse hard fail (`missing required argument: --env`, non-zero exit)
  - stage/prod policy matrix aktif:
    - Stage score eşikleri: `<40 BLOCKED`, `40-60 WARN`, `>=60 PASS`
    - Prod score eşikleri: `<60 BLOCKED`, `60-75 WARN`, `>=75 PASS`
- **A2 Gate policy matrix** backend/CLI katmanına taşındı:
  - değerlendirilen alanlar: `exchange_health`, `execution_quality_score`, `permission_drift_alert`, `active_override`, `live_mode_enabled`
  - çıktı statüleri: `PASS | PASS_WITH_OVERRIDE | WARN | BLOCKED`
  - release gate endpoint environment-aware oldu: `GET /api/phase4/admin/release-gate?environment=stage|prod`
- **A3 CI entegrasyonu** hazırlandı:
  - wrapper scriptler eklendi:
    - `/app/scripts/ci_stage_gate.sh`
    - `/app/scripts/ci_prod_gate.sh`
  - script parse çıktısı:
    - `release_gate_status=...`
    - `environment=...`
    - `reason_code=...`
    - override varsa `override_expires_at=...`
- **A4 Override countdown + auto-refresh** eklendi:
  - `/admin/monitoring` override kartında kalan süre badge + progress bar
  - son 5 dk warning state
  - operability bar: `auto-refresh` ve `page_visible`
  - aktif override varken 15sn polling, aksi halde 30sn
- **B1/B2/B3/B4 User execution kanıt hattı** güçlendirildi:
  - readiness endpoint genişletildi (`validation_snapshot_id` dahil)
  - `POST /api/exchange/test-order` blocked durumunda normalized `failure_code` döner
  - failure normalization sözlüğü aktif: `invalid_key, permission_denied, ip_restricted, testnet_unreachable, insufficient_balance, exchange_rejected, stale_validation, unknown_exchange_error`
  - yeni evidence endpoint: `GET /api/exchange/lifecycle-evidence/latest`
  - execution persistence alanları genişletildi (client order id, submitted/ack/final timestamps, raw status, validation snapshot korelasyonu)
  - lifecycle timeline olay tablosu eklendi (`execution_lifecycle_events`)
- **C HTML/CSS operability standardizasyonu**:
  - monitoring operability bar + override status kartı sertleştirildi
  - user tarafında readiness/failure/evidence kartları tutarlı state modeliyle hizalandı
- Migrationlar:
  - `20260311_0009_execution_evidence_fields.py`
  - SQLite fallback uyumluluğu için `db.py` tarafına kritik sütun/tablolar için güvenli bootstrap eklendi
- Testler:
  - `/app/test_reports/iteration_14.json` (backend 27/27 pass, frontend 100%)
  - `/app/backend/tests/test_phase4_iter5_env_aware_release_gate.py`
  - `/app/test_reports/pytest/pytest_results_iter14_phase4_iter5.xml`
  - Not: valid Binance testnet key olmadığı için gerçek fill doğrulaması bu turda da **MOCKED/BLOCKED** akışla test edildi.

### 2026-03-11 (Faz-4 İterasyon-6 — CI Kapanışı + User Ürünleşme + Alarm Yönlendirme)
- **A (Admin/Deploy)**
  - CI wrapper entegrasyonu tamamlandı:
    - `.github/workflows/stage-gate.yml` → `scripts/ci_stage_gate.sh`
    - `.github/workflows/prod-gate.yml` → `scripts/ci_prod_gate.sh`
  - `run_release_gate_check.sh` `--env` olmadan hard fail (explicit env zorunlu)
  - stage/prod policy matrix davranışı korunarak parse edilebilir çıktı standardı devam ettirildi
  - Monitoring’e **Active Alerts** + **Alert Policy** blokları eklendi
  - Alert policy backend’i eklendi:
    - `GET/PUT /api/phase4/admin/alert-policy`
    - `GET /api/phase4/admin/active-alerts`
  - Permission drift için routing hattı eklendi (admin notification + ops webhook + monitoring audit log)

- **B (User/Execution)**
  - User tarafı 3 sekmeli ürünleşmiş yapıya alındı:
    - `Overview`
    - `Risk Settings`
    - `Test & Validation`
  - Yeni user risk backend’i:
    - `GET/PUT /api/user-risk/settings`
    - `GET /api/user-risk/preview`
    - `GET /api/user-risk/overview`
  - Risk modeli yüzde bazlı kısıtlarla uygulandı:
    - allocation `%1-%50`, trade risk `%1-%25`, daily loss `%1-%10`
    - soft warning alanları (high_allocation/high_trade_risk/high_daily_loss)
  - Test & Validation tarafında awaiting_valid_key davranışı korunarak evidence panel hazır bırakıldı
  - Lifecycle evidence endpointi kullanılarak timeline UI beslemesi aktif

- **C (Operability/UI)**
  - Admin navbar’da aktif override countdown badge eklendi
  - Monitoring operability bar + override countdown/progress görselleştirmesi sürdürüldü
  - User panelde risk önizleme ve execution evidence görünümü ayrıştırıldı

- Ek düzeltmeler:
  - `/api/health` endpointi eklendi (404 minor issue giderildi)
  - User exchange page ilk yüklemede gereksiz validate çağrısı kaldırıldı (konsol 400/404 gürültüsü azaltıldı)

- Migrationlar:
  - `20260311_0010_user_risk_and_alert_policy.py`
  - SQLite fallback uyumluluğu için `db.py` bootstrap genişletildi

- Testler:
  - `/app/test_reports/iteration_15.json` (backend 28/28 pass, frontend 100%)
  - `/app/backend/tests/test_phase4_iter6_user_risk_alert_policy.py`
  - `/app/test_reports/pytest/pytest_results_iter15_phase4_iter6.xml`
  - Not: valid testnet key paylaşılmadığı için gerçek fill lifecycle bu turda da **MOCKED/BLOCKED** (awaiting_valid_key) modunda bırakıldı.

### 2026-03-11 (Faz-5 İterasyon-1 — Safety-First Core)
- Kullanıcı kararı uygulandı: **1A, 2A, 3A, 4A**
  - 1A: Risk Engine + Position Sizing + Kill Switch
  - 2A: Hard veto
  - 3A: Kill switch sadece yeni order’ları durdurur, açık pozisyonlara dokunmaz
  - 4A: Backtest/Replay Faz-5 İterasyon-2’ye planlandı
- Yeni servisler:
  - `services/pipeline/position_sizing_engine.py`
  - `services/pipeline/kill_switch_service.py`
- Risk Engine iyileştirmeleri:
  - Position sizing formülü user modeliyle bağlandı
  - günlük zarar limiti ve consecutive loss kontrolü eklendi
  - max portfolio exposure + max risk per trade kontrolleri eklendi
  - Hard veto blok sebepleri zorunlu risk_tags ile dönüyor
- Runtime Kill Switch guard:
  - 10sn loop ile tetik kontrolü
  - aktifken orchestrator yeni order üretmez
  - `mode=block_new_orders_only` (açık pozisyonlar korunur)
  - botlar pause edilir, audit log düşülür
- Kill switch admin endpointleri:
  - `GET /api/admin-control/kill-switch/status`
  - `POST /api/admin-control/kill-switch/reset`
- Monitoring snapshot alanları genişledi:
  - `execution_errors_5m`, `risk_anomalies_5m`, `global_trading_pause`, `kill_switch_reasons`
- Frontend monitoring:
  - Kill Switch metriği ve reasons gösterimi eklendi
- Testler:
  - `/app/test_reports/iteration_16.json` (backend 22/22 pass, frontend 100%)
  - `/app/backend/tests/test_phase5_iter1_risk_killswitch.py`
  - `/app/test_reports/pytest/pytest_results_iter16_phase5_iter1.xml`

### 2026-03-11 (Faz-5 İterasyon-2 — Venue Expansion Tamamlama)
- Kullanıcı karar seti uygulandı: **1C, 2B, 3A, 4A**
- Admin tarafında Venue yönetimi ürünleştirildi:
  - Yeni sayfa: `/admin/exchanges`
  - **Exchange Registry FULL CRUD** (create/list/update/delete)
  - **Capabilities FULL CRUD** (create/list/update/delete)
  - **Allowed Markets FULL CRUD** (create/list/toggle/delete)
  - **User Assignment matrix** (list/upsert/delete)
  - Venue health/availability/capability mismatch özet görünümü
- Backend Venue API’leri genişletildi ve ana router’a eklendi:
  - `server.py` içine `venues.router` include edildi
  - `venues.py` içinde CRUD endpointleri tamamlandı
  - `seed_binance_venue_registry` idempotent hale getirildi (admin override edilen alanları ezmiyor)
- `/api/exchange/validate` endpointi artık **venue-aware zorunlu contract** ile çalışıyor:
  - Zorunlu query: `exchange`, `market_type`, `environment`
  - Response alanları: `exchange`, `market_type`, `environment`, `capability_match`, `reason_codes`
  - Venue access/assignment/capability kontrolleri validate hattına bağlandı
- User panelde Venue seçimi güçlendirildi (`/user/exchange-settings`):
  - `Risk Settings` + `Test & Validation` sekmelerine exchange/market/environment dropdownları
  - Canlı `venue access` paneli (`allowed`, `venue_state`, `capability_match`, `reason_codes`)
  - Test order butonunda venue uygunluk kısıtı (`binance/futures/testnet`)
- PostgreSQL-only doğrulama:
  - Kod tabanı tarandı; `mongo/pymongo/ObjectId` üretim kodunda kalıntı bulunmadı
- Testler:
  - `/app/test_reports/iteration_17.json` (backend 34/34 pass, frontend venue kapsamı pass)
  - `/app/backend/tests/test_phase5_iter2_venue_expansion.py`
  - `/app/test_reports/pytest/pytest_results_iter17_venue_expansion.xml`
  - Frontend smoke: admin exchanges sayfası ve landing yüklenmesi doğrulandı

### 2026-03-11 (Faz-5 İterasyon-3 — Execution Altyapısı + Dual-Mode + Replay Backend)
- Kullanıcı karar seti uygulandı: **1B, 2B, 3A, 4A**
- **A — Execution Proof altyapısı (key yokken bloksuz ilerleme):**
  - `/api/exchange/test-order` venue-context query paramları destekler hale getirildi: `exchange`, `market_type`, `environment`, `leverage`, `margin_mode`, `position_side`
  - Test-order response’a immutable context alanları eklendi: `exchange`, `market_type`, `environment`
  - `execution_metrics` tablosuna context kolonları eklendi: `exchange`, `market_type`, `environment`
  - Lifecycle event isimleri A2’ye hizalandı: `request_sent`, `exchange_ack`, `partial_fill`, `final_fill` (+ `final_cancel`)
  - Hata sınıflandırması normalize edildi ve venue-context ile döndürülüyor: `invalid_key`, `permission_denied`, `ip_restricted`, `insufficient_balance`, `exchange_rejected`, `testnet_unreachable`, `stale_validation`, `unknown_exchange_error`
- **B — Spot/Futures Dual-Mode:**
  - User panelde `Risk Settings` ve `Test & Validation` sekmeleri market type’a göre ayrıştırıldı
  - Spot mod: futures alanları gizli; quoteQty semantiği açıklaması
  - Futures mod: `leverage`, `margin_mode`, `position_side`, liquidation-risk görünürlüğü
  - `/api/user-risk/preview` market-aware hale getirildi (`market_type`, `leverage`, `margin_mode`, `position_side`)
  - Futures preview alanları eklendi: `estimated_liquidation_buffer_pct`, `margin_usage_pct`
- **C — Backtest/Replay başlangıcı (Backend-only):**
  - Yeni servis: `backend/services/replay_service.py`
  - Yeni endpointler:
    - `POST /api/backtest/replay/run`
    - `GET /api/backtest/replay/run/{run_id}`
  - Replay pipeline contractı uygulandı: `historical_data -> signal_engine -> risk_engine -> position_sizing -> simulated_execution -> metrics`
  - Binance Futures historical klines adapter: `1m`, `5m`, `15m`, `1h`
  - Simulator lifecycle: `SIM_NEW`, `SIM_FILLED`, `SIM_CANCELED`; metrics persistence aktif
- Operasyonel iyileştirme:
  - `/api/phase4/execution-quality/latest` artık boş durumda 404 yerine `awaiting_valid_key` fallback response dönüyor (UI console 404 gürültüsü azaltıldı)
- Testler:
  - `/app/test_reports/iteration_18.json` (backend+frontend pass)
  - `/app/backend/tests/test_phase5_iter3_execution_dualmode_replay.py` (22/22 pass)
  - Smoke ve API self-testler: dual-mode UI + replay run/detail + venue-context test-order doğrulandı

### 2026-03-11 (Faz-5 İterasyon-4 — Lifecycle Proof Orchestration + Immutable Execution + Replay Risk Summary)
- Kullanıcı karar seti uygulandı: **1B, 2B, 3B, 4B**
- **Görev-1 (Lifecycle Proof):**
  - Yeni orchestrator endpoint: `POST /api/exchange/lifecycle-proof`
  - Pipeline davranışı:
    - Önce live proof denemesi (`binance/futures/testnet`)
    - Key blokajında machine-readable blocker üretimi
    - Otomatik fallback replay evidence üretimi
  - Artifact çıktıları:
    - `exchange_evidence_{...}.json` (live veya blocked)
    - `fallback_replay_evidence_{...}.json` (non-live kanıt)
  - `evidence_type` alanı ile ayrım kesinleştirildi: `live_exchange | fallback_replay | blocked`
- **Görev-2 (Immutable Execution):**
  - `ExecutionMetric` satırı SQLAlchemy `before_update` hook ile immutable yapıldı
  - Yeni append-only event modeli: `execution_correction_events`
  - Yeni API’ler:
    - `POST /api/exchange/execution/{execution_id}/corrections`
    - `GET /api/exchange/execution/{execution_id}/corrections`
  - Update yerine correction-event akışı devreye alındı
- **Görev-3 (Replay → Risk Policy Feedback):**
  - Replay equity eğrisi persist edildi (`replay_equity_points`)
  - Yeni endpoint: `GET /api/backtest/replay/{run_id}/risk-summary`
  - Risk metrikleri: `max_drawdown`, `sharpe`, `win_rate`, `profit_factor`, `avg_slippage_bps`, `volatility_bucket`, `regime_bucket_distribution`, `exposure_breach_count`, `risk_reject_count`
  - Deterministic export: `replay_risk_summary_{run_id}.json` (`schema_version` zorunlu)
- Ek API uyumluluğu:
  - Alias endpoint eklendi: `POST /api/exchange/execution/order` (mevcut test-order contract delegasyonu)
- Migration/DB güncellemeleri:
  - Alembic: `20260311_0013_execution_immutability_and_replay_risk.py`
  - Yeni tablolar: `execution_correction_events`, `replay_equity_points`
- Testler:
  - `/app/test_reports/iteration_19.json` (backend/frontend pass)
  - `/app/backend/tests/test_phase5_iter4_lifecycle_immutable_risk.py` (5/5 pass)
  - Regression: iter3 test seti tekrar koşuldu (22/22 pass)

### 2026-03-11 (Faz-5 Hardening İterasyon-5 — Artefact Integrity + Verify + Admin Proof Panel)
- Kullanıcı karar seti uygulandı: **1A, 2B, 3B, 4B**
- **Görev-1 (Proof Artefact Integrity / SHA-256):**
  - Yeni servis: `backend/services/artifact_service.py`
  - Tüm proof artefact’lar imzalanıyor (SHA-256):
    - `exchange_evidence_*.json`
    - `fallback_replay_evidence_*.json`
    - `replay_risk_summary_*.json`
  - Artefact metadata alanları eklendi: `schema_version`, `artifact_type`, `created_at`, `sha256`, `artifact_id`
  - Merkezi manifest: `/app/backend/exports/artifact_manifest.json`
    - zorunlu alanlar: `artifact_id`, `filename`, `artifact_type`, `sha256`, `size`, `created_at`
- **Görev-2 (Proof Verification Endpoint):**
  - Yeni router: `backend/routers/audit.py`
  - Endpoint: `GET /api/audit/artifacts/{artifact_id}/verify`
    - UUID tabanlı lookup (manifest içi `artifact_id`)
    - `sha256_expected`, `sha256_actual`, `verified` döner
    - doğrulama sonucu audit log’a yazılır (`action=artifact_verify`)
  - Endpoint: `GET /api/audit/artifacts/{artifact_id}/download`
- **Görev-3 (Admin Proof Panel):**
  - Yeni rota: `/admin/proofs`
  - Yeni sayfa: `frontend/src/pages/AdminProofsPage.jsx`
  - Liste alanları: `proof_id`, `evidence_type`, `status`, `artifact_hash`, `created_at`, `filename`
  - Satır aksiyonları: `Verify`, `Download`
  - Nav entegrasyonu: `Proof Panel` linki eklendi
- **Görev-4 (Replay Risk → Risk Policy Feed):**
  - Yeni tablo/model: `risk_policy_audit_events`
  - Trigger politikası: **yalnızca replay run completion** anında tek kayıt
  - Duplicate önleme: aynı `replay_run_id` için ikinci write engellenir
- Migration/DB:
  - Alembic: `20260311_0014_risk_policy_audit_events.py`
  - SQLite compatibility: `risk_policy_audit_events` tablosu eklendi
- Testler:
  - `/app/test_reports/iteration_20.json` (backend/frontend pass)
  - `test_faz5_hardening_iter5_artifacts.py` (15/15 pass)
  - Lokal regresyon: iter3+iter4 toplam 27/27 pass

### 2026-03-11 (Faz-6.1 + 6.2 — Strategy Domain + Deterministic Kernel Contract)
- Kullanıcı karar seti uygulandı: **kapsam A (6.1+6.2), admin-only create/version, rota `/admin/strategies`, manifest_chain_hash ertelendi**
- **6.1 Strategy Domain:**
  - Yeni modeller: `StrategyDefinition`, `StrategyVersion` (append-only sürümleme)
  - `StrategyDefinition` alanları: `strategy_id`, `name`, `code(unique)`, `description`, `owner_type=admin`, `created_by`, `status`, `active_version_id`, `created_at`, `updated_at`
  - `StrategyVersion` alanları: `version_id`, `strategy_id`, `version_number`, `config_json`, `config_schema_version`, `created_by`, `created_at`, `version_hash`
  - Hash kuralı uygulandı: `sha256(canonical_config_json + strategy_id + version_number + config_schema_version)`
  - `StrategyVersion` immutable: SQLAlchemy `before_update` bloklama
  - Activation pointer modeli: `active_version_id` + status güncellemesi
  - Strategy registry read katmanı: strategy/version/active set çözümlemesi
- **6.2 Deterministic Kernel Contract:**
  - `DecisionContextInput` sözleşmesi eklendi (canonical hash üretimi)
  - `POST /api/strategy-domain/admin/kernel/evaluate` pure-kernel contract endpoint’i eklendi
  - `DecisionResult` sözleşmesi: `action`, `order_intent`, `size`, `price_reference`, `confidence`, `risk_score`, `reason_codes`, `context_hash`, `decision_hash`
  - Typed reject davranışı eklendi:
    - `validation_error`
    - `strategy_version_not_found`
    - `strategy_version_hash_mismatch`
    - `risk_gate_blocked`
- **Admin UI (`/admin/strategies`):**
  - Strategy list/detail, version list, create definition, create version, activate version, archive strategy
  - Deterministic kernel evaluate paneli
  - Panel `/admin/proofs`’tan bağımsız bounded context olarak ayrıldı
- **Yeni API yüzeyi:**
  - `GET/POST /api/strategy-domain/admin/strategies`
  - `GET /api/strategy-domain/admin/strategies/{strategy_id}`
  - `POST /api/strategy-domain/admin/strategies/{strategy_id}/versions`
  - `POST /api/strategy-domain/admin/strategies/{strategy_id}/activate/{version_id}`
  - `POST /api/strategy-domain/admin/strategies/{strategy_id}/archive`
  - `GET /api/strategy-domain/admin/registry/active`
  - `POST /api/strategy-domain/admin/kernel/evaluate`
- Migration/DB:
  - Alembic: `20260311_0015_strategy_domain_core.py`
  - SQLite compatibility: `strategy_definitions`, `strategy_versions` tabloları
- Testler:
  - `/app/test_reports/iteration_21.json` (backend/frontend pass)
  - `test_phase6_iter2_comprehensive_strategy_domain.py` (testing agent comprehensive suite)
  - Lokal regresyon: `test_phase6_iter1_strategy_domain_kernel.py` + iter5/iter4 toplam 9/9 pass

### 2026-03-11 (Faz-6.3 — Runtime Execution Skeleton + Hot/Cold Trace Skeleton)
- Kullanıcı karar seti uygulandı: **kapsam B (6.3 + hot/cold skeleton), Redis event bus, ayrı process worker iskeleti, paper/mock adapter boundary**
- **6.3.1 Redis Event Bus Contract:**
  - Yeni servis: `runtime_event_bus_service.py`
  - Event envelope alanları sabitlendi:
    - `event_id`, `event_type`, `correlation_id`, `causation_id`, `partition_key`, `created_at`, `schema_version`, `payload`, `payload_hash`, `ordering`
  - At-least-once semantiği + idempotent tüketim için `processed event set` eklendi
- **6.3.2 Event Zinciri:**
  - `decision.produced`
  - `execution.intent.created` / `execution.intent.rejected`
  - `execution.order.submission_requested`
  - `execution.order.submitted`
  - `execution.order.updated`
  - `execution.order.finalized`
- **6.3.3 Decision -> ExecutionIntent Mapper:**
  - Yeni servis: `runtime_execution_service.py`
  - Kurallar:
    - `REJECT` -> intent yok, rejected event
    - `HOLD` -> intent yok, `hold_noop` rejected event
    - `BUY|SELL|CLOSE` -> immutable intent üretimi
  - `intent_hash` deterministic canonical hash ile üretiliyor
- **6.3.4 Worker Skeleton (ayrı process hazır):**
  - Worker giriş noktası: `backend/workers/execution_worker.py`
  - API tetikleme iskeleti: `POST /api/strategy-domain/admin/runtime/worker/run-once`
  - Duplicate event toleransı: processed-set + ack akışı
- **6.3.5 Paper/Mock Adapter Boundary:**
  - Yeni adapter: `paper_exchange_adapter_service.py`
  - Deterministic lifecycle simülasyonu: `NEW`, `PARTIALLY_FILLED`, `FILLED|CANCELED|REJECTED`
  - **Canlı submit bu fazda kapalı** (safety-first)
- **6.3.6/6.3.7 Hot/Cold Storage Skeleton:**
  - Yeni tablolar:
    - `decision_trace_hot` (48h TTL alanı ile)
    - `decision_trace_cold` (append-only audit/replay özet)
  - Runtime dispatch anında hot trace, worker finalization sonrası cold trace yazılıyor
- **Yeni runtime API yüzeyi:**
  - `POST /api/strategy-domain/admin/runtime/dispatch`
  - `POST /api/strategy-domain/admin/runtime/worker/run-once`
  - `GET /api/strategy-domain/admin/runtime/intents`
  - `GET /api/strategy-domain/admin/runtime/intents/{intent_id}/events`
  - `GET /api/strategy-domain/admin/runtime/hot-traces`
  - `GET /api/strategy-domain/admin/runtime/cold-traces`
- **Admin UI güncellemesi (`/admin/strategies`):**
  - Runtime dispatch, worker run-once, intents/hot/cold görünümleri eklendi
- Migration/DB:
  - Alembic: `20260311_0016_runtime_execution_skeleton.py`
  - Yeni modeller: `ExecutionIntent`, `ExecutionIntentEvent`, `DecisionTraceHot`, `DecisionTraceCold`
- Testler:
  - `/app/test_reports/iteration_22.json` (backend/frontend pass)
  - `test_faz63_runtime_skeleton.py` (testing agent suite)
  - Lokal regresyon: `test_phase6_iter3_runtime_skeleton.py` + `test_phase6_iter1_strategy_domain_kernel.py` + iter5 toplam 6/6 pass

### 2026-03-11 (Faz-6.4/6.5 — Regime Gating + Risk Orchestrator)
- Regime gating admin endpointleri tamamlandı: bindings/evaluate/overview, regime snapshot persistence, reject audit log.
- Admin Strategies UI: regime binding editor + deterministic allowed/blocked demo + snapshot/reject dağılımı paneli.
- Risk Orchestrator policy modeli + migration (`20260311_0018_risk_orchestrator_core.py`) + SQLite fallback.
- Pre-trade risk gate runtime dispatch’e bağlandı (account/symbol exposure, strategy concurrency, cooldown, frequency, duplicate suppression, daily loss, kill-switch).
- In-trade supervisor endpointi + status snapshot + risk reject audit log’u eklendi.
- Admin Risk Orchestrator sayfası (/admin/risk-orchestrator) eklendi (policy editor, status, supervisor run, reject list).
- Decision context’e `account_id` eklendi; execution intent’ler account bazlı takip ediyor.
- PostgreSQL-only sweep tekrarlandı: mongo/pymongo/ObjectId kalıntısı yok.
- Testler: curl risk-orchestrator + regime evaluate, Playwright screenshot (risk orchestrator + strategies).

### 2026-03-11 (Faz-7.1/7.2/7.5 — Hardening Blok-1)
- Manifest zinciri eklendi: `prev_chain_hash`, `chain_hash`, `chain_position` (GENESIS bootstrap).
- Verify endpoint chain doğrulaması dönüyor; chain bozulması tespit ediliyor.
- Batch verify endpointi eklendi: `GET /api/audit/artifacts/verify-all` (artifact_type/date/status filtreleri).
- Admin Proof paneli: batch verify UI + chain alanları görünür oldu.
- Release Gate Hardening: READY/WARNING/BLOCKED statüleri, clock drift ve worker lag eşikleri, rate-limit/permission/risk-orchestrator/chain kontrolleri.
- Release gate CLI ve admin UI statü renkleri güncellendi.
- Testler: curl batch verify + release gate; Playwright: proofs + phase4 live control.

### 2026-03-11 (Faz-7.3/7.4/7.6/7.7 — Hardening Blok-2)
- Runtime DLQ/Quarantine eklendi: retry queue + dead letter + quarantine; max_retry=3 ve exponential backoff.
- Quarantine admin ekranı (/admin/runtime/quarantine) + replay/dismiss/mark_failed aksiyonları.
- Stuck intent recovery servisi + admin ekranı (/admin/runtime/recovery) + sync/replay/cancel/mark_failed aksiyonları.
- System alerts tablosu + admin dashboard banner + ack endpointleri (internal alert pipeline).
- Risk orchestrator analytics endpointi + UI (/admin/risk-orchestrator/analytics), audit tabanlı trend ve dağılımlar.
- Release gate chain/risk alertleri + kill-switch audit + günlük loss uyarıları.
- Testler: curl stuck-intents + analytics + system-alerts, Playwright runtime quarantine/recovery/analytics.

### 2026-03-11 (Alert Pipeline v2 — Resend/Slack boundary + Weekly CSV)
- System alerts v2: fingerprint/entity_key/root_cause_code/state_key + delivery_status alanları.
- Dedup (10 dk) + rate-limit (5/min, CRITICAL 3/30m) + severity routing uygulandı.
- Resend/Slack channel adapter iskeleti (config missing → CONFIG_MISSING), channel config endpointi eklendi.
- Weekly CSV report generator + scheduler (Pzt 09:00 Europe/Berlin) + manual run/download endpointleri.
- Release gate warning/blocked alertleri ve quarantine growth uyarıları eklendi.
- Fix: /api/phase4/admin/release-gate 500 (timezone diff) giderildi.
- Testler: curl config/report/run + release-gate; smoke UI test.

### 2026-03-11 (Weekly CSV Archive + Admin Reports)
- WeeklyReportArchive modeli + retention (12 ay) + checksum üretimi.
- /admin/reports/archive list/filter + download (verify opsiyonlu) endpointleri.
- Admin Reports Archive UI (liste, filtre, checksum, download).
- Weekly report manual run artık archive kaydı oluşturuyor; download audit log yazılıyor.

### 2026-03-11 (Test-order Quantity Fix + Live Proof)
- Test-order quantity normalization: minQty*5 fallback + stepSize/precision + minNotional guard + typed reject codes.
- Exchange test-order artık quantity<=0 göndermiyor; invalid quantity exchange’e gitmeden reject ediliyor.
- Testnet live proof tekrar koşuldu: validate ✅, test-order ✅ (NEW → FILLED).
- Testnet readiness artık release gate BLOCKED olsa bile test-order’a izin veriyor.

### 2026-03-11 (Admin Bulk Approvals + Alert Ops Simulate)
- /admin/user-approvals list + bulk approve/reject endpoints (reject reason zorunlu) + audit log (USER_APPROVAL_BULK_APPROVED/REJECTED).
- Admin User Approvals UI: arama/sıralama, checkbox seçim, bulk approve/reject + reject reason.
- Ops alert simulate endpoint (/api/ops-alerts/simulate) + POST /admin/system-alerts/config (config refresh).
- Role set güncellendi: super_admin/admin/ops/user; require_admin ops’u kabul ediyor.

## 6) Prioritized Backlog
### P0 (Sonraki kritik adımlar)
- Resend/Slack secrets sağlanınca Alert Pipeline v2 kanal aktivasyonu + uçtan uca test
- Bot profile/risk/strategy için delete endpointleri + soft delete stratejisi
- Admin user-management modülünü approval sonrasına genişletme (disable/enable, filtreleme, audit trail)
- Alembic migration’larda rollback senaryolarının staging doğrulaması

### P1
- Strategy param validasyonları ve Basic/Advanced user modları
- Correlation/cluster exposure kontrolünün gerçek korelasyon matrisi ile güçlendirilmesi
- Session protection: cooldown + frequency limit + günlük PnL gate
- Monitoring detayları: per-symbol latency, dead-letter benzeri failed-event kuyruğu
- Hardening metriklerinin kalıcı snapshot/raporlanabilir hale getirilmesi
- Hardening checklist trend analizi (run history grafiği + regresyon alarmı)
- Backtest insights filtreleme (market/timeframe/risk etiketine göre)

### P2
- Bybit/OKX adapter stubları
- Gelişmiş raporlama ve zaman serisi chartları
- Strategy backtest sonuç kartları (onaylandı)
- İnce ayar UX optimizasyonları ve onboarding akışları

## 7) Next Tasks List
1. Resend/Slack secrets sağlanınca Alert Pipeline v2 kanal aktivasyonu + uçtan uca test
2. Admin user-management paneli (/admin/users)
3. System Alerts panel upgrade (severity/entity filter, timeline, bulk acknowledge)
4. CSV diff analizi (report A/B)
5. Legacy endpoint cleanup
6. Adapter stubs (Bybit/OKX)
7. User platform başlangıcı (dashboard/portfolio)

## 8) 2026-03-11 — Admin Domain Closure Güncellemesi
- **Tamamlandı (P0): Admin User Management**
  - Backend: `GET /api/admin/users`, `PATCH /api/admin/users/{id}/role`, `PATCH /api/admin/users/{id}/status`
  - Legacy uyumluluk korundu: `POST /api/admin/users/{id}/role|disable|enable`
  - Rol seti aktif: `super_admin`, `admin`, `ops`, `user`
  - Durum modeli aktif: `active`, `disabled`
  - Audit event’leri doğrulandı: `USER_ROLE_CHANGED`, `USER_DISABLED`, `USER_ENABLED`
- **Tamamlandı (P0): System Alerts Panel Upgrade**
  - Yeni admin sayfası: `/admin/system-alerts`
  - Özellikler: status/severity/alert_type/entity_key filtreleri, timeline, delivery status görünürlüğü, bulk acknowledge, single ack/resolve
  - Yeni frontend sayfası: `frontend/src/pages/AdminSystemAlertsPage.jsx`
- **Tamamlandı (P0): Admin Users UI**
  - Yeni admin sayfası: `/admin/users`
  - Özellikler: kullanıcı listeleme, arama/filtre/sıralama, satır bazlı rol atama, enable/disable
  - Yeni frontend sayfası: `frontend/src/pages/AdminUsersPage.jsx`
- **Tamamlandı: Alert Delivery Activation Config Akışı**
  - `POST /api/admin/system-alerts/config` artık payload alarak DB’ye güvenli (encrypted) kanal konfigürasyonu yazıyor
  - `GET /api/admin/system-alerts/config` kanal readiness + masked config döndürüyor
  - Yeni model/migration: `AlertChannelConfig`, `20260311_0023_alert_channel_configs.py`
  - `POST /api/ops-alerts/simulate` delivery_status ile çalışıyor
- **Erişim Politikası İyileştirmesi**
  - Frontend admin route guard güncellendi: `super_admin/admin/ops` admin paneline erişebiliyor
  - Home redirect ve sidebar admin-role aware hale getirildi
- **Test Durumu**
  - Testing Agent: `/app/test_reports/iteration_23.json`
  - Sonuç: Backend **21/21 pass**, Frontend admin users + system alerts akışları **pass**

### Güncel Kapanış Durumu (Admin Domain)
- [x] Admin user management
- [x] System alerts panel upgrade
- [x] Alert delivery **email-only gerçek kanal başarı doğrulaması** (Option C)

### Kalan P0
1. (Opsiyonel) `ALERT_FROM=admin@platform.dev` kullanımı için Resend domain verify (`platform.dev`) tamamlamak
2. (Opsiyonel) Slack webhook ekleyip ikinci kanal aktivasyonunu tamamlamak

## 9) 2026-03-11 — Admin Domain Final Step (Option C: Email-only Activation)
- Kullanıcı talebine göre Slack bekletildi, email kanalı aktive edildi.
- `/api/admin/system-alerts/config` ile email-only config akışı doğrulandı.
- `/api/ops-alerts/simulate` ile gerçek provider çağrısı doğrulandı; email tarafında `SENT` + `provider_id` alındı.
- Audit doğrulaması: `ALERT_DELIVERY_SUCCESS` (channel=`email`) kaydı oluştu.
- Panel doğrulaması: `/admin/system-alerts` üst satırda `channel_status=READY · email_channel=active · slack_channel=disabled`.
- Testing agent raporu: `/app/test_reports/iteration_24.json` (backend 9/9, frontend 100%).

### Not (Provider Constraint)
- `ALERT_FROM=admin@platform.dev` değeri Resend domain doğrulaması yapılmadığı için doğrudan gönderimde `domain not verified` hatası üretir.
- `ALERT_TO` alanında yazım düzeltmesi (`huseyinwural@gmail.com`) ile hesap sahibi test alıcısına başarılı gönderim doğrulandı.

## 10) 2026-03-11 — Spot Strategy Engine Faz-1 (P0) Uygulandı

### Uygulanan P0 Omurga
- **Daily Spot Tradable Universe**: Binance spot verisinden günlük universe yenileme (`/api/spot-strategy/universe/refresh`) + `spot_universe.json` artefact üretimi.
- **Market Data Collector (15m)**: Universe sembolleri için `market_data_store:{symbol}:15m` cache akışı ve **min 500 candle** bootstrap.
- **Indicator Layer**: EMA50, EMA200, RSI14, ATR14, VWAP hesaplama ve symbol bazlı cache (`/api/spot-strategy/indicators/{symbol}`).
- **Signal Engine**: Spot trend-pullback long mantığı (trend/pullback/RSI/volume spike/volatility) + skor alanları.
- **Risk + Position Control**: Spot pullback için %1 risk yaklaşımı, TP/SL (2%/1%), max open positions=3, max per symbol=1.
- **Paper Execution Lifecycle Hooks**: Trade open/close audit eventleri (`TRADE_OPENED`, `TRADE_CLOSED`, `STOP_LOSS_TRIGGERED`, `TAKE_PROFIT_TRIGGERED`) eklendi.
- **Performance Logger**: `daily_strategy_report.json` üretimi + endpoint (`/api/spot-strategy/report/daily/generate`).

### Yeni API Yüzeyi
- `GET /api/spot-strategy/universe`
- `POST /api/spot-strategy/universe/refresh`
- `GET /api/spot-strategy/market-data/{symbol}`
- `GET /api/spot-strategy/indicators/{symbol}`
- `POST /api/spot-strategy/scan/run`
- `GET /api/spot-strategy/scan/latest`
- `POST /api/spot-strategy/report/daily/generate`
- `GET /api/spot-strategy/report/daily`

### Test Durumu
- Testing agent: `/app/test_reports/iteration_25.json` → **11/11 PASS** (backend).
- Deep backend test: **16/16 PASS**.

### P1 (Sıradaki Güçlendirme)
1. TrendStrength + BTCRegime hard gate’lerini execution selection katmanına taşımak.
2. RelativeVolume + PullbackQuality skorlarının slot bazlı sıralama kararına bağlanması.
3. `max_open_positions` altında en yüksek skorlu sinyali seçen selection layer.
4. BTC hostile freeze guard (2 candle freeze) ve rapor metriklerine etkisinin izlenmesi.
