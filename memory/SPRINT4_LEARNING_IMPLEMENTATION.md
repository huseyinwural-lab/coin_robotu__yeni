# Sprint-4 Hafıza Katmanı — Uygulanan Mimari

## Kapsam
- Learning event persistence
- Strategy/family outcome memory
- Guardrailed recommendation engine (auto-mutate yok)
- Admin learning panel + apply (manual onay)
- User safe surface (confidence adjustment + badges)

## Uygulanan Tablolar
- `learning_decision_events`
- `strategy_outcome_memory`
- `family_outcome_memory`
- `learning_recommendations`

## Learning Guardrails
- Learning engine production kuralını otomatik değiştirmez.
- Sadece öneri üretir (`disable`, `auto_throttle`, `weight_boost`).
- Uygulama yalnız admin endpointi ile (`/api/admin/learning/recommendations/{id}/apply`).

## API
- `POST /api/admin/learning/refresh`
- `GET /api/admin/learning/overview`
- `POST /api/admin/learning/recommendations/{id}/apply`
- `GET /api/user/learning/safe-surface`

## User Safe Surface
- `confidence_adjustment`
- `learning_badges`
  - `recent quality degraded`
  - `strategy currently throttled`
  - `decision supported by high-quality recent signals`

## Not
- Bu sürümde learning hesaplaması deterministic ve batch refresh tabanlıdır.
- Daha ileri iterasyonda drift alert + regime-aware decay fonksiyonu genişletilebilir.
