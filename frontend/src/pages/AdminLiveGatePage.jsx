import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, CircleAlert, CircleDashed, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const stateMeta = {
  PASS: { label: "PASS", className: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30", icon: CheckCircle2 },
  FAIL: { label: "FAIL", className: "bg-rose-500/20 text-rose-300 border-rose-500/30", icon: CircleAlert },
  WAIT: { label: "BEKLİYOR", className: "bg-amber-500/20 text-amber-300 border-amber-500/30", icon: CircleDashed },
};

const hasAnyReason = (readiness, list) => {
  const codes = new Set(readiness?.reason_codes || []);
  return list.some((item) => codes.has(item));
};

export const AdminLiveGatePage = () => {
  const [loading, setLoading] = useState(true);
  const [rerunLoading, setRerunLoading] = useState(false);
  const [gate, setGate] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [liveConfig, setLiveConfig] = useState(null);
  const [proxyHealth, setProxyHealth] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [gateResp, readinessResp, configResp, proxyResp] = await Promise.allSettled([
        apiClient.get("/phase4/admin/production-gate?refresh_checks=false"),
        apiClient.get("/admin/execution-readiness"),
        apiClient.get("/phase4/live-config"),
        apiClient.get("/runtime/exchange/proxy-health"),
      ]);

      setGate(gateResp.status === "fulfilled" ? gateResp.value.data : null);
      setReadiness(readinessResp.status === "fulfilled" ? readinessResp.value.data : null);
      setLiveConfig(configResp.status === "fulfilled" ? configResp.value.data : null);
      setProxyHealth(proxyResp.status === "fulfilled" ? proxyResp.value.data : null);

      const hasHardFail = [gateResp, readinessResp].some((item) => item.status === "rejected");
      if (hasHardFail) {
        setError("Bazı canlı geçiş kontrolleri okunamadı. Yenile ile tekrar dene.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const rerunGate = async () => {
    setRerunLoading(true);
    try {
      await apiClient.post("/phase4/admin/production-gate/checks/rerun", {});
      await load();
    } finally {
      setRerunLoading(false);
    }
  };

  const steps = useMemo(() => {
    const proxySpot = proxyHealth?.result?.spot || {};
    const proxyFutures = proxyHealth?.result?.futures || {};

    return [
      {
        id: 1,
        title: "Key Girişi",
        desc: "Kullanıcının Binance live API key/secret bağlantısı girilmiş olmalı.",
        state: readiness?.exchange_connection === "OK" ? "PASS" : "FAIL",
        to: "/user/exchange-settings",
      },
      {
        id: 2,
        title: "Key Doğrulama & Permission",
        desc: "Permission ve can_trade doğrulaması geçmeli.",
        state: readiness?.permissions === "OK" ? "PASS" : "FAIL",
        to: "/admin/execution-readiness",
      },
      {
        id: 3,
        title: "Venue & Allowed Market",
        desc: "Live spot/futures market açık olmalı, market_disabled olmamalı.",
        state: hasAnyReason(readiness, ["market_disabled", "live_not_allowed", "assignment_required", "testnet_not_allowed"]) ? "FAIL" : "PASS",
        to: "/admin/credential-orchestration",
      },
      {
        id: 4,
        title: "Kill Switch",
        desc: "Canlıya çıkmadan önce kill switch kapalı, trading aktif olmalı.",
        state: liveConfig?.kill_switch_enabled ? "FAIL" : "PASS",
        to: "/admin/live-trading-dashboard",
      },
      {
        id: 5,
        title: "Risk Policy",
        desc: "Risk Engine aktif ve readiness reason_code içinde risk bloklayıcı olmamalı.",
        state: hasAnyReason(readiness, ["RISK_POLICY_MISSING", "EXPOSURE_NO_EQUITY", "MARGIN_DATA_MISSING"]) ? "FAIL" : "PASS",
        to: "/admin/risk-orchestrator",
      },
      {
        id: 6,
        title: "Strategy Template",
        desc: "Strateji motoru biliniyor olmalı (STRATEGY_ENGINE_UNKNOWN olmamalı).",
        state: hasAnyReason(readiness, ["STRATEGY_ENGINE_UNKNOWN"]) ? "FAIL" : "PASS",
        to: "/admin/strategies",
      },
      {
        id: 7,
        title: "Bot Oluştur & Başlat",
        desc: "Bot profili oluşturup RUNNING durumuna alınmalı.",
        state: hasAnyReason(readiness, ["ORDER_EXECUTION_MISSING", "WORKER_STATE_UNKNOWN"]) ? "WAIT" : "PASS",
        to: "/user/bot-profiles",
      },
      {
        id: 8,
        title: "Production Gate Rerun",
        desc: "Stale check kalmamalı. GO ve deploy_allowed=true olmalı.",
        state: gate?.effective_state === "GO" && gate?.deploy_allowed ? "PASS" : "FAIL",
        to: "/admin/live-trading-dashboard",
      },
      {
        id: 9,
        title: "Mode Transition LIVE",
        desc: "Execution mode LIVE ve final_status READY olmalı.",
        state: readiness?.mode === "LIVE" && readiness?.final_status === "READY" ? "PASS" : "FAIL",
        to: "/admin/live-trading-dashboard",
      },
      {
        id: 10,
        title: "Canlı Akış İzleme",
        desc: "Proxy health, execution readiness ve gate sürekli izlenmeli.",
        state:
          proxySpot?.proxy_token_set &&
          proxySpot?.base_url_set &&
          proxyFutures?.proxy_token_set &&
          proxyFutures?.base_url_set
            ? "PASS"
            : "FAIL",
        to: "/admin/execution-readiness",
      },
    ];
  }, [gate, readiness, liveConfig, proxyHealth]);

  return (
    <section className="space-y-5" data-testid="admin-live-gate-page">
      <div className="rounded border border-slate-700 bg-slate-900/60 p-4" data-testid="admin-live-gate-header-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-slate-100" data-testid="admin-live-gate-title">Live Gate</h1>
            <p className="text-sm text-slate-300" data-testid="admin-live-gate-subtitle">Canlıya alma prosedürü tek alanda, sıralı ve takip edilebilir.</p>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={load}
              disabled={loading}
              data-testid="admin-live-gate-refresh-button"
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Yenile
            </Button>
            <Button
              type="button"
              onClick={rerunGate}
              disabled={rerunLoading}
              data-testid="admin-live-gate-rerun-button"
            >
              {rerunLoading ? "Rerun..." : "Gate Checks Rerun"}
            </Button>
          </div>
        </div>
        {error ? <p className="mt-3 text-sm text-amber-300" data-testid="admin-live-gate-error-text">{error}</p> : null}
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-live-gate-steps-grid">
        {steps.map((step) => {
          const meta = stateMeta[step.state] || stateMeta.WAIT;
          const Icon = meta.icon;
          return (
            <article key={step.id} className="rounded border border-slate-700 bg-slate-900/60 p-4" data-testid={`admin-live-gate-step-card-${step.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase text-slate-400" data-testid={`admin-live-gate-step-index-${step.id}`}>Adım {step.id}</p>
                  <h2 className="text-base font-semibold text-slate-100" data-testid={`admin-live-gate-step-title-${step.id}`}>{step.title}</h2>
                  <p className="mt-1 text-sm text-slate-300" data-testid={`admin-live-gate-step-desc-${step.id}`}>{step.desc}</p>
                </div>
                <span className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-xs ${meta.className}`} data-testid={`admin-live-gate-step-badge-${step.id}`}>
                  <Icon className="h-3.5 w-3.5" /> {meta.label}
                </span>
              </div>
              <div className="mt-3">
                <Link to={step.to} data-testid={`admin-live-gate-step-link-${step.id}`} className="text-sm font-medium text-cyan-300 hover:text-cyan-200">
                  İlgili ekrana git →
                </Link>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
};
