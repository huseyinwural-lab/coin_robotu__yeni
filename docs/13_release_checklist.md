# Release Checklist

## Kurulum / Bootstrap
- [x] `backend/.env` içinde bootstrap admin değerleri doğrulandı.
- [x] İlk kurulumda `users` boşken bootstrap admin oluştu.
- [x] `users` doluyken bootstrap admin yeniden üretilmedi.

## Frontend Smoke
- [x] Landing page açılıyor.
- [x] Sayfa boş değil.
- [x] Kullanıcı Girişi görünüyor.
- [x] Admin Girişi görünüyor.
- [x] Kritik console error yok.

## Runtime/Gate
- [x] `bash scripts/ci_alembic_drift_gate.sh` PASS.
- [x] `bash scripts/ci_stage_gate.sh` PASS.
- [x] `bash scripts/ci_prod_gate.sh` PASS.

## Master Closure Ek Kontrolleri (2026-03-15)
- [x] Risk config governance safe-bounds reject (HTTP 400) doğrulandı.
- [x] `POST /api/admin/risk/config/rollback` çalışıyor.
- [x] `POST /api/admin/risk/execution-quality/calibrate` ve latest calibration endpoint çalışıyor.
- [x] `GET /api/venues/admin/adapter-smoke` çalışıyor (execution keysiz modda **MOCKED**).
- [x] `GET /api/admin/universe/runtime-summary` içinde `risk_overview` ve `observability_trends` doğrulandı.
