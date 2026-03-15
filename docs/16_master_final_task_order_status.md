# TRADING ENGINE — MASTER FINAL TASK ORDER STATUS

Tarih: 2026-03-15

## FINAL-1 Exchange Execution Activation
- Admin Exchange Settings credential alanları backend+frontend eklendi:
  - bybit_api_key
  - bybit_secret
  - okx_api_key
  - okx_secret
  - okx_passphrase
- Endpointler:
  - `GET /api/venues/admin/execution-credentials`
  - `PATCH /api/venues/admin/execution-credentials`
  - `POST /api/venues/admin/execution-validation`
- Validation kapsamı:
  - adapter smoke
  - precision validation
  - lot size validation
  - order submit test
  - cancel test
  - retry behavior
- Not: kullanıcı tercihi gereği credential yok; execution submit/cancel **MOCKED**.

## FINAL-2 Live Deployment Rollout (Operasyon)
- Kod içi otomasyon yardımcıları eklendi:
  - `scripts/live_rollout_metrics_snapshot.sh`
- Fazlar (DEPLOY-3..7) runbook ile yürütülecek (zaman bazlı operasyon).

## FINAL-3 Execution Quality Final Calibration
- Kalibrasyon endpointleri aktif:
  - `POST /api/admin/risk/execution-quality/calibrate`
  - `GET /api/admin/risk/execution-quality/calibration`
- Veri azlığında `policy_documented_warning` standardı aktif.

## FINAL-4 Regime / Risk Tuning
- normal/volatile/stress cap profilleri aktif.
- volatility/spread/latency/execution_quality_trend girdileri ile rejim seçimi aktif.

## FINAL-5 Risk Governance Maturity
- Safe bounds reject + config_version + rollback aktif.
- Timeline + profiles + overrides endpointleri aktif:
  - `GET /api/admin/risk/config/timeline`
  - `GET /api/admin/risk/config/profiles`
  - `POST /api/admin/risk/config/profiles/{profile}/apply`
  - `GET/PATCH /api/admin/risk/config/overrides`
- Tenant policy desteği config override katmanında hazır (opsiyonel rollout).

## FINAL-6 Admin Observability Hardening
- Runtime summary içinde risk_overview + observability trend alanları aktif.
- Admin Universe Monitor sayfasına metrik/trend/pnl görünürlüğü eklendi.

## FINAL-7 Admin UI Düzenleme
- Primary action butonları açık yeşil standarda çekildi (`#4CAF50`).
- Sol menü sıralaması sadeleştirildi, logout en alta taşındı ve sticky yapıldı.
- Sidebar scroll davranışı iyileştirildi.

## FINAL-8 CI / Docker Doğrulama
- Stage/prod gate PASS.
- Docker helper script eklendi: `scripts/docker_validation_check.sh`
- Bu podda docker yoksa script `runner_required` çıktısı verir.

## FINAL-9 Exchange Normalization Hardening
- symbol mapper + precision normalizer + leverage rule + error taxonomy + retry policy eklendi.
- funding rate fetch altyapısı eklendi (Bybit/OKX public endpoint).

## FINAL-10 Advanced Improvements
- Smart routing / otomatik rejim-risk profili / explainability 2.0 / canary otomasyonu backlog’a yazıldı.
