# Alembic Drift Resolution Plan (FAZ-2B / Görev-3)

## Hedef
Alembic drift gate çıktısını ikiye ayırmak:
- Non-destructive drift: bu iterasyonda kapatılacak
- Destructive drift: planlanacak, sonraki onaylı faza bırakılacak

## Gerçek drift / false-positive ayrımı
- Import/metadata false-positive tespiti yapılmadı.
- Mevcut farklar gerçek schema farkı olarak değerlendirildi.

## Uygulanacak (non-destructive)

### Migration grubu: `execution + pending_signal schema hardening`
Tek migration altında aşağıdaki adımlar uygulanır:

1. `execution_intents.account_id` için eksik index oluşturma
   - `ix_execution_intents_account_id`

2. `user_execution_intents.intent_type` için eksik index oluşturma
   - `ix_user_execution_intents_intent_type`

3. `pending_signals` tablosunda eksik FK constraint’leri oluşturma
   - `bot_profile_id -> bot_profiles.id`
   - `exchange_connection_id -> user_exchange_connections.id`
   - `created_order_intent_id -> user_execution_intents.id`
   - `risk_policy_id -> risk_policies.id`

## Ertelenecek (destructive)

1. Nullable tightening
   - `bot_profiles.is_running` nullable `True -> False`
   - `strategy_observability_events.created_at` nullable `True -> False`
   - `users.updated_at` nullable `True -> False`

2. Type migration
   - `users.role`: `VARCHAR(5)` -> `Enum(UserRole)`

Bu kalemler veri güvenliği etkisi nedeniyle bu iterasyonda uygulanmaz.

## Drift Gate davranışı
- Gate, non-destructive drift kalemleri kapanmadan FAIL verir.
- Non-destructive kalemler kapanınca;
  - yalnız yukarıdaki deferred-destructive kalemler kalırsa PASS (planlı defer)
  - beklenmeyen yeni drift varsa FAIL

## Uygulama sonrası doğrulama listesi
1. `bash /app/scripts/ci_alembic_drift_gate.sh`
2. `GET /api/health`
3. `POST /api/auth/login/admin`
4. `GET /api/admin/universe-monitor`
5. `GET /api/user/scanner/symbol-selection`
