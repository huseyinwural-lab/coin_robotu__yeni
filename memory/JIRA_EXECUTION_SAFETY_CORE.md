# EPIC: EXECUTION SAFETY CORE (Futures)

## Epic Goal
Futures execution hattında sistem hazır değilse **asla READY/ALLOW** dönmemesi; signal → order → ack/fill → reconcile → audit zincirinin izlenebilir, durdurulabilir, tekrar işlenebilir ve immutable kanıt üreten yapıya dönüşmesi.

---

## STORY-1: Merkezi Execution Safety Gate
**Kapsam**
- `/api/execution-safety/gate`
- Standard response: `state, score, blockers[], warnings[], evaluated_at, correlation_id`
- Hard blocker override ve fail-safe deny

**Acceptance Criteria**
1. Hard blocker varsa state daima `BLOCKED`.
2. Score yüksek olsa bile blocker override edilir.
3. Kritik veri eksikse sistem `BLOCKED` döner.
4. Response standard alanları eksiksiz döner.

---

## STORY-2: Unified Environment Policy (testnet/staging/live)
**Kapsam**
- `/api/execution-safety/recovery/policy`
- `/api/execution-safety/recovery/policy/{environment}`
- Policy alanları: `enable_flag, validation_status, last_verified_at, verification_evidence, path_open`

**Acceptance Criteria**
1. Live path açılmadan testnet validation zorunlu.
2. Testnet disabled + live unvalidated kombinasyonu `BLOCKED` üretir.
3. Path açık/kapalı kararı tek merkez policy’den gelir.

---

## STORY-3: Canonical Intent Lifecycle State Machine
**Kapsam**
- `/api/execution-safety/intents`
- Canonical state set:
  `CREATED, SUBMITTED, ACKED, PARTIALLY_FILLED, FILLED, FAILED, CANCELED, RECONCILING, RECONCILED`
- Invalid transition reject/violation log

**Acceptance Criteria**
1. Intent sadece tanımlı transition matrisi üzerinden ilerler.
2. `PARTIALLY_FILLED`, `RECONCILING`, `RECONCILED` ayrı state olarak görünür.
3. `CANCELED` tek standarttır (CANCELLED normalize edilir).

---

## STORY-4: Stuck Intent Detection + Recovery
**Kapsam**
- Timeout state’leri: `CREATED, SUBMITTED, ACKED, PARTIALLY_FILLED, RECONCILING`
- Recovery aksiyonları:
  - tekil: `/api/execution-safety/recovery/{intent_id}/{action}` (`retry|cancel|reconcile|quarantine`)
  - batch: `/api/execution-safety/recovery/batch`

**Acceptance Criteria**
1. Stuck intent tespit edilir (`is_stuck=true`).
2. En az bir recovery aksiyonu çalışır ve audit izi bırakır.
3. Sonsuz retry engellenir (retry policy + quarantine).

---

## STORY-5: Runtime Quarantine / DLQ Productionization
**Kapsam**
- `/api/execution-safety/quarantine`
- `/api/execution-safety/quarantine/{quarantine_id}/{action}`
- Action set: `replay, reprocess, manual_resolve, mark_failed`

**Acceptance Criteria**
1. Retry exhaustion sonrası event quarantine’a düşer.
2. Quarantine event replay/reprocess ile tekrar işlenebilir.
3. Poison message sonsuz döngüye girmez.
4. Quarantine kaydı zorunlu alanları taşır:
   `quarantine_id, correlation_id, intent_id, reason, failure_stage, retry_count, first_seen_at, last_seen_at, payload_snapshot, error_snapshot, status`

---

## STORY-6: Immutable Proof Artefact Pipeline
**Kapsam**
- `/api/execution-safety/artifacts?intent_id=...`
- `/api/execution-safety/artifacts/incident-export`
- Artefact bileşenleri:
  `signal_snapshot, decision_snapshot, risk_snapshot, order_request, order_response, exchange_ack_or_fill_evidence, reconcile_result, failure_trace, retry_trace`

**Acceptance Criteria**
1. Artefact immutable olarak kaydedilir (signed manifest zinciri).
2. Intent’e bağlı kanıt bileşenleri tek pakette toplanır.
3. Artefact üretim/kalite eksikse gate fail-safe blocker üretebilir.

---

## STORY-7: Correlation Spine Zorunluluğu
**Kapsam**
- Gate ve intent zincirinde zorunlu kimlik takibi:
  `request_id, intent_id, order_id, execution_id, session_id, correlation_id`

**Acceptance Criteria**
1. Tek intent için log/DB/artifact/quarantine zinciri ilişkilendirilebilir.
2. Kritik correlation alanları eksikse fail-safe block uygulanır.

---

## STORY-8: Fail-Safe Default Deny Enforcement
**Kapsam**
- Gate değerlendirmesinde fail-open davranışların temizlenmesi

**Acceptance Criteria**
1. Kritik bilgi yoksa sonuç `BLOCKED`.
2. “Belirsiz ama devam et” davranışı yoktur.
3. Fail-open örnekleri testlerle yakalanır.

---

## STORY-9: Observability & Auditability
**Kapsam**
- `/api/execution-safety/observability`
- Görünürlük:
  `current gate state, blockers, active stuck intents, quarantined events, replay history, son execution denemeleri, intent timeline, artifact manifest`

**Acceptance Criteria**
1. Tek intent yaşam döngüsü operasyonda okunabilir.
2. Stuck/failed/quarantined olaylar görünür ve aksiyonlanabilir.

---

## STORY-10: Testnet Acceptance Flow (En Son)
**Kapsam**
- Gerçek testnet zinciri doğrulaması (submit → ack/fill → reconcile → artefact)

**Acceptance Criteria**
1. En az 1 gerçek testnet order zinciri uçtan uca tamamlanır.
2. Zincir API/audit/artefact üzerinden doğrulanabilir.
