# Canary Playbook

## Amaç
SIM/testnet sonrası canlı geçişten önce düşük notional ve dar kapsamla runtime davranışını doğrulamak.

## Açılış Koşulları
1. `EXECUTION_MODE=testnet`
2. `TESTNET_TRADING_ENABLED=true`
3. `LIVE_TRADING_ENABLED=false`
4. `CANARY_MODE=true`
5. `CANARY_MAX_NOTIONAL=100`
6. `CANARY_ALLOWED_STRATEGIES=ema_rsi`
7. `CANARY_ALLOWED_USER_IDS` (opsiyonel; boşsa admin-only)

## İzlenecek Metrikler
- `failed_orders_last_n`
- `queue_depth`
- `execution total_ms`
- `runtime_pnl_drop`
- kill-switch state

## Ne Zaman Kapatılır?
- `runtime_kill_switch_activated` alerti gelirse
- fail rate spike (20 içinde 6+) oluşursa
- latency spike sürekli ise

## Rollback Prosedürü
1. `POST /api/runtime/safety/kill-switch/activate`
2. `EXECUTION_MODE=sim`
3. Worker backlog ve açık orderları reconcile et
4. `POST /api/runtime/reconciliation/orders/run`
5. Alert triage ile incident’i `resolved`/`escalated` olarak kapat

## Manuel Sağlık Komutları
- Smoke: `python /app/scripts/daily_smoke.py`
- Reconciliation: `POST /api/runtime/reconciliation/orders/run`
- Timeline: `GET /api/runtime/timeline/events`

## Önerilen Cron
- Reconciliation (5 dk): `*/5 * * * * /root/.venv/bin/python /app/scripts/order_reconciliation_cron.py`
