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

## 6) Prioritized Backlog
### P0 (Sonraki kritik adımlar)
- Canlı PostgreSQL + Redis ortamında fallback’siz doğrulama
- Bot profile/risk/strategy için delete endpointleri + soft delete stratejisi
- Admin user-management modülü (listeleme, disable/enable)
- Execution state machine’i daha granular hale getirme (created/submitted/ack/partial/filled/rejected/failed)
- Alembic migration’larda rollback senaryolarının staging doğrulaması

### P1
- Strategy param validasyonları ve Basic/Advanced user modları
- Correlation/cluster exposure kontrolü (BTC-ETH-SOL benzer risk kümeleri)
- Session protection: cooldown + frequency limit + günlük PnL gate
- Monitoring detayları: per-symbol latency, dead-letter benzeri failed-event kuyruğu
- Unified exposure modelinden çoklu exposure group modeline geçiş (majors/high-beta/mid-cap)

### P2
- Bybit/OKX adapter stubları
- Gelişmiş raporlama ve zaman serisi chartları
- Strategy backtest sonuç kartları (onaylandı)
- İnce ayar UX optimizasyonları ve onboarding akışları

## 7) Next Tasks List
1. Risk engine’i tek-gruptan çoklu exposure gruplarına genişlet (majors/high-beta/mid-cap)
2. Execution engine state machine adımlarını policy’ye bağlı granular hale getir
3. Hardening checklist endpoint/rapor ekranını ekle (idempotency, duplicate-protection, reconnect test sonuçları)
4. Backtest card’ları kullanıcı tarafında read-only karar destek ekranına taşı
5. Canlı emir öncesi dry-run senaryoları için otomatik test paketini artır
