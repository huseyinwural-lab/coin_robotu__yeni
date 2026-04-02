# ROADMAP — Prioritized Backlog

## 2026-03-27 (P2 Risk-Based Stateful Auth uygulandı)
- ✅ Tamamlanan çekirdek:
  - Deterministic/stateless risk engine
  - Scope-aware step-up auth
  - Risk response standardizasyonu
  - Grace-risk override
  - Suspicious activity + security metrics endpointleri
  - Recovery quorum + delay flow
  - Secret provider abstraction (plan-to-code)

### Kalan geliştirmeler (P2 devam)
- Suspicious activity için daha gelişmiş anomaly kural setleri
- Recovery akışına domain-level SLA/notification genişletmeleri
- AWS KMS / Vault gerçek provider implementasyonu

## 2026-03-27 (P1 Production Security Hardening Kapandı)
- ✅ Tamamlandı:
  - All-users new-device MFA challenge enforcement
  - Session hijack koruması (IP/device değişiminde re-auth + invalidation)
  - Local GeoIP audit context
  - Email OTP hardening + resend/rate controls
  - API standardizasyonu + backward compatibility/deprecation
  - Admin MFA reset/recovery + audit genişletmeleri
  - MFA UX wizard/state iyileştirmeleri

### Kalan Öncelikler
- P1 devam: Sumsub AML entegrasyonu (manuel veri fazı)
- P1 devam: Deterministik risk scoring genişletmesi (LLM yok)

## 2026-03-27 (P0 Security BLOCKER Kapandı)
- ✅ Tamamlandı (P0):
  - Challenge-based login + token-after-MFA
  - 24h grace + grace sonrası hard block
  - JWT `mfa_verified/device_id` + httpOnly cookie binding
  - Brute-force lock (5 fail / 30dk, user+IP)
  - TOTP anti-replay + backup code hardening
  - Step-up auth (10dk) + kritik endpoint enforcement

## P1 (Sıradaki)
- Sumsub AML entegrasyonu (ilk faz: manuel veri girişi destekli şema/akış)
- Deterministik risk scoring genişletmesi (LLM yok)

## P2 (Backlog)
- Multi-tenant capital rebalance automation (policy/simulation/manual -> scheduler/kill-switch fazları)

## 2026-03-25 (P1.3 tamamlandı)
- ✅ Tamamlandı:
  - Retention trend (weekly/monthly)
  - Segment profitability + churn risk/re-engagement
  - Economics export (CSV/XLSX)
  - Daily/weekly scheduled snapshot + trend
- 🟡 Sonraki P1 adımı:
  - Retention alerting (drop threshold)
  - Segment bazlı otomatik aksiyon önerisi

## 2026-03-25 (P1.2 tamamlandı)
- ✅ Tamamlandı:
  - User Economics aggregate katmanı
  - `/api/admin/users/economics` endpointi
  - User Economics admin UI (filter + KPI + top users + churn + cohort)
- 🟡 Sonraki P1 adımı:
  - Cohort retention eğrileri (zaman serisi)
  - User profitability segmentation (VIP/standard/new)

## 2026-03-25 (P1 başlangıç tamamlandı)
- ✅ Tamamlandı:
  - Revenue Engine Core (ledger + write path + summary API + admin UI)
  - deterministic summary + idempotent ledger write
- 🟡 Sonraki P1 genişletme:
  - User economics (ARPU/ARPPU/LTV/churn/cohort)
  - Revenue detay kırılımları (strategy/tag/market bazlı)

## 2026-03-25 (P0 closure blocker netleşti)
- ✅ Tamamlandı:
  - Spot/Futures live zincir teknik koşumu
  - Futures live credential + probe
- 🔴 Blocker:
  - Live key üzerinde ingest edilebilir trade coverage görünmüyor (`myTrades/userTrades` boş)
  - Bu nedenle spot+futures combined `live_transition_ready=true` alınamadı

## 2026-03-25 (Proxy geçiş sonrası durum)
- ✅ Tamamlandı:
  - Spot/Futures live proxy entegrasyonu aktif
  - Kademeli düşük ağırlık spot ingest operasyonu
- 🔴 Kalan:
  - Spot hesabında gerçek trade coverage üretimi (şu an sembol kontrollerinde trade=0)
  - Spot live-gate true sonrası P1 başlangıcı

## 2026-03-25 (Low-weight operasyona geçiş)
- ✅ Tamamlandı:
  - Spot live ingest düşük ağırlık modu
  - Drift highlight severity etiketleri
- 🟡 Kalan:
  - Spot live için gerçek trade coverage üretimi (fetched/inserted > 0)
  - Spot `live_transition_ready=true` sonrası P1 Revenue Engine başlangıcı

## 2026-03-25 (Spot rerun durumu)
- ✅ Tamamlandı:
  - Drift highlight UI (trace compare) eklendi
  - Spot sembol seti ve 1 yıllık ingest koşumu denendi
- 🔴 Kalan blocker:
  - Spot live tarafında Binance request-weight limiti (`429 -1003`) nedeniyle coverage üretilemedi
  - Spot `live_transition_ready=true` alınmadan P1'e geçiş beklemede

## 2026-03-25 (P0 zincir tekrar koşumu sonucu)
- ✅ Tamamlandı:
  - Spot live + futures test zinciri tekrar koşuldu
  - P0 endpointleri market-scope bazlı çalışacak şekilde hardening yapıldı
  - Trace geçmiş karşılaştırma UI eklendi
- 🟡 Kalan:
  - Spot live scope’ta gerçek trade coverage olmadığı için `live_transition_ready` henüz `false`
  - Kullanıcı kuralı gereği P1 Revenue Engine geçişi beklemede

## 2026-03-25 (Traceability Increment)
- ✅ Tamamlandı:
  - request_id bazlı resolution trace response
  - aynı sayfada audit drawer/modal
  - unique request_id doğrulaması + acceptance test PASS

## 2026-03-25 (P0 Devamı Güncelleme)
- ✅ Tamamlandı:
  - Spot live + futures test credential/probe doğrulama
  - P0 ingestion çağrılarının 200 stabil dönmesi
  - Decision Trace Timeline UI enhancement
  - Proxy header ve market alias backend hardening
- 🔴 Açık kalan:
  - `live_transition_ready=true` kapanışı için gerçek trade coverage ile ingest/pnl/reconciliation kontrollerinin PASS olması
  - Futures live proxy URL/token netleştirmesi (kullanıcıdan eksik bilgi)

## 2026-03-25 (Task-1 Güncelleme)
- ✅ P0 tamamlandı: Credential Orchestration UI 8/8 genişletme maddesi kapatıldı.
  - Multi-exchange: `binance/bybit/okx`
  - Market modeli: `spot/usdt_perp/coin_perp`
  - Purpose: `market_data/execution/fallback`
  - Base URL + Proxy/Egress görünürlüğü
  - Routing matrix + resolution preview + probe state dashboard
- ✅ Backend uyumu tamamlandı: purpose filter + yeni enum/alias desteği.
- 🔴 Açık blocker (P0 closure): Spot+Futures live E2E için Futures proxy erişim bilgisi bekleniyor (451 external blocker).

## 2026-03-25 Güncel Durum
- ✅ Tamamlanan ana iş: Admin Credential Orchestration Layer
  - Admin master credential yönetimi + approval/probe/audit
  - Credential assignment rules (user/admin/admin_fallback)
  - Deterministic resolver ve user response routing preview
- 🔴 Açık blocker (ayrı iş paketi): Live Spot 451 egress remediation
  - Hedef: allowed-region live spot proxy/egress ile 451 kaldırma
  - Spot+Futures live gate closure bu iş tamamlanınca yeniden doğrulanacak

## 2026-03-24 P0.5 Closure Durumu
- ✅ Tamamlandı:
  - Observability endpoint standardizasyonu + frontend uyumu
  - Request-level reason validation enforcement
  - MFA bypass audit + UI badge
  - Endpoint contract freeze korunumu (impact_delta/risk_delta/numeric_changes + bulk preview summary)
- 🔜 Sonraki net adım:
  - Spot regional erişim blocker kalkınca Spot+Futures live-gate final PASS (Commercial Ops P0 tam kapanış)

## 2026-03-24 Commercial Ops P0 (Aktif Sprint)
- ✅ Tamamlandı (Bu tur):
  1. Canonical trade schema + PnL/Reconciliation domain tabloları
  2. Binance REST ingestion endpointleri (Spot + Futures)
  3. PnL engine (gross/net + fee breakdown)
  4. Reconciliation loglama (drift + tolerance)
  5. Data quality + live transition gate + CSV standard export
  6. WebSocket bootstrap endpointi (listenKey/ws URL)
- 🔴 P0 Kalan:
  1. WebSocket consumer worker ile gerçek zamanlı trade ingestion
  2. `huseyinwural@gmail.com` üzerinde live tam E2E doğrulama
  3. Drift tolerans kalibrasyonu ve reconciliation doğruluk tuning
  4. Live 3/3 kontrol sonrası controlled live geçişi
- Bloker:
  - Preview backend 502 (runtime `postgres.internal` çözümleme sorunu), canlı endpoint testleri beklemede.

## 2026-03-24 Commercial Ops P0 Closure Durumu (Güncel)
- ✅ Tamamlandı:
  1. Runtime blocker fix (health 200, DB reachable)
  2. Futures-only gerçek live E2E (ingest→pnl→reconciliation→gate)
  3. Drift kalibrasyonu `%0.3` ile reconciliation pass
  4. WS worker lifecycle (start/status/stop, reconnect+dedup)
  5. Export schema + PnL consistency doğrulaması
- ⚠️ Açık dış blocker:
  - Binance Spot endpointleri `451 restricted location` (infra/region kaynaklı)
- 🔴 Kalan net P0 kapanış adımı:
  - Spot erişim blocker kalkınca Spot+Futures birlikte live-gate pass alınması

## 2026-03-23 P2 Faz Sonuçları
- ✅ Tamamlandı:
  1. Check history/trend + flapping detection
  2. Override analytics panel
  3. Before/after remediation compare
  4. Incident timeline + category filters
  5. Dynamic risk scoring badge
  6. Export V2 (history + analytics + timeline + risk)

## Sonraki Gelişim (P3 öneri)
1. Predictive risk forecasting (trend-based forward score)
2. Incident correlation graph (check-fail ↔ override ↔ mode switch)
3. Team ops workflows (assignment/ack/sla tracking)

## 2026-03-23 P1 Kapanış Durumu
- ✅ P1 mandatory closure maddeleri tamamlandı:
  1. Evidence gap (test report + smoke artefact + endpoint/state evidence)
  2. API key test control (success/fail, reason, summary, last tested, audit)
  3. Permission breakdown (exchange bazlı read/write/trade)
  4. Exchange health görünümü (connection/auth/permission + remediation)
  5. Mode history
  6. Order scenario matrix
  7. Auto-refresh + pause + interval
  8. FAIL alert visibility + override risk banner
  9. Filtered JSON export
  10. Reason-code → runbook linkleme

## Sonraki Faz (P2 - Planlanmış)
1. Check history / trend / flapping tespiti
2. Override analytics (sebep dağılımı, sıklık, etki)
3. Before/after remediation compare (latency ve state transition farkları)

## 2026-03-23 Update (Production Gate P0)
- ✅ Tamamlandı:
  1. Backend-first Production Gate state engine (`NO_GO | GO | GO_WITH_OVERRIDE`)
  2. Deploy/LIVE hard-block enforcement (403) + validation block (400)
  3. Override create/revoke/expiry akışları (super_admin + max 30 dk + strict enum)
  4. Checklist enforcement + stale/running check GO blokajı
  5. Mode transition guard (reason + confirmation + audit)
  6. Rerun all/single checks + fail reason/remediation payload standardı
  7. JSON export endpointleri
  8. Execution Readiness sayfasının write-capable Control Panel’e dönüşümü

## P1 (Sıradaki)
1. Auto-refresh interval + incremental polling stratejisi
2. Fail alert + exchange health detay görünümü (operator-first)
3. Export UX iyileştirmeleri (scope/filters/date range)

## P2 (Backlog)
1. Check history/trend görselleştirme
2. Override analytics (before/after, frequency, impact)
3. Gate kararlarının timeline/incident korelasyonu

## 2026-03-22 Update (Faz-2 Tam Kapanış)
- ✅ Tur-1 tamamlandı: Freshness/SLA + KPI Recommendation + Trend/Analytics
- ✅ Tur-2 tamamlandı: Export/Data Access + Universe Bulk UX + Debug policy + UX polish

## Sonraki Adım (Production Readiness)
1. Prod rollout planı + rollback stratejisi kilitleme
2. Load/risk analizi (yük altında export + scanner + trend etkisi)
3. SLO/SLA alarm eşikleri ve operasyon runbook revizyonu

## 2026-03-22 Update (Faz-2 Tur-1)
- ✅ Tamamlandı:
  - Freshness / SLA
  - KPI Recommendation
  - Trend / Analytics

## Faz-2 Tur-2 (Sıradaki)
1. Export / Data Access
   - DB tabanlı async export job
   - CSV + JSON + API link generator
2. Universe Bulk UX
   - CSV paste/import + validation + preview + partial apply
3. Debug policy
   - Debug effective universe: super_admin-only + toggle + prod hide
4. Hızlı kazanımlar
   - Auto-refresh interval ayarı
   - Global error state banner
   - Empty state reason zenginleştirme

## 2026-03-21 Faz-1 Durum
- ✅ Tamamlandı: Rollout Orchestrator, Scanner Control, Risk/Exposure, Slow Strategy/Symbol Control

## Sonraki Faz (P2)
1. Universe Management derinleştirme (symbol add/delete ayrı akış + 100+ import UX rafinesi)
2. Freshness / SLA management (stale detection + rescan-stale + threshold UI)
3. KPI Recommendation Engine (apply/reject/postpone + history)
4. Trend & Analytics panel (time-range drill-down chart)
5. Export & Data Access (CSV/JSON + API link generator)
6. Global audit/polish (auto-refresh interval config, immutable audit görünürlüğü)

## 2026-03-21 Final Update
- ✅ Final Cleanup + Real State + Lock tamamlandı (tek panel, gerçek state validation, action-result bağları, ws debug, gate rules, override impact, exchange action, mode visibility, alert filter).

## Sonraki Aşama (Ops)
1. Prod rollout planı (kademeli canlıya alma)
2. Rollback runbook (tetikleyici + adım adım geri dönüş)
3. Post-deploy gözlem KPI seti (gate, ws, guard, alert, override)

## 2026-03-21 UI Update
- ✅ Admin içerik yüzeylerinde koyu kutu temizliği tamamlandı (açık yeşil tema)

## 2026-03-21 Update (P1 Production Readiness Lock)
- ✅ **P1 tamamlandı**
  - config single-source quote policy lock
  - UI şeffaflık (allowed quotes + invalid quote guard visibility)
  - state validation checklist
  - action→result traceability iyileştirmesi
  - deployment checklist + rollback plan dokümantasyonu

## P2 (Sıradaki)
1. Release Gate final:
   - rule breakdown
   - fix_hint
   - history
2. Override hardening:
   - TTL countdown UI
   - active override ayrı panel
   - cancel sonrası anlık state etkisi
3. WS debug:
   - last_error
   - reconnect reason
   - son 10 connection log
4. Mode visibility:
   - üst alanda `MODE: MOCK / LIVE`

## 2026-03-21 Update (Quote Asset Constraint)
- ✅ **P0 tamamlandı**
  - USDT/USDC hard constraint execution + scanner/signal + guard telemetry hatlarında enforce edildi
  - Invalid quote hata sözleşmesi standardize edildi
  - Override bypass engeli doğrulandı (hard rule)

## P1 (Sıradaki)
1. Config taşıma
   - `config/trading.json` altında `allowed_quote_assets: ["USDT", "USDC"]`
2. UI görünürlük genişletmesi
   - Summary panelde `Allowed Quote Assets: USDT, USDC`
   - Trade/Block detaylarında reason vurgusu

## P2 (Backlog)
1. Balance check daraltma (yalnız USDT/USDC bakiyeleri)
2. Drift detection: API key yetki denetiminde USDT/USDC trade scope doğrulaması

## 2026-03-21 Update (Unified Pipeline Panel)
- ✅ **P0 tamamlandı**
  - Runtime action contract standardizasyonu (`status, trace_id, message, state_snapshot`)
  - Zorunlu trace/audit görünürlüğü
  - Yeni `/admin/pipeline-operations` unified ekranı
  - Geçiş stratejisi: legacy ekranlar korunarak yeni sayfaya linkleme

## P1 (Sıradaki)
1. Release Gate re-check script wrapper derinleştirme
   - mevcut `scripts/ci_*` üzerinden rule breakdown + fix hint üretimi
2. Override lifecycle sıkılaştırma
   - strict TTL cap doğrulama
   - aktif override görünürlüğü iyileştirme
   - cancel override akışının operasyonel netleştirilmesi
3. Guard telemetry genişletmesi
   - blocked-trades endpoint derinliği + reason aggregation netleştirme

## P2 (Backlog)
1. WebSocket health session geçmişi + çoklu bağlantı görünürlüğü
2. Exchange monitoring drift aksiyonları (`revalidate_key`, `disable_key`) operasyonel UX iyileştirmesi
3. Alert engine policy version history + rollback ergonomisi

## 2026-03-18 Update
- ✅ FAZ-C Ultra Minimal Closure tamamlandı:
  - `/user/trade` tek nokta trade entry
  - validate→open-position zorunlu akış
  - positions execution_mode görünürlüğü
  - screener→chart bridge
  - minimal filter layer + `/api/screener` backend sync
  - C1-C6 E2E PASS
- 🔜 Sonraki odak: Phase-9B hardening, ops script sağlamlaştırma, düşük öncelikli teknik borç temizliği.

## 2026-03-18 Update (Telemetry + Explainability)
- ✅ Guard telemetry + explainability mini fast close tamamlandı.
  - `/api/admin/guard-telemetry` hazır
  - `/admin/system-status` guard kartı canlı
  - `/api/screener` + trade response explain alanları deterministic
- 🔜 Sonraki odak: explain detaylarını expandable drawer ile artırma ve telemetry query maliyet optimizasyonu.

## 2026-03-18 Update (MFA + Brand Settings)
- ✅ Optional MFA (User+Admin) tamamlandı (email OTP + TOTP, login sonrası step-up)
- ✅ Kalıcı branding tamamlandı (DB logo saklama + admin upload endpoint + global yayın)
- ✅ Admin `brand-settings` ekranı ve panel nav entegrasyonu tamamlandı.

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
- Iteration-53 kapanışı:
  - Execution Advanced Actions tamamlandı
  - Position management intent pipeline (close/partial/reverse/stop/tp) canlı
  - User `/user/positions` + admin `/admin/positions-monitor` sayfaları canlı
- Iteration-54 kapanışı:
  - Phase-9B Strategy Intelligence tamamlandı
  - conflict resolver + dynamic rebalance + hedge suggestion engine canlı
  - admin `/admin/strategy-intelligence` + risk simulation + manual override audit canlı
  - user execute/positions intelligence blokları canlı

## P1 (Sıradaki)
1. Phase-9B hardening & optimization:
   - conflict resolver policy tuning (win-rate / slippage bazlı)
   - rebalance cadence governance (time-window + max-shift caps)
   - hedge önerisi execution-ready intent üretimi
2. Position intelligence:
   - liquidation early-warning notifier
   - strategy-level position heatmap
3. Institutional controls:
   - override approval workflow (4-eyes principle)
   - simulation scenario library (stress/volatility/regime templates)

## P2 (Backlog)
1. Legacy endpoint cleanup ve teknik borç azaltımı
2. Advanced PDF reporting görsel kalite upgrade
3. Strategy performance attribution raporları (haftalık/aylık)

---

## 2026-03-15 Güncel Öncelik Haritası

### P0 (Kapatıldı)
- #797 Son Düzeltme Mini Paketi eksikleri doğrulandı ve kapatıldı.
- CI gate’ler (drift/stage/prod), frontend frozen-lockfile kurulumu, admin login smoke PASS.
- Credential cleanup final (deprecated admin domain literal izi kaldırıldı).
- RISK-1..RISK-6 parametrik Risk Engine paketi backend’de devreye alındı.

### P1 (Aktif)
1. FINAL-2 canlı rollout operasyonu (zaman bazlı):
   - DEPLOY-3 (24s MOCK stabilite)
   - DEPLOY-4 canary (12–24s)
   - DEPLOY-5 Top10 (24–48s)
   - DEPLOY-6 Top50 (2–3 gün)
   - DEPLOY-7 full USDT
2. FINAL-3 canlı log birikimi sonrası execution-quality final kalibrasyon tekrar koşumu
3. FINAL-5 tenant policy (global/tenant/user) operasyonel rollout ve yetkilendirme modeli

### P2 (Bekleyen)
1. Bybit/OKX gerçek execution adapter aktivasyonu (credential sağlandığında **MOCKED** -> live)
2. Docker image reproducibility doğrulaması (harici docker runner)
3. Smart order routing (spread/liquidity/slippage bazlı venue seçimi)
4. Rejim -> risk profile otomasyonu
5. Explainability 2.0 ve canary otomasyon pipeline
