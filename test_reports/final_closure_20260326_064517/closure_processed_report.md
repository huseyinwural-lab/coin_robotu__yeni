# Alternatif Kapanış Raporu

- Kaynak klasör: `/app/test_reports/final_closure_20260326_064517`
- Final durum: **FAIL**
- PASS: 1 | FAIL: 8

## FAIL Olan Koşullar
- `infra_patch_applied` → 3:B seçimi nedeniyle canlı apply bu oturumda yapılmadı
- `production_url_used` → kullanılan URL preview, production/public URL değil
- `login_10x_200` → /api/auth/login çağrıları 404 döndü
- `websocket_stable` → websocket soak doğrulaması tamamlanamadı
- `smoke_pass` → smoke overall_status FAIL
- `readiness_ready` → readiness NOT_READY
- `dry_run_pass` → dry-run FAIL
- `go_live_true` → checklist go_live=false

## Kanıt Dosyaları
- `devops_apply_commands`: `/app/test_reports/final_closure_20260326_064517/devops_apply_commands.sh`
- `daily_smoke_latest`: `/app/test_reports/final_closure_20260326_064517/daily_smoke_latest.json`
- `final_go_no_go_artifact`: `/app/test_reports/final_closure_20260326_064517/final_go_no_go_artifact.json`
- `rollback_state`: `/app/test_reports/final_closure_20260326_064517/rollback_state.json`
- `kill_switch_verify`: `/app/test_reports/final_closure_20260326_064517/kill_switch_verify.json`