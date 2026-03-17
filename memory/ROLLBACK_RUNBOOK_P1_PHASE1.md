# Rollback Runbook — P1 Faz-1 Reliability Tuning

Version: `runbook_p1_phase1_v1`  
Policy bağlı sürüm: `connection_reliability_policy_v1`

## Tetik Koşulları (Rollback Başlat)

1. Health flap oranı 30 dk pencerede baseline üstüne %25+ çıkarsa
2. `exchange_validation_failure` hacmi tuning sonrası anlamlı artarsa
3. Reconnect döngüsü nedeniyle kullanıcı işlemleri bloke olursa

## Hızlı Rollback Adımları

1. Config dosyasını önceki güvenli sürüme al:
   - `/app/config/connection_reliability_policy.json`
2. `profiles.production` içinde aşağıdaki alanları önceki değerlerine döndür:
   - `retry.*`
   - `health.liveness_interval_seconds.*`
   - `health.signed_interval_seconds.*`
   - `health.transient_failures_before_reconnect`
   - `http_timeouts.*`
3. Config doğrulama:
   - Backend startup’ın policy validation’dan geçtiğini logdan doğrula
4. Servis yenileme (gerekirse):
   - `sudo supervisorctl restart backend`

## Parametre Bazlı Geri Alma Prosedürü

- Timeout kaynaklı regresyon:
  - `http_timeouts.signed_get/signed_post` değerlerini önceki baseline’a çek
- Retry gecikmesi fazla olduysa:
  - `retry.max_backoff_seconds` düşür
  - `retry.max_retry_attempts` düşür
- Hızlı flap geri döndüyse:
  - `health.transient_failures_before_reconnect` artır
  - `health.signed_interval_jitter_seconds` stabil değerde tut (1-2)

## Post-Rollback Doğrulama Checklist

1. `GET /api/health` -> 200
2. `GET /api/user/exchange-connections` -> health alanları dönüyor
3. `POST /api/user/exchange-connections/{id}/revalidate` -> 200/4xx (500 olmamalı)
4. Audit timeline’da zincir tutarlılığı:
   - duplicate `exchange_health_transition` spam yok
   - `exchange_validation_failure/success` eventleri anlamlı

## Notlar

- Bybit/OKX adapterları bu fazda **MOCKED** kalır.
- Rollback sonrası 30 dk gözlem penceresi zorunlu.
