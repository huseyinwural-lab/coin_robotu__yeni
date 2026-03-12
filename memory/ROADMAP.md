# ROADMAP — Prioritized Backlog

## P0 (Tamamlandı)
- Phase 5.1A Futures Liquidation Protection System
- ADL Risk Shield (detector + aggregator + policy + reducer + gate)
- Admin observability endpointleri:
  - `/api/admin/futures/risk/status`
  - `/api/admin/futures/liquidation-protection/status`
  - `/api/admin/futures/adl/status`
- Admin panel: `/admin/futures/liquidation-protection`

## P1 (İlerleme)
1. ✅ `futures_trend_follow_v1` (paper-only) strategy contract + engine + paper executor + admin strategy görünürlüğü
2. ⏳ Phase 5.1B Market Microstructure Guard (detector set + endpoint + panel)
3. ⏳ Phase 5.2 risk core + paper decision flow’un tek trace altında tam standardizasyonu
4. ⏳ Futures reversion/breakout stratejileri + dynamic leverage model

## P2 (Backlog)
1. Spot/Futures capital allocation engine formalizasyonu
2. User platform derinleşmesi (portföy, performans, kullanıcı metrikleri)
3. Multi-exchange adapter genişleme (Bybit, OKX)
4. Legacy endpoint cleanup
