# Release Rollback Plan

## Scope
Bu plan FAZ-7 release readiness için zorunlu rollback hazırlığını tanımlar.

## 1) Application Rollback
1. Aktif release sorunluysa stack'i durdur:
   - `docker compose down`
2. Önceki stabil image tag'lerine dön:
   - `docker compose pull`
3. Eski stabil image ile yeniden başlat:
   - `docker compose up -d`

## 2) Database Strategy
- **Varsayılan strateji:** forward-fix (önerilen)
- **Gerekirse controlled rollback:**
  - `alembic downgrade <target_revision>`
  - Sadece etki analizi sonrası uygulanır.

## 3) Post-Rollback Smoke
- `POST /api/auth/login/admin` → 200
- `GET /api/admin/live-trading/summary` → 200
- Frontend login akışı çalışır

## 4) Decision Rule
- App rollback possible: **YES**
- DB rollback possible: **CONDITIONAL** (impact review required)
- Eğer DB rollback riskliyse: **forward-fix uygulanır**
