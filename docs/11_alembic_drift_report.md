# Alembic Drift Report (FAZ-2B / Görev-1)

## Çalıştırılan kaynak
- Komut: `PYTHONPATH=/app/backend alembic check`
- Kaynak çıktı: `/tmp/alembic_check_current.log`

## Drift envanteri (ham tespit)

1. `NOT NULL` farkı: `bot_profiles.is_running`
2. Ek indeks: `ix_execution_intents_account_id` (`execution_intents.account_id`)
3. Ek FK: `pending_signals.bot_profile_id -> bot_profiles.id`
4. Ek FK: `pending_signals.exchange_connection_id -> user_exchange_connections.id`
5. Ek FK: `pending_signals.created_order_intent_id -> user_execution_intents.id`
6. Ek FK: `pending_signals.risk_policy_id -> risk_policies.id`
7. `NOT NULL` farkı: `strategy_observability_events.created_at`
8. Ek indeks: `ix_user_execution_intents_intent_type` (`user_execution_intents.intent_type`)
9. Type farkı: `users.role` (`VARCHAR(5)` -> `Enum(UserRole)`)
10. `NOT NULL` farkı: `users.updated_at`

## Sınıflandırma

### A) Non-destructive gerçek drift
- İndeks farkları:
  - `ix_execution_intents_account_id`
  - `ix_user_execution_intents_intent_type`
- FK farkları:
  - `pending_signals.bot_profile_id`
  - `pending_signals.exchange_connection_id`
  - `pending_signals.created_order_intent_id`
  - `pending_signals.risk_policy_id`

### B) Destructive/ertelenecek gerçek drift
- Nullable tightening:
  - `bot_profiles.is_running`
  - `strategy_observability_events.created_at`
  - `users.updated_at`
- Type change:
  - `users.role` (`VARCHAR` -> `Enum`)

### C) False-positive analizi
- `backend/models.py` + `backend/model_domains/**` import zinciri kontrol edildi.
- Mapper/table çoğaltması bulunmadı (`dups={}`), tek metadata registry kullanılıyor.
- Sonuç: Bu iterasyondaki drift kalemleri import/aggregate kaynaklı false-positive değil.

## Etkilenen model dosyaları
- `backend/model_domains/strategy_decision.py` (`BotProfile.is_running`, `StrategyObservabilityEvent.created_at`)
- `backend/model_domains/risk_execution_positions.py` (`UserExecutionIntent.intent_type`, `ExecutionIntent.account_id`)
- `backend/model_domains/audit_reporting_system_config.py` (`PendingSignal` FK alanları)
- `backend/model_domains/auth_users.py` (`User.role`, `User.updated_at`)

## Etkilenen migration kökleri
- `20260311_0018_risk_orchestrator_core.py` (index koşullu/eksik)
- `20260312_0029_execution_position_actions.py` (intent_type index eksik)
- `20260313_0034_pending_signal_execution_trace.py` (FK constraint eksik)

## Ek teknik not
- Bu iterasyonda mevcut migration dosyaları değiştirilmedi; yalnız drift envanteri ve non-destructive kapanış uygulanmıştır.

## FAZ-2C uygulama sonucu
- Uygulanan migration dosyaları:
  - `20260315_0042_destructive_backfill_prepare.py`
  - `20260315_0043_users_role_enum_alignment.py`
  - `20260315_0044_nullable_alignment.py`
- `alembic check` sonucu: **No new upgrade operations detected.**
- `bash /app/scripts/ci_alembic_drift_gate.sh` sonucu: **PASS (strict mode)**
