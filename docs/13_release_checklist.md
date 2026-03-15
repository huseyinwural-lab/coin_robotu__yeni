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
