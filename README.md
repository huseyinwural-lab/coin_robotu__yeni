# Trading Platform — Final Hardening Quickstart

## 0) Repo içeriği ve zorunlu dosyalar

- `backend/.env.example`
- `frontend/.env.example`
- `backend/migrations/*` (Alembic zinciri)
- `backend/tests/*` ve `tests/*` (test katmanları)

Runtime çıktıları (`*.db`, test artefact görselleri, snapshot/debug çıktıları) kaynak kod kapsamı dışında tutulmalıdır.
Repo artefact sınıflandırma politikası: `docs/10_repo_artifact_policy.md`

## 1) Environment hazırlığı

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`frontend/.env`:

- Local: `REACT_APP_BACKEND_URL=http://localhost:8001`
- LAN/Sunucu: `REACT_APP_BACKEND_URL=http://<HOST_IP>:8001`

`backend/.env`:

- `CORS_ORIGINS` içine frontend origin’lerini ekleyin
- Örnek: `http://localhost:3000,http://127.0.0.1:3000,http://<HOST_IP>:3000`

## 2) Frontend package manager standardı

- Resmi frontend kurulum modeli: **Yarn**
- Deterministik build: `frontend/yarn.lock` + Dockerfile `yarn install --frozen-lockfile --non-interactive`
- Monorepo kökünde package manager kullanılmaz.

## 3) Docker ile ayağa kaldırma

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

## 4) Servis URL’leri

- Frontend: `http://localhost:3000` veya `http://<HOST_IP>:3000`
- Backend API: `http://localhost:8001/api` veya `http://<HOST_IP>:8001/api`

## 5) Startup akışı (gerçek çalışma sırası)

Backend startup sırası:

1. Alembic migration `head`
2. Bootstrap seed kontrolleri
3. Runtime servis başlangıcı

Not: Startup içinde `create_all` kullanılmaz; schema otoritesi Alembic’tir.

## 6) Varsayılan admin bootstrap davranışı

Varsayılan admin seed yalnızca `users` tablosu tamamen boşken çalışır.

- Kimlik bilgileri `backend/.env` içindeki `DEFAULT_ADMIN_EMAIL` ve `DEFAULT_ADMIN_PASSWORD` alanlarından okunur.
- Repo içinde operasyonel kullanım için sabit credential tekrarları tutulmamalıdır.
- Kurulum varsayılan bootstrap admin:
  - Email/Kullanıcı adı: `admin@platform.local`
  - Şifre: `Admin12345!`

- Tablo doluysa seed/recreate/reset yapılmaz.
- Duplicate kullanıcı üretilmez.
- İlk başarılı girişten sonra admin panelinden profil ve şifre güncellemesi yapılmalıdır.

## 7) Test komutları

Backend (lokal):

```bash
cd backend
pytest
```

Credential gerektiren script/testler için env tabanlı kullanım:

```bash
export TEST_ADMIN_EMAIL="admin@platform.local"
export TEST_ADMIN_PASSWORD="Admin12345!"
export TEST_USER_EMAIL="<user-email>"
export TEST_USER_PASSWORD="<user-password>"
```

Frontend (lokal):

```bash
cd frontend
yarn test
```

## 8) Development vs Production farkları

Development:

- PostgreSQL erişilemezse SQLite fallback devreye alınabilir.
- Redis erişilemezse in-memory fallback devreye alınabilir.

Production hedefi:

- PostgreSQL + Redis zorunlu kabul edilir.
- Fallback modları production eşdeğeri sayılmaz; yalnız geliştirme/teşhis amaçlıdır.

## 9) Fallback davranış özeti

- DB fallback: PostgreSQL bağlantısı kurulamazsa SQLite kullanılabilir.
- Cache fallback: Redis bağlantısı kurulamazsa in-memory cache kullanılabilir.
- Bu modlarda davranış sınırları capability matrix ile değerlendirilmelidir.

## 10) Frontend smoke checklist (release)

- Landing page açılıyor.
- Sayfa boş değil.
- `Kullanıcı Girişi` aksiyonu görünür.
- `Admin Girişi` aksiyonu görünür.
- Kritik console error yok.

## 11) Operasyon notları

- Bybit/OKX bu turda placeholder warning modundadır.
- `candidate_count = 0` bazı taramalarda hata değil, karar sonucu olabilir.
- Fallback aktifleştiğinde top volume moda geçiş normal davranıştır.
- Bootstrap admin bilgileri:
  - `admin@platform.local`
  - `Admin12345!`
- Prod/stage için ilk girişten sonra admin profil ve şifre güncellenmelidir.
