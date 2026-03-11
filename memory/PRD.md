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

## 6) Prioritized Backlog
### P0 (Sonraki kritik adımlar)
- Kullanıcıdan geçerli Binance Testnet key alıp ilk kontrollü test order’ı gerçekten gönderme ve filled/cancelled sonucu doğrulama
- Canlı PostgreSQL + Redis ortamında fallback’siz doğrulama
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
1. Geçerli testnet key ile ilk order sonucu (filled/partial/cancelled) ve slippage doğrulamasını canlı testte tamamla
2. Hardening checklist trendini alarm geçmişiyle operasyonel eşiklere bağla
3. User approval paneline arama/sıralama + toplu onay (bulk action) ekle
4. Ops webhook teslimatını retry/backoff + dead-letter mantığıyla sertleştir
5. Valid key sonrası lifecycle evidence panelinde gerçek NEW/PARTIAL/FILLED kanıtını finalize et
