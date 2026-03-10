# Sistem Mimari Diyagramı (Metin Tabanlı)

```text
[React Web UI]
   |
   | HTTPS (/api)
   v
[FastAPI API Gateway]
   |-- Auth Module (JWT + Role)
   |-- Bot Config Module
   |-- Risk Policy Module
   |-- Strategy Template Module
   |-- Audit Module
   |-- Exchange Adapter Layer
         |-- BinanceMockAdapter (Phase-1)
         |-- BybitAdapter (Phase-2)
         |-- OKXAdapter (Phase-2)
   |
   |-- SQLAlchemy Repository --> [PostgreSQL]
   |-- Cache/State ----------> [Redis]
```

Not: Phase-1'de execution sadece MOCK akışıdır, canlı trade yoktur.
