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
- Iteration-50 kapanışı:
  - PG-01 canlı weekly reporting (`/api/user/reports/weekly` + artifacts + manifest)
  - Phase-7A execution backend/admin (policy registry, precheck, intent queue, admin approve/reject)
  - User `/user/reports` + `/user/execute` sayfaları
  - Scanner/Signals -> Execute deep-link entegrasyonu
  - Execution contract compliance gate + test artefact’ları
- Iteration-51 kapanışı:
  - Phase-8 Explainability Engine tamamlandı
  - Signal/Trade/Execution decision-trace endpointleri canlı
  - Strategy explain + 7 günlük trace coverage endpointi canlı
  - 90 gün retention policy aktif
  - User Signals/Trades/Execute explainability panelleri tamamlandı
- Iteration-52 kapanışı:
  - Phase-9A Strategy Meta Engine + Portfolio Risk Layer tamamlandı
  - Risk gate execution preview pipeline içine alındı
  - Cluster exposure + strategy allocation dashboard’ları canlı
  - User execute risk impact + signals/trades attribution görünür

## P1 (Sıradaki)
1. Phase-9B Advanced Meta Orchestration:
   - çapraz-strateji conflict resolver (aynı symbol/karşıt yön netting)
   - dynamic capital rebalance (intraday)
   - portfolio-level hedging öneri katmanı
2. Execution panel advanced actions:
   - close/partial close/reverse intent contract’larını canlı aksiyonlara taşıma
3. Risk governance:
   - admin manual override audit trail
   - rule simulation/sandbox mode

## P2 (Backlog)
1. Legacy endpoint cleanup ve teknik borç azaltımı
2. Advanced PDF reporting görsel kalite upgrade
3. Strategy performance attribution raporları (haftalık/aylık)
