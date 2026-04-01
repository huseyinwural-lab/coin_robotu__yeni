# Production Gate P2 Hardening Evidence

- generated_at: 2026-03-24T00:35:31.396603+00:00
- generation: automated
- source: runtime test execution

## Cross-check
- endpoint: /api/phase4/admin/production-gate/system/cross-check
- is_consistent: True
- counts: {"history_count": 179, "history_linked_count": 179, "audit_check_event_count": 179, "audit_run_id_count": 67, "override_rows_count": 2, "analytics_override_count": 2}

## Artefact gerçeklik kontrolü
- run_id UUID valid: 16/16
- audit_id/request_id UUID item sayısı: 216

## Flapping doğrulaması
- non-low flapping row sayısı: 56
- örnek severity: HIGH
- örnek count: 21

## Compare doğrulaması
- run_count>=3 item sayısı: 6
- improvement=true item sayısı: 1

## Timeline-Audit eşleşmesi
- timeline item sayısı: 216
- audit/request UUID item sayısı: 216

## Üretilen dosyalar
- /app/test_reports/production_gate_p2_risk_engine.json
- /app/test_reports/production_gate_p2_flapping.json
- /app/test_reports/production_gate_p2_timeline_audit_match.json
- /app/test_reports/production_gate_p2_compare_multi_run.json
- /app/test_reports/iteration_115.json
