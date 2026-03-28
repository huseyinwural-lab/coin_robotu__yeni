# Trading Lifecycle Unified Event Schema (v1.0.0)

## Zorunlu Alanlar

- `event_id`
- `event_type`
- `timestamp`
- `correlation_id`
- `parent_event_id`
- `strategy_id`
- `symbol`
- `user_id`
- `environment`
- `payload`
- `latency`
- `decision_reason`
- `risk_flags`
- `execution_result`

Tüm alanlar event envelope içinde key olarak bulunur. Doldurulamayan alanlar `null` / empty standartla işaretlenir, key kaybolmaz.

## Event Taxonomy

Lifecycle stage prefix:

- `request.*`
- `intent.*`
- `decision.*`
- `risk.*`
- `order.*`
- `execution.*`
- `fill.*`

## Correlation Kuralları

- Her event correlation zincirine (`correlation_id`) bağlanmalı.
- Parent-child ilişkisi `parent_event_id` ile taşınır.
- Parent bulunamıyorsa event `orphan` olarak işaretlenir.
- Kritik stage eksikse chain `trace_incomplete=true` olur.

## Severity Standardı

- `INFO` → observe
- `WARNING` → filterable
- `ERROR` → incident_candidate
- `CRITICAL` → alert_escalate

## Replay Kuralları

- Deterministic ordering zorunludur.
- Replay izolasyon modunda çalışır (`side_effects_blocked=true`).
- Aynı input + aynı ordering aynı break step’i üretmelidir.
