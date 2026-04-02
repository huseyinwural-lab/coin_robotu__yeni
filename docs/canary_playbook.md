# Canary Playbook (P1.3 Iteration 4)

## Amaç
Live modunda küçük notional ile canlıya geçiş öncesi execution/risk/reconciliation davranışını doğrulamak.

## Zorunlu Başlangıç Konfigürasyonu
1. `EXECUTION_MODE=live`
2. `LIVE_TRADING_ENABLED=true`
3. `LIVE_TRADING_ENABLED=false`
4. `LIVE_ROUTE_APPROVED=false`
5. `CANARY_MODE=true`
6. `CANARY_MAX_NOTIONAL=100`
7. `CANARY_ALLOWED_STRATEGIES=ema_rsi`
8. `CANARY_ALLOWED_USER_IDS` (opsiyonel, boş ise sadece operasyonel hesaplarla koştur)

## Exchange/Proxy Gereksinimi (Binance)
- Base URL, proxy endpoint olmalı (`BINANCE_SPOT_LIVE_BASE_URL` veya `BINANCE_SPOT_BASE_URL`).
- `X-Proxy-Token` header zorunlu (env üzerinden):
  - `BINANCE_SPOT_LIVE_PROXY_TOKEN` veya `BINANCE_SPOT_PROXY_TOKEN`
  - Opsiyonel genel fallback: `BINANCE_PROXY_TOKEN`
- Live key/secret tanımlı olmalı:
  - `BINANCE_LIVE_API_KEY`
  - `BINANCE_LIVE_API_SECRET`

## Canary Operasyon Akışı
1. **Guard doğrulama**
   - `GET /api/runtime/config`
   - `GET /api/runtime/safety/kill-switch`
2. **Küçük notional order akışı**
   - execution signal submit
   - timeline’da durum geçişi izle: `CREATED -> SENT -> FILLED/CANCELED`
3. **Reconciliation**
   - `POST /api/runtime/reconciliation/orders/run`
4. **PnL ve alert gözlemi**
   - `GET /api/runtime/pnl/summary`
   - `GET /api/runtime/alerts`
5. **Smoke koşusu**
   - `python /app/scripts/daily_smoke.py`

## İzleme Metrikleri
- `failed_orders_last_n`
- `queue_depth`
- `execution_ms`, `total_ms`
- `runtime_pnl_drop`
- canary violations (`CANARY_*` reason code)
- kill-switch state

## Otomatik/Kritik Durdurma Kriterleri
- `runtime_kill_switch_activated` alerti
- Son 20 order içinde 6+ fail
- Sürekli latency spike (eşik üstü p95)
- `CANARY_CAPITAL_LIMIT_EXCEEDED` veya `CANARY_MAX_POSITIONS_EXCEEDED`

## Rollback Prosedürü
1. `POST /api/runtime/safety/kill-switch/activate`
2. `EXECUTION_MODE=sim`
3. `POST /api/runtime/reconciliation/orders/run`
4. Açık incident için alert triage aksiyonu (`ack/mute/resolve/escalate`)
5. Timeline ve smoke çıktısıyla kapanış kanıtını kaydet

## Iteration 4 Kapanış Kontrol Listesi
- [ ] Binance live order lifecycle çalıştı (proxy + token ile)
- [ ] Kill-switch aktifken yeni execution BLOCK oldu
- [ ] Reconciliation akışı PASS
- [ ] Canary guard limitleri doğru uygulandı
- [ ] Timeline event akışı admin panelde doğrulandı
