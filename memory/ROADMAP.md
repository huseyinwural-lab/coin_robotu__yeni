# ROADMAP — Prioritized Backlog

## P0 (Tamamlandı)
- Phase 5.1A → 5.8A institutional futures engine (risk/correlation/capital/tail-risk/live-readiness/scaling)
- Admin observability panelleri ve release-gate operability hattı
- Phase 6 / Faz-1 Görev-1:
  - User registry katmanı
  - JWT auth entegrasyonu (role=user otomatik, pending approval)
  - Backend owner-scope enforcement + veri izolasyonu
- Admin kullanıcı yönetimi UX düzeltmesi:
  - Admin/User kullanıcı menüsü ayrımı
  - Admin ekleme akışı (`admin-create`)
  - Admin panelde koyu butonların açık yeşil temaya geçirilmesi
- Phase L1 Core (Faz 1-3-5-6):
  - Legacy formula canonicalization
  - 4 strategy + 4 prefilter/scanner native entegrasyonu
  - DISABLED + SHADOW_ONLY governance lock
  - Admin panellerde legacy observability metrikleri
- Phase 6 toplu kapanış (NA-01..NA-06):
  - User scanner + signals + assisted queue
  - `/api/user/*` tam set + owner-scope + role separation
  - User dashboard/portfolio/trades/scanner/signals sayfaları + alias route’lar
  - Phase 6 validation report
- FB-01 + FB-02 kapanışı:
  - Research namespace isolation
  - Production formula gate (runtime + static import check + CI fail-fast)
  - 18M decomposition + excluded dual report
  - Legacy strategy matrix + integration report

## P1 (Sıradaki)
1. Phase 7 UI/UX hardening (UX-01/UX-02/UX-03):
   - mobile responsive
   - layout stabilization (sticky nav, compact table, loading skeleton)
   - accessibility (WCAG 2.1 AA)
2. Contract test paketleri (UI değişikliklerinde backend regresyonu önlemek için)
3. PG-01 haftalık performans raporu (`weekly_performance_report.pdf`, `weekly_trades.csv`, `weekly_strategy_stats.json`)

## P2 (Backlog)
1. Explainability layer (reason-codes, decision trace, strategy explanation)
2. Strategy engine architecture genişletmesi (meta-strategy wrapper ve kurumsal karar katmanı)
3. Legacy endpoint cleanup ve teknik borç azaltımı
