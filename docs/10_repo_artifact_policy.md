# Repo Artifact Policy (FAZ-1 / Görev-1)

## 1) Sınıflandırma

### A. Kaynak kod / zorunlu içerik
- `backend/`, `frontend/`, `scripts/`, `.github/workflows/`, `docs/`, `memory/`

### B. Runtime üretimi (kaynak kod dışı)
- `*.db`, `*.db-journal`
- `backend/exports/` içindeki rapor/evidence çıktıları
- `artifacts/reports/` içindeki rapor çıktıları
- `test_reports/` içindeki test artefact ve koşu çıktıları

### C. Değerlendirildi, korunacak alanlar
- `backend/exports/` (runtime servisleri tarafından aktif kullanılıyor)
- `artifacts/reports/` (weekly reporting servisleri tarafından aktif kullanılıyor)
- `test_reports/` (test zinciri referansları mevcut)

## 2) Politika

- Silme yerine önce `.gitignore` ile ayrıştırma uygulanır.
- Kör toplu silme yapılmaz.
- Temizlik yalnız açıkça izinli path listesi üzerinde ve tek tek değerlendirme ile yapılır.

## 3) Bu iterasyonda path değerlendirme sonucu

### Değerlendirilen tekil dosyalar
- `backend/test_learning.db` → runtime/test/docker/readme bağı bulunmadı; temizlemeye uygun
- `trading_platform_local.db` → runtime/test/docker/readme bağı bulunmadı; temizlemeye uygun

### Değerlendirilen klasörler
- `backend/exports/` → runtime bağı var, korunacak
- `artifacts/reports/` → runtime bağı var, korunacak
- `test_reports/` → test zinciri bağı var, korunacak

## 4) Operasyonel kural

- Production repo kaynak kod odaklı tutulur.
- Runtime çıktılarının kalıcılığı için artifact storage tercih edilir.
- Test çıktıları geçici çalışma verisi olarak ele alınır.