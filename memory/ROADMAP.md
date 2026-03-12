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
- Phase-7 CT + UX kapanışı:
  - API contract snapshot + contract CI gate
  - `/api/user/reports/weekly` 501 stub contract
  - Responsive user pages + sticky nav + compact mode
  - Accessibility audit artefact
  - Phase-7A execution contract preparation artefact

## P1 (Sıradaki)
1. PG-01 weekly reporting engine implementasyonu:
   - `/api/user/reports/weekly` canlı backend
   - `/user/reports` UI
   - hafif text/pdf fallback + CSV/JSON artefact üretimi
2. Phase-7A Trade Execution Control Panel implementasyonu (admin/backend sonra user panel)
3. Execution contract compliance test paketi (`execution_intent_contract.json` ile)

## P2 (Backlog)
1. Explainability layer (reason-codes, decision trace, strategy explanation)
2. Strategy engine architecture genişletmesi (meta-strategy wrapper ve kurumsal karar katmanı)
3. Legacy endpoint cleanup ve teknik borç azaltımı
