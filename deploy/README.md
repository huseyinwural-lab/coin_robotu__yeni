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

## Health/Readiness

- `/api/health`: process + db + startup state
- `/api/ready`: db/redis/queue readiness kontrolü
