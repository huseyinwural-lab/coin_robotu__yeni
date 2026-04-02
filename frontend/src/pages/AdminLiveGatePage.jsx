import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, CircleAlert, CircleDashed, Lock, RefreshCw, Wrench } from "lucide-react";

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

const COMPLETION_STORAGE_KEY = "live_gate_wizard_completions_v1";

export const AdminLiveGatePage = () => {
  const [loading, setLoading] = useState(true);
  const [rerunLoading, setRerunLoading] = useState(false);
  const [unblockLoading, setUnblockLoading] = useState(false);
  const [gate, setGate] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [liveConfig, setLiveConfig] = useState(null);
  const [proxyHealth, setProxyHealth] = useState(null);
  const [manualComplete, setManualComplete] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(COMPLETION_STORAGE_KEY) || "{}");
    } catch {
      return {};
    }
  });
  const [error, setError] = useState("");

  useEffect(() => {
    localStorage.setItem(COMPLETION_STORAGE_KEY, JSON.stringify(manualComplete));
  }, [manualComplete]);

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

  const ensureAllowedMarketEnabled = async (exchange, market, environment) => {
    const listResp = await apiClient.get("/venues/admin/allowed-markets");
    const rows = listResp.data || [];
    const found = rows.find(
      (row) =>
        String(row.exchange_code || "").toLowerCase() === exchange &&
        String(row.market_type || "").toLowerCase() === market &&
        String(row.environment || "").toLowerCase() === environment,
    );
    if (!found) {
      await apiClient.post("/venues/admin/allowed-markets", {
        exchange_code: exchange,
        market_type: market,
        environment,
        enabled: true,
      });
      return;
    }
    if (!found.enabled) {
      await apiClient.put(`/venues/admin/allowed-markets/${found.id}`, { enabled: true });
    }
  };

  const autoUnblock = async () => {
    setUnblockLoading(true);
    setError("");
    try {
      await apiClient.post("/phase4/admin/production-gate/checks/rerun", {});

      const gateResp = await apiClient.get("/phase4/admin/production-gate?refresh_checks=false");
      const currentGate = gateResp.data || {};
      if (currentGate.effective_state !== "GO") {
        await apiClient.post("/phase4/admin/production-gate/state", {
          target_state: "GO",
          reason_code: "LIVE_GATE_AUTO_UNBLOCK",
          reason_text: "live gate auto unblock",
        });
      }

      const configResp = await apiClient.get("/phase4/live-config");
      const config = configResp.data || {};
      await apiClient.put("/phase4/live-config", {
        ...config,
        kill_switch_enabled: false,
        trading_enabled: true,
      });

      await ensureAllowedMarketEnabled("binance", "futures", "live");
      await ensureAllowedMarketEnabled("binance", "spot", "live");

      await load();
    } catch (unblockError) {
      const message = unblockError?.response?.data?.detail || "Otomatik blokaj kaldırma sırasında hata oluştu.";
      setError(String(message));
    } finally {
      setUnblockLoading(false);
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

  const wizardSteps = useMemo(() => {
    return steps.map((step, index) => {
      const previous = steps.slice(0, index);
      const previousDone = previous.every((item) => item.state === "PASS" || manualComplete[item.id]);
      const unlocked = index === 0 || previousDone;
      const done = step.state === "PASS" || !!manualComplete[step.id];
      return { ...step, unlocked, done };
    });
  }, [steps, manualComplete]);

  const doneCount = wizardSteps.filter((item) => item.done).length;

  const markStepDone = (id) => {
    setManualComplete((prev) => ({ ...prev, [id]: true }));
  };

  const resetStepDone = (id) => {
    setManualComplete((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

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
            <Button
              type="button"
              variant="secondary"
              onClick={autoUnblock}
              disabled={unblockLoading}
              data-testid="admin-live-gate-auto-unblock-button"
            >
              <Wrench className="mr-2 h-4 w-4" /> {unblockLoading ? "Blokaj kaldırılıyor..." : "Blokajları Otomatik Kaldır"}
            </Button>
          </div>
        </div>
        <p className="mt-3 text-sm text-slate-300" data-testid="admin-live-gate-progress-text">
          Wizard İlerlemesi: <strong>{doneCount}/10</strong>
        </p>
        {error ? <p className="mt-3 text-sm text-amber-300" data-testid="admin-live-gate-error-text">{error}</p> : null}
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-live-gate-steps-grid">
        {wizardSteps.map((step) => {
          const meta = stateMeta[step.state] || stateMeta.WAIT;
          const Icon = meta.icon;
          return (
            <article key={step.id} className="rounded border border-slate-700 bg-slate-900/60 p-4" data-testid={`admin-live-gate-step-card-${step.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase text-slate-400" data-testid={`admin-live-gate-step-index-${step.id}`}>Adım {step.id}</p>
                  <h2 className="text-base font-semibold text-slate-100" data-testid={`admin-live-gate-step-title-${step.id}`}>{step.title}</h2>
                  <p className="mt-1 text-sm text-slate-300" data-testid={`admin-live-gate-step-desc-${step.id}`}>{step.desc}</p>
                  {!step.unlocked ? (
                    <p className="mt-1 inline-flex items-center gap-1 text-xs text-amber-300" data-testid={`admin-live-gate-step-locked-${step.id}`}>
                      <Lock className="h-3 w-3" /> Önce önceki adımları tamamla
                    </p>
                  ) : null}
                </div>
                <span className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-xs ${meta.className}`} data-testid={`admin-live-gate-step-badge-${step.id}`}>
                  <Icon className="h-3.5 w-3.5" /> {meta.label}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Link
                  to={step.unlocked ? step.to : "#"}
                  onClick={(event) => {
                    if (!step.unlocked) event.preventDefault();
                  }}
                  data-testid={`admin-live-gate-step-link-${step.id}`}
                  className={`text-sm font-medium ${step.unlocked ? "text-cyan-300 hover:text-cyan-200" : "cursor-not-allowed text-slate-500"}`}
                >
                  İlgili ekrana git →
                </Link>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!step.unlocked || step.done}
                  onClick={() => markStepDone(step.id)}
                  data-testid={`admin-live-gate-step-complete-button-${step.id}`}
                >
                  Tamamlandı İşaretle
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={!manualComplete[step.id]}
                  onClick={() => resetStepDone(step.id)}
                  data-testid={`admin-live-gate-step-reset-button-${step.id}`}
                >
                  İşareti Kaldır
                </Button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
};
