#!/usr/bin/env bash
set -euo pipefail
NS=prod
INGRESS_NS=ingress-nginx
INGRESS_DEPLOY=ingress-nginx-controller
kubectl -n "$NS" apply -f /app/infra/k8s/ingress-timeout-patch.yaml
# include /app/infra/nginx/live_timeout_patch.conf on ingress nginx and reload
kubectl -n "$INGRESS_NS" rollout restart deploy/"$INGRESS_DEPLOY"
kubectl -n "$INGRESS_NS" rollout status deploy/"$INGRESS_DEPLOY"
