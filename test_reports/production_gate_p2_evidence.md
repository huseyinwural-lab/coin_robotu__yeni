# Production Gate P2 Evidence Pack

- Generated at: 2026-03-23
- Base URL: `https://dry-run-shadow.preview.emergentagent.com`

## Mandatory P2 Artefacts
- `/test_reports/production_gate_p2_evidence.md`
- `/test_reports/production_gate_p2_timeline.json`
- `/test_reports/production_gate_p2_analytics.json`
- `/test_reports/production_gate_p2_compare.json`
- `/test_reports/production_gate_p2_smoke.jpeg`
- `/test_reports/iteration_114.json`

Manifest bağlantısı: `/backend/exports/artifact_manifest.json`

## Backend Validation
- Pytest raw output: `/test_reports/production_gate_p2_backend_pytest.txt`
- Sonuç: `3 passed`, `0 failed` (history/flapping + analytics/timeline/risk + export v2)

## Independent Test Agent Validation
- Rapor: `/test_reports/iteration_114.json`
- Sonuç: backend `%100`, frontend `%100`
- Doğrulanan ana başlıklar: history filters, compare deltas, override analytics, timeline categories, risk badge, Export V2 alanları.

## Kanıtlanan P2 Modülleri
1. **Check History & Trend Engine**
   - Endpoint: `GET /api/phase4/admin/production-gate/checks/history`
   - `check_key/status/date` filtreleri aktif.
   - Flapping flag üretimi (`FLAPPING`) doğrulandı.

2. **Override Analytics Panel**
   - Endpoint: `GET /api/phase4/admin/production-gate/override-analytics`
   - `override_count`, `override_rate`, `reason_distribution`, `top_override_checks`, `expiry_vs_revoke_ratio` dolu.

3. **Before/After Compare**
   - Endpoint: `GET /api/phase4/admin/production-gate/checks/compare`
   - `previous_result`, `new_result`, `latency_delta_ms`, `state_delta` alanları dolu.

4. **Incident Timeline**
   - Endpoint: `GET /api/phase4/admin/production-gate/timeline`
   - Kategoriler: checks / overrides / mode / deploy
   - UI filtreleri aktif.

5. **Risk Scoring**
   - `risk_score (0-100)` ve `risk_level (LOW/MEDIUM/HIGH)` gate header’da görünür.
   - Flapping/fail/stale/override etkisi skora yansır.

6. **Export V2**
   - Endpoint: `GET /api/phase4/admin/production-gate/export/raw`
   - Export payload içinde:
     - check history snapshot
     - override analytics summary
     - timeline snapshot
     - risk score/risk level

## Smoke Evidence
- Dosya: `/test_reports/production_gate_p2_smoke.jpeg`
- İçerik:
  - Snapshot A: risk badge + fail banners + gate state
  - Snapshot B: check history/trend + override analytics + incident timeline
