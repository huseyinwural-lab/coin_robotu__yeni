# PROD Deployment Checklist + Rollback Plan

## Amaç
Canlıya çıkmadan önce sistemin operasyonel güvenilirlik, izlenebilirlik ve geri dönüş güvenliğini garanti etmek.

## A) Pre-Deploy Checklist (Go/No-Go)

### 1) Quote Policy Lock (Zorunlu)
- [ ] `/app/config/trading.json` içinde `allowed_quote_assets` yalnızca `USDT`, `USDC`
- [ ] `/api/runtime/quote-policy` çıktısı config ile birebir aynı
- [ ] Invalid quote denemesi `INVALID_QUOTE_ASSET` ile bloklanıyor
- [ ] `state_snapshot.symbol` ve `allowed_quote_assets` response içinde mevcut

### 2) Override Güvenliği
- [ ] Invalid quote override ile bypass edilemiyor
- [ ] Override create/cancel sonrası aktif override state anlık değişiyor
- [ ] Audit log’da override action + trace_id kaydı var

### 3) Gate Gerçekliği
- [ ] `/api/runtime/gate/recheck` gerçek CI script sonuçlarını (`scripts`) döndürüyor
- [ ] Gate decision + reason codes UI’da görülebiliyor

### 4) WS Sağlığı
- [ ] Reconnect sonrası session id değişimi doğrulanıyor
- [ ] State Validation Checklist WS satırı PASS üretiyor

### 5) Guard Telemetry
- [ ] Blocked trades listesinde `symbol`, `reason`, `updated_at` dolu
- [ ] `INVALID_QUOTE_ASSET` reason breakdown’da görünür
- [ ] UI’da badge/highlight/pinned görünür

### 6) Action → Result Zinciri
- [ ] Tüm kritik aksiyonlarda toast: success/fail + trace_id
- [ ] Panel result alanında `last_action_result` güncelleniyor
- [ ] Backend action response contract: `{ status, trace_id, message, state_snapshot }`

### 7) Audit Tamlığı
- [ ] Kritik aksiyonların hepsi audit log’a düşüyor
- [ ] trace_id ile aksiyon sonucu korelasyon kurulabiliyor

## B) Deploy Adımları (Önerilen Sıra)
1. DB migration/health kontrolü
2. Backend deploy + health check
3. Frontend deploy
4. Smoke tests:
   - login
   - quote policy endpoint
   - ws reconnect
   - gate recheck
   - guard telemetry
5. Operatör onayı (Go/No-Go)

## C) Rollback Tetikleyicileri
- Critical endpoint 5xx artışı
- Invalid quote trade açılabilmesi
- Guard telemetry boş/bozuk veri
- Gate/WS state doğrulama başarısızlığı

## D) Rollback Planı

### Hızlı Rollback (Öncelikli)
1. Son stabil backend artefact/version’a dön
2. Son stabil frontend artefact/version’a dön
3. Runtime kontrol endpointlerini smoke test et
4. Operatör dashboard check:
   - quote policy görünürlüğü
   - guard telemetry reason breakdown
   - ws reconnect kontrolü

### Veri Güvenliği
- Migration geri dönüş gerektiriyorsa yalnız doğrulanmış down migration uygula
- Kritik tablolarda (audit, overrides, intents) veri bütünlüğü kontrol et

### Post-Rollback Doğrulama
- [ ] `/api/runtime/quote-policy` doğru dönüyor
- [ ] Invalid quote bloklanıyor
- [ ] action→result trace_id zinciri çalışıyor
- [ ] UI’da state validation kartı bozulmadan yükleniyor

## E) Operasyonel Not
Rollback bir başarısızlık değil; canlı riskini düşüren kontrollü güvenlik prosedürüdür.