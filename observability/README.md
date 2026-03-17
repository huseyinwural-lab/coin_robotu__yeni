# Observability Stack (Faz-2)

Bu klasör self-host **Loki + Promtail + Grafana + Alertmanager** kurulumunu içerir.

## Hedef
- Structured backend loglarını topla
- Request/Session correlation ile sorgulanabilir hale getir
- `invalid_key` artışı ve `health flap` için erken uyarı üret

## Kurulum

```bash
cd /app/observability
cp .env.example .env
docker compose -f docker-compose.loki.yml --env-file .env up -d
```

## Erişim
- Grafana: `http://<host>:3001`
- Loki API: `http://<host>:3100`
- Alertmanager: `http://<host>:9093`

## Varsayılan Alert Kuralları
- `InvalidKeySurge`
- `ExchangeHealthFlap`
- `ValidationFailureRateHigh`

Kural dosyası: `loki/rules/trading-alerts.yaml`

## Log Kaynağı
- Backend supervisor logları: `/var/log/supervisor/backend*.log`
- Frontend supervisor logları: `/var/log/supervisor/frontend*.log`

Promtail parse ettiği alanları label olarak çıkarır:
- `event_type`, `reason_code`, `method`, `status_code`, `level`

## Operasyonel Notlar
- Uygulama içi retention temizliği: `/api/audit-logs/admin/retention/prune?days=90`
- Loki tarafı retention: `loki/config.yaml` içinde `retention_period: 2160h` (90 gün)

## Doğrulama

```bash
curl -s http://localhost:3100/ready
curl -s http://localhost:3001/api/health
```

Grafana dashboard otomatik provision edilir:
- `Trading Observability Overview`
