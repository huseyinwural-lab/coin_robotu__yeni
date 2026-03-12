# ROADMAP — Prioritized Backlog

## P0 (Tamamlandı)
- Phase 5.1A Futures Liquidation Protection System
- Phase 5.1B Market Microstructure Guard
- Phase 5.2 Futures Decision Trace Standard (trace contract + reason taxonomy + attribution + diagnostics)
- Phase 5.4 Dynamic Leverage Model (final leverage + size ratio + leverage observability)
- ADL Risk Shield (detector + aggregator + policy + reducer + gate)
- Admin observability endpointleri:
  - `/api/admin/futures/risk/status`
  - `/api/admin/futures/liquidation-protection/status`
  - `/api/admin/futures/adl/status`
  - `/api/admin/futures/microstructure/status`
- Admin panel: `/admin/futures/liquidation-protection`
- Admin panel: `/admin/futures/microstructure-guard`

## P1 (İlerleme)
1. ✅ `futures_trend_follow_v1` (paper-only) strategy contract + engine + paper executor + admin strategy görünürlüğü
2. ✅ Strategy Decision Diagnostics (false allow/reject + confidence/result + layer attribution)
3. ⏳ Phase 5.5 Controlled Testnet Hook
4. ⏳ Futures reversion/breakout stratejileri + dynamic leverage model entegrasyonu

## P2 (Backlog)
1. Spot/Futures capital allocation engine formalizasyonu
2. User platform derinleşmesi (portföy, performans, kullanıcı metrikleri)
3. Multi-exchange adapter genişleme (Bybit, OKX)
4. Legacy endpoint cleanup
