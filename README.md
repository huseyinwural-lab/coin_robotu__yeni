# Trading Platform — Docker Quickstart

## 1) Environment dosyalarını oluştur

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`frontend/.env` içinde backend URL'i browser erişimine göre ayarlayın:

- Local kullanım: `REACT_APP_BACKEND_URL=http://localhost:8001`
- Sunucu/LAN kullanım: `REACT_APP_BACKEND_URL=http://<HOST_IP>:8001`

Not: Browser `http://backend:8001` hostname’ini çözmez; bu değer sadece Docker network içi servisler için uygundur.

`backend/.env` içindeki `CORS_ORIGINS` değerine de aynı host/IP origin'ini ekleyin:

- Örnek: `http://localhost:3000,http://127.0.0.1:3000,http://<HOST_IP>:3000`
- Not: `<HOST_IP>` placeholder'ını gerçek sunucu/LAN IP adresinizle değiştirin.

Package manager:

- Frontend için deterministik kurulum: **Yarn** (`yarn.lock` + Dockerfile `--frozen-lockfile`).

## 2) Compose doğrulama

```bash
docker compose config
```

## 3) Build + çalıştır

```bash
docker compose up -d --build
```

## 4) Durum kontrol

```bash
docker compose ps
```

## 5) Erişim URL'leri

- Frontend: `http://localhost:3000` (veya `http://<HOST_IP>:3000`)
- Backend API: `http://localhost:8001/api` (veya `http://<HOST_IP>:8001/api`)

## 6) Varsayılan admin (ilk kurulum / boş DB)

- Email: `admin@platform.dev`
- Password: `Admin12345!`

Bootstrap davranışı deterministic'tir:

- Sadece `users` tablosu boşken varsayılan admin oluşturulur.
- Tablo boş değilse tekrar oluşturulmaz.
- Duplicate oluşmaz.
- Yeni admin ekleyip varsayılan admin'i sildiğinizde (tablo boş olmadığı sürece) otomatik yeniden oluşmaz.
