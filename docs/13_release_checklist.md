# Release Checklist

## Kurulum / Bootstrap
- [ ] `backend/.env` içinde bootstrap admin değerleri doğrulandı.
- [ ] İlk kurulumda `users` boşken bootstrap admin oluştu.
- [ ] `users` doluyken bootstrap admin yeniden üretilmedi.

## Frontend Smoke
- [ ] Landing page açılıyor.
- [ ] Sayfa boş değil.
- [ ] Kullanıcı Girişi görünüyor.
- [ ] Admin Girişi görünüyor.
- [ ] Kritik console error yok.

## Runtime/Gate
- [ ] `bash scripts/ci_alembic_drift_gate.sh` PASS.
- [ ] `bash scripts/ci_stage_gate.sh` PASS.
- [ ] `bash scripts/ci_prod_gate.sh` PASS.
