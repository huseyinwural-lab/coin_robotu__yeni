# Release Readiness Final Checklist (P0 Closure Gate)

Bu doküman üretim kapanışı öncesi tek sayfa kontrol listesidir.

## 1) Migration / DB Gate

- [ ] Prod env’de `ALEMBIC_ALLOW_SQLITE_FALLBACK=0`
- [ ] `alembic heads` çıktısı alındı
- [ ] `alembic_version` mevcut head ile eşleşiyor
- [ ] Kritik tablolar mevcut:
  - `users`
  - `bot_profiles`
  - `risk_policies`
  - `pending_signals`
  - `admin_control`
  - `audit_logs`
  - `signal_events`
  - `paper_positions`

## 2) Contract/API Smoke

- [ ] `/api/v1/user/trading/preview` leverage alanları dönüyor
  - `requested_leverage`
  - `recommended_leverage`
  - `applied_leverage`
- [ ] `/api/user/exchange-connections` health/jitter alanları dönüyor
- [ ] `/api/user/exchange-connections/{id}/revalidate` çalışıyor
- [ ] Bot soft-delete sonrası listede görünmüyor
- [ ] `/api/audit-logs/admin/incident-export?window_days=7` ZIP indirilebiliyor

## 3) UI Smoke

- [ ] Overview > System Health Dashboard kartları dolu
- [ ] Exchange Settings > reason/action/timeline görünür
- [ ] Execute Preview > leverage policy satırları görünür
- [ ] Scanner degrade fallback banner çalışır
- [ ] Audit Logs > incident window (1/7/30/90) + ZIP download çalışır

## 4) P1 Faz-2 Ops Doğrulama

- [ ] `/api/admin/users/futures-live-path-check` summary PASS
- [ ] `/api/admin/system-alerts/burn-in` metrikleri okunuyor
- [ ] `/api/admin/system-alerts/test-delivery` (email/slack/both) test edildi

## Otomatik Komutlar

### A) Hızlı smoke

```bash
python /app/backend/cli/final_release_smoke_suite.py
```

Beklenen: JSON içinde `"overall": "PASS"`

### B) P0 Closure Gate (önerilen)

```bash
python /app/backend/cli/p0_closure_gate.py --target-env preview
```

Prod için:

```bash
python /app/backend/cli/p0_closure_gate.py --target-env prod
```

Beklenen: JSON içinde `"overall": "PASS"`

## Risk Notu

- Bybit/OKX execution adapterları bu sürümde **MOCKED** (kullanıcı kararı).
