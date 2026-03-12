# ROADMAP — Prioritized Backlog

## P0 (Tamamlandı)
- Phase 5.1A Futures Liquidation Protection System
- ADL Risk Shield (detector + aggregator + policy + reducer + gate)
- Admin observability endpointleri:
  - `/api/admin/futures/risk/status`
  - `/api/admin/futures/liquidation-protection/status`
  - `/api/admin/futures/adl/status`
- Admin panel: `/admin/futures/liquidation-protection`

## P1 (Sıradaki)
1. `futures_trend_follow_v1` (paper-only) strateji implementasyonu
2. Yeni futures stratejilerinin risk foundation ile entegrasyonu
3. Dynamic leverage modelinin policy engine ile uyumlu aktif edilmesi

## P2 (Backlog)
1. Spot/Futures capital allocation engine formalizasyonu
2. User platform derinleşmesi (portföy, performans, kullanıcı metrikleri)
3. Multi-exchange adapter genişleme (Bybit, OKX)
4. Legacy endpoint cleanup
