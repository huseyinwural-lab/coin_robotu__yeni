# Production Gate P1 — Evidence Closure

- Generated: 2026-03-23
- Base URL: `https://identity-control-1.preview.emergentagent.com`
- Manifest: `/backend/exports/artifact_manifest.json`

## Mandatory Artefacts (Present)
- `/test_reports/production_gate_p1_evidence.md`
- `/test_reports/production_gate_p1_endpoint_state_evidence.json`
- `/test_reports/production_gate_p1_smoke_after_login.jpeg`
- `/test_reports/production_gate_p1_backend_pytest.txt`
- `/test_reports/iteration_113.json`

## Smoke Evidence
- File: `/test_reports/production_gate_p1_smoke_after_login.jpeg`
- İçerik: tek birleşik görselde iki state snapshot var:
  1. **NO_GO + HARD BLOCK + ACTIVE FAIL banner**
  2. **GO_WITH_OVERRIDE + override aktif görünüm + ACTIVE FAIL banner**

## Endpoint / State Evidence
- File: `/test_reports/production_gate_p1_endpoint_state_evidence.json`
- Her senaryoda mevcut: `request`, `response`, `state_before`, `state_after`
- Kanıtlanan zorunlu akışlar:
  - `checklist_incomplete_go_block` (GO blok)
  - `validation_400_invalid_confirmation` (400)
  - `hard_block_403_no_go_live` (403)
  - `override_create_transition` (NO_GO -> GO_WITH_OVERRIDE)
  - `override_expiry_to_no_go` (expiry sonrası NO_GO)
  - `override_revoke_transition` + `post_revoke_instant_block`

## Backend Raw Test Output
- File: `/test_reports/production_gate_p1_backend_pytest.txt`
- Ham çıktı içerir: test isimleri, toplam test sayısı, PASS dağılımı
- Sonuç: `28 passed`, `fail=0`

## Independent Iteration Report
- File: `/test_reports/iteration_113.json`
- Backend + Frontend test kapsamı ve pass/fail detaylarını içerir.

## Commit/Trace Chain
- Tüm artefact referansları `artifact_manifest.json` içinde path/type/description/commit_hash/timestamp alanları ile zincirlenmiştir.
