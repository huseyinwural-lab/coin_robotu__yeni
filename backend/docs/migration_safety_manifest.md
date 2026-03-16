# Migration Safety Manifest

## 1) Active Head Revision
- **Current head**: `20260316_0046`
- **Policy**: PostgreSQL-first migration flow. SQLite fallback intentionally disabled.

## 2) batch_alter_table Inventory & Decision Table

| Migration File | Batch Block | Reason (Historical) | Decision | Applied Action |
|---|---|---|---|---|
| `20260311_0005_user_approval_flow.py` | users alter/drop columns | SQLite-compatible alter/drop pattern | REFACTOR | Direct `op.alter_column` + `op.drop_column` |
| `20260311_0007_execution_metrics_and_permission_drift.py` | user_exchange_settings alter/drop | Legacy compatibility style | REFACTOR | Direct `op.alter_column` + `op.drop_column` |
| `20260311_0008_release_gate_override_and_validation_snapshot.py` | user_exchange_settings alter/drop | Legacy compatibility style | REFACTOR | Direct `op.alter_column` + `op.drop_column` |
| `20260311_0009_execution_evidence_fields.py` | execution_metrics/user_exchange_settings alter/drop | Legacy compatibility style | REFACTOR | Direct `op.alter_column` + `op.drop_column` |
| `20260311_0012_execution_context_and_replay.py` | execution_metrics alter/drop | Legacy compatibility style | REFACTOR | Direct `op.alter_column` + `op.drop_column` |
| `20260315_0043_users_role_enum_alignment.py` | users role alter | Non-Postgres fallback branch | REFACTOR | Direct `op.alter_column` (non-batch); Postgres path unchanged |
| `20260315_0044_nullable_alignment.py` | nullable alignment alters | Generic compatibility template | REFACTOR | Direct `op.alter_column` |

### Current State
- Repo migration setinde **aktif `batch_alter_table` kullanımı yok**.
- Karar seti: PostgreSQL üretim hattında gereksiz table recreate davranışı kaldırıldı.

## 3) Baseline Scope Matrix

### 3.1 Critical Table Set

| Table | In Model | Migration Create Path | Usage Status | Class | Action |
|---|---:|---:|---|---|---|
| users | Yes | Yes (`20260316_0046` repair path) | Auth/Core | CRITICAL | keep + verify on clean install |
| bot_profiles | Yes | Yes (`20260316_0046`) | Trading core | CRITICAL | keep + verify |
| risk_policies | Yes | Yes (`20260316_0046`) | Risk core | CRITICAL | keep + verify |
| pending_signals | Yes | Yes (existing migration + `20260316_0046`) | Scanner->execution bridge | CRITICAL | keep + verify FK |
| admin_control | Yes | Yes (`20260316_0046`) | Control plane | CRITICAL | keep + verify |
| audit_logs | Yes | Yes (`20260316_0046`) | Observability/Audit | CRITICAL | keep + verify |
| signal_events | Yes | Yes (`20260316_0046`) | Signal traceability | CRITICAL | keep + verify |
| paper_positions | Yes | Yes (`20260316_0046`) | Position core | CRITICAL | keep + verify |

### 3.2 Open Table Set (Classified)

| Table | In Model | Migration Create Path | Usage Status | Class | Action |
|---|---:|---:|---|---|---|
| indicator_computation_cache | Yes | No | Indicator cache flow | OPTIONAL | feature migration planned / document |
| scanner_fallback_events | Yes | No | Scanner observability | OPTIONAL | feature migration planned / document |
| scanner_performance_snapshots | Yes | No | Scanner performance dashboards | OPTIONAL | feature migration planned / document |
| strategy_templates | Yes | No | Strategy template feature | OPTIONAL | feature migration planned / document |
| symbol_selection_watchlists | Yes | No | Symbol selector feature | OPTIONAL | feature migration planned / document |
| universe_rollout_state | Yes | No | Universe rollout monitoring | OPTIONAL | feature migration planned / document |
| user_learning_simulation_suggestions | Yes | No | Learning simulator | OPTIONAL | feature migration planned / document |
| user_onboarding_profiles | Yes | No | Onboarding feature | OPTIONAL | feature migration planned / document |
| user_scanner_symbol_selections | Yes | No | Scanner selection persistence | OPTIONAL | feature migration planned / document |
| execution_events | Yes | No | Exchange execution event stream | OPTIONAL | feature migration planned / document |
| external_provider_credentials | Yes | No | Provider credential store | OPTIONAL | feature migration planned / document |
| position_ledger_events | Yes | No | Position ledger analytics | OPTIONAL | feature migration planned / document |

### Legacy Set
- Bu fazda **LEGACY** olarak sınıflanan tablo yok.

## 4) PostgreSQL dışı migration desteği
- SQLite fallback **desteklenmiyor** (bilinçli karar).
- Migration safety akışı PostgreSQL odaklıdır.

## 5) Clean Install Expectation
- Temiz PostgreSQL volume üzerinde:
  1. `alembic upgrade head`
  2. `alembic_version == 20260316_0046`
  3. Critical tables present
  4. Critical FK checks pass (özellikle `pending_signals.risk_policy_id -> risk_policies.id`)
  5. Startup öncesi schema complete

## 6) Operational Command
- Tek komutlu doğrulama scripti: `backend/scripts/verify_clean_install.sh`
