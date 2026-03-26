# Live Prep Proxy Timeout Patch

## Amaç
- 502 ve websocket idle timeout riskini azaltmak
- `/api/runtime/ws/*` hatlarında bağlantı düşmesini önlemek

## Nginx Patch
- Dosya: `/app/infra/nginx/live_timeout_patch.conf`
- Uygula: ilgili `server/location` bloğuna include edin.

## K8s Ingress Patch
- Dosya: `/app/infra/k8s/ingress-timeout-patch.yaml`
- Uygula: `kubectl apply -f /app/infra/k8s/ingress-timeout-patch.yaml`

## Beklenen Sonuç
- Login timeout düşüşü
- Runtime websocket bağlantılarında daha az disconnect
- Upstream timeout kaynaklı 502 azalması
