# Readiness Ops Runbook (P2 Operasyonel Kapanış)

## 1) Admin giriş yolu (kanonik)
- **Doğru yol:** `/admin/login`
- User panelde admin login denemesi olursa UI otomatik olarak admin panele yönlendirir.

## 2) Readiness dashboard amacı
- `/admin/futures/live-readiness` ekranı, canlıya çıkış kararını katman bazında açıklar.
- Sadece status değil, blocker reason-code ve remediation (runbook key) gösterir.

## 3) History endpoint ne gösterir
- `GET /api/admin/futures/readiness/history`
- İçerik: `top_reason_codes`, `top_blockers`, `failure_trend`, `layer_failure_rate`, `last_n_summary`, `incident_correlation_id`
- Filtreler: `days`, `exchange`, `strategy`, `symbol`, `page`, `page_size`

## 4) Maintenance cron ne yapar
- Nightly maintenance:
  - readiness history retention
  - cleanup
  - aggregate summary refresh
  - daily summary üretimi
- K8s tanımı: `deploy/cron/readiness-maintenance-cron.yaml`

## 5) En sık blocker reason-code örnekleri
- `STRATEGY_ENGINE_HEARTBEAT_STALE`
- `EXECUTION_PROOF_ONLY_MOCKED`
- `FUNDING_DATA_STALE`
- `LIQUIDATION_INPUT_COVERAGE_LOW`
- `EXPOSURE_LIMIT_BREACH`

## 6) Venue config kontrol adımları
1. Credential mapping (live)
2. Environment-policy eşleşmesi
3. Authenticated probe
4. Market data availability
5. Order capability smoke path

## 7) Cron failure müdahale adımı
1. `/app/artifacts/readiness_maintenance_status.json` kontrol et
2. `reason_code` ve `retry_in_seconds` değerlerini al
3. `/app/artifacts/readiness_maintenance_cron.log` satırlarını incele
4. Gerekirse `POST /api/admin/futures/readiness/history/maintenance?dry_run=false` manuel tetikle

## 8) Fallback / UNKNOWN durumunda yapılacak
- UNKNOWN asla PASS değildir; canlıya çıkış bloke edilir.
- Önce reason-code üzerinden runbook eşlemesini uygula.
- Veri kaynağı veya credential mismatch varsa venue checklist’i düzelt.

## 9) Operasyonel smoke komutu
```bash
./scripts/run_readiness_smoke.sh local
./scripts/run_readiness_smoke.sh preview "$REACT_APP_BACKEND_URL"
./scripts/run_readiness_smoke.sh ops "$OPS_BASE_URL"
```

Rapor çıktısı: `/app/test_reports/readiness_ops_smoke_*.json`

## 10) Kapanış raporu üretimi
```bash
python backend/cli/readiness_closure_report.py \
  --base-url http://127.0.0.1:8001 \
  --email canary.admin@platform.local \
  --password 'CanaryAdmin123!' \
  --output /app/test_reports/readiness_closure_report_latest.json
```
