# Runtime Hardening Config (Versioned)

Bu klasör, control plane runtime sertleştirme kanıt dosyalarını içerir.

## Dosyalar

- `supervisor_control_plane.conf`
  - PostgreSQL process config
  - Backend process config
  - restart/retry policy (`startretries=10`)
  - `start_backend_with_db_guard.sh` çağrısı

- `../scripts/start_backend_with_db_guard.sh`
  - `wait_for_postgres_ready.py` preflight
  - DB hazır değilse backend health/readiness tarafında degraded sinyal verir

- `cron/readiness-maintenance-cron.yaml`
  - Nightly readiness maintenance schedule (02:15 UTC)
  - `daily_ops_automation.py` çalıştırır
  - retention + cleanup + aggregate summary refresh akışını tetikler

## Health/Readiness

- `/api/health`: process + db + startup state
- `/api/ready`: db/redis/queue readiness kontrolü

## Readiness Maintenance Runtime Artefaktları

- `/app/artifacts/readiness_maintenance_cron.log`
  - Job log formatı (OK/FAIL + reason_code/retry)
- `/app/artifacts/readiness_maintenance_status.json`
  - Son başarılı run timestamp
  - Son hata reason_code + retry bilgisi
