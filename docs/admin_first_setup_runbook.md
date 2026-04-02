# Admin İlk Kurulum Runbook (Canlı Kullanım Öncesi)

Bu runbook, admin tarafında ilk kurulum doğrulamasını **tek script** ile standartlaştırır.

## 1) Amaç
- API sağlık ve hazır durumunu doğrulamak
- Admin oturumunu güvenli cihaz-bağlı şekilde doğrulamak (`X-Session-Device`)
- Canlı operasyon kapılarının açık olduğunu doğrulamak:
  - `Execution Readiness = LIVE + go_live_allowed=true`
  - `Production Gate = GO + deploy_allowed=true`

## 2) Script
- Dosya: `/app/scripts/admin_first_setup_guide.sh`

## 3) Hızlı kullanım

### A) Varsayılanlarla çalıştır
```bash
bash /app/scripts/admin_first_setup_guide.sh
```

### B) Özel URL ve admin bilgisi ile
```bash
bash /app/scripts/admin_first_setup_guide.sh \
  --base-url "https://<senin-url>.preview.emergentagent.com" \
  --admin-email "admin@example.com" \
  --admin-password "StrongPassword"
```

### C) JSON raporu artefact olarak kaydet
```bash
bash /app/scripts/admin_first_setup_guide.sh \
  --json-out /app/artifacts/admin_first_setup_report.json
```

## 4) Beklenen PASS kriteri
- `api_health` → HTTP 200, `status=ok`
- `api_ready` → HTTP 200, `status=ready`
- `admin_login` → HTTP 200, `access_token` mevcut
- `execution_readiness` → HTTP 200, `go_live_allowed=true`, `mode=LIVE`
- `production_gate` → HTTP 200, `configured_state=GO`, `effective_state=GO`, `deploy_allowed=true`

## 5) Kurulum sonrası admin akışı (özet)
1. Admin panelde market-data tarafını doğrula (Admin key data/control-plane için).
2. User key execution hattını doğrula (User key ile trade, fallback kapalı).
3. Kill-switch ve küçük notional test-order ile operasyonel hazır olma kontrolünü tamamla.

## 6) Not
- Preview ortamında backend doğrulamalarını `/api/*` üzerinden yap.
- Bu script **read-only doğrulama** odaklıdır; konfigürasyon yazmaz.
