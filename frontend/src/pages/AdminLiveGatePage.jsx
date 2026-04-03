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

export const AdminLiveGatePage = () => {
  const [loading, setLoading] = useState(true);
  const [rerunLoading, setRerunLoading] = useState(false);
  const [unblockLoading, setUnblockLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState({});
  const [gate, setGate] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [liveConfig, setLiveConfig] = useState(null);
  const [proxyHealth, setProxyHealth] = useState(null);
  const [manualComplete, setManualComplete] = useState({});
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [gateResp, readinessResp, configResp, proxyResp, progressResp] = await Promise.allSettled([
        apiClient.get("/phase4/admin/production-gate?refresh_checks=false"),
        apiClient.get("/admin/execution-readiness"),
        apiClient.get("/phase4/live-config"),
        apiClient.get("/runtime/exchange/proxy-health"),
        apiClient.get("/phase4/admin/live-gate/wizard-progress"),
      ]);

      setGate(gateResp.status === "fulfilled" ? gateResp.value.data : null);
      setReadiness(readinessResp.status === "fulfilled" ? readinessResp.value.data : null);
      setLiveConfig(configResp.status === "fulfilled" ? configResp.value.data : null);
      setProxyHealth(proxyResp.status === "fulfilled" ? proxyResp.value.data : null);

      if (progressResp.status === "fulfilled") {
        const ids = progressResp.value.data?.completed_step_ids || [];
        const mapped = ids.reduce((acc, id) => ({ ...acc, [id]: true }), {});
        setManualComplete(mapped);
      }

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

  const saveProgress = async (nextMap) => {
    const completedIds = Object.keys(nextMap)
      .filter((key) => nextMap[key])
      .map((key) => Number(key))
      .sort((a, b) => a - b);
    await apiClient.put("/phase4/admin/live-gate/wizard-progress", { completed_step_ids: completedIds });
  };

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

  const applyKillSwitch = async (enabled) => {
    const configResp = await apiClient.get("/phase4/live-config");
    const config = configResp.data || {};
    await apiClient.put("/phase4/live-config", {
      ...config,
      kill_switch_enabled: enabled,
      trading_enabled: !enabled,
    });
  };

  const autoUnblock = async () => {
    const confirmationPhrase = window.prompt("Onay için AUTO UNBLOCK yazın");
    if (String(confirmationPhrase || "").trim().toUpperCase() !== "AUTO UNBLOCK") {
      setError("Auto Unblock iptal edildi: onay metni doğrulanmadı.");
      return;
    }
    if (!window.confirm("Auto Unblock işlemi kritik aksiyonlar çalıştıracak. Devam edilsin mi?")) {
      return;
    }
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

      await applyKillSwitch(false);
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

  const runStepFix = async (stepId) => {
    setActionLoading((prev) => ({ ...prev, [stepId]: true }));
    try {
      if (stepId === 3) {
        await ensureAllowedMarketEnabled("binance", "futures", "live");
        await ensureAllowedMarketEnabled("binance", "spot", "live");
      }
      if (stepId === 8) {
        await apiClient.post("/phase4/admin/production-gate/checks/rerun", {});
      }
      if (stepId === 9) {
        await apiClient.post("/phase4/admin/production-gate/mode-transition", {
          target_mode: "LIVE",
          reason_text: "live gate step fix",
          confirmation_phrase: "SWITCH TO LIVE",
        });
      }
      await load();
    } catch (stepError) {
      const message = stepError?.response?.data?.detail || "Adım düzeltme işlemi başarısız oldu.";
      setError(String(message));
    } finally {
      setActionLoading((prev) => ({ ...prev, [stepId]: false }));
    }
  };

  const steps = useMemo(() => {
    const proxySpot = proxyHealth?.result?.spot || {};
    const proxyFutures = proxyHealth?.result?.futures || {};

    const reasons = readiness?.reason_codes || [];
    const gateReasons = gate?.blocked_reason_codes || [];

    return [
      {
        id: 1,
        title: "Key Girişi",
        desc: "Kullanıcının Binance live API key/secret bağlantısı girilmiş olmalı.",
        state: readiness?.exchange_connection === "OK" ? "PASS" : "FAIL",
        reason: reasons.filter((code) => ["EXCHANGE_CONNECTION_MISSING", "invalid_key", "exchange_error_451"].includes(code)).join(", "),
        to: "/user/exchange-settings",
      },
      {
        id: 2,
        title: "Key Doğrulama & Permission",
        desc: "Permission ve can_trade doğrulaması geçmeli.",
        state: readiness?.permissions === "OK" ? "PASS" : "FAIL",
        reason: reasons.filter((code) => ["missing_trade_permission", "permission_check_fail", "missing_credentials"].includes(code)).join(", "),
        to: "/admin/execution-readiness",
      },
      {
        id: 3,
        title: "Venue & Allowed Market",
        desc: "Live spot/futures market açık olmalı, market_disabled olmamalı.",
        state: hasAnyReason(readiness, ["market_disabled", "live_not_allowed", "assignment_required"]) ? "FAIL" : "PASS",
        reason: reasons.filter((code) => ["market_disabled", "live_not_allowed", "assignment_required"].includes(code)).join(", "),
        to: "/admin/credential-orchestration",
      },
      {
        id: 4,
        title: "Kill Switch",
        desc: "Bu adımda blokaj koyma/kaldırma işlemi yapılır.",
        state: liveConfig?.kill_switch_enabled ? "FAIL" : "PASS",
        reason: liveConfig?.kill_switch_enabled ? "kill_switch_enabled" : "",
        to: "/admin/live-trading-dashboard",
      },
      {
        id: 5,
        title: "Risk Policy",
        desc: "Risk Engine aktif ve readiness reason_code içinde risk bloklayıcı olmamalı.",
        state: hasAnyReason(readiness, ["RISK_POLICY_MISSING", "EXPOSURE_NO_EQUITY", "MARGIN_DATA_MISSING"]) ? "FAIL" : "PASS",
        reason: reasons.filter((code) => ["RISK_POLICY_MISSING", "EXPOSURE_NO_EQUITY", "MARGIN_DATA_MISSING"].includes(code)).join(", "),
        to: "/admin/risk-orchestrator",
      },
      {
        id: 6,
        title: "Strategy Template",
        desc: "Strateji motoru biliniyor olmalı (STRATEGY_ENGINE_UNKNOWN olmamalı).",
        state: hasAnyReason(readiness, ["STRATEGY_ENGINE_UNKNOWN"]) ? "FAIL" : "PASS",
        reason: reasons.filter((code) => ["STRATEGY_ENGINE_UNKNOWN"].includes(code)).join(", "),
        to: "/admin/strategies",
      },
      {
        id: 7,
        title: "Bot Oluştur & Başlat",
        desc: "Bot profili oluşturup RUNNING durumuna alınmalı.",
        state: hasAnyReason(readiness, ["ORDER_EXECUTION_MISSING", "WORKER_STATE_UNKNOWN"]) ? "WAIT" : "PASS",
        reason: reasons.filter((code) => ["ORDER_EXECUTION_MISSING", "WORKER_STATE_UNKNOWN"].includes(code)).join(", "),
        to: "/user/bot-profiles",
      },
      {
        id: 8,
        title: "Production Gate Rerun",
        desc: "Stale check kalmamalı. GO ve deploy_allowed=true olmalı.",
        state: gate?.effective_state === "GO" && gate?.deploy_allowed ? "PASS" : "FAIL",
        reason: gateReasons.join(", "),
        to: "/admin/live-trading-dashboard",
      },
      {
        id: 9,
        title: "Mode Transition LIVE",
        desc: "Execution mode LIVE ve final_status READY olmalı.",
        state: readiness?.mode === "LIVE" && readiness?.final_status === "READY" ? "PASS" : "FAIL",
        reason: readiness?.mode !== "LIVE" ? `mode=${readiness?.mode || "-"}` : readiness?.final_status !== "READY" ? `final_status=${readiness?.final_status || "-"}` : "",
        to: "/admin/live-trading-dashboard",
      },
      {
        id: 10,
        title: "Canlı Akış İzleme",
        desc: "Proxy health, execution readiness ve gate sürekli izlenmeli.",
        state: proxySpot?.proxy_token_set && proxySpot?.base_url_set && proxyFutures?.proxy_token_set && proxyFutures?.base_url_set ? "PASS" : "FAIL",
        reason:
          proxySpot?.proxy_token_set && proxySpot?.base_url_set && proxyFutures?.proxy_token_set && proxyFutures?.base_url_set
            ? ""
            : "proxy_missing_or_token_missing",
        to: "/admin/execution-readiness",
      },
    ];
  }, [gate, readiness, liveConfig, proxyHealth]);

  const wizardSteps = useMemo(() => {
    return steps.map((step, index) => {
      const previousSteps = steps.slice(0, index);
      const unlocked = previousSteps.every((prev) => prev.state === "PASS" || !!manualComplete[prev.id]);
      const manualDoneAllowed = step.state !== "FAIL";
      const done = step.state === "PASS" || (manualDoneAllowed && !!manualComplete[step.id]);
      return { ...step, unlocked, done, manualDoneAllowed };
    });
  }, [steps, manualComplete]);

  const doneCount = wizardSteps.filter((item) => item.done).length;

  const markStepDone = async (id) => {
    const target = wizardSteps.find((item) => item.id === id);
    if (!target?.unlocked) {
      setError("Bu adım henüz kilitli. Önce önceki adımları tamamlayın.");
      return;
    }
    if (!target?.manualDoneAllowed) {
      setError("FAIL durumundaki adım manuel tamamlanamaz. Önce fix uygulayın.");
      return;
    }
    const next = { ...manualComplete, [id]: true };
    setManualComplete(next);
    try {
      await saveProgress(next);
    } catch {
      setError("Adım tamamlanma bilgisi backend'e kaydedilemedi.");
    }
  };

  const resetStepDone = async (id) => {
    const target = wizardSteps.find((item) => item.id === id);
    if (!target?.unlocked) {
      setError("Bu adım henüz kilitli.");
      return;
    }
    const next = { ...manualComplete };
    delete next[id];
    setManualComplete(next);
    try {
      await saveProgress(next);
    } catch {
      setError("Adım sıfırlama bilgisi backend'e kaydedilemedi.");
    }
  };

  return (
    <section className="space-y-5" data-testid="admin-live-gate-page">
      <div className="rounded border border-slate-700 bg-slate-900/60 p-4" data-testid="admin-live-gate-header-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-slate-100" data-testid="admin-live-gate-title">Live Gate</h1>
            <p className="text-sm text-slate-300" data-testid="admin-live-gate-subtitle">Canlıya alma prosedürü tek alanda, sıralı ve kilitli wizard olarak yönetilir.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={load} disabled={loading} data-testid="admin-live-gate-refresh-button">
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Yenile
            </Button>
            <Button type="button" onClick={rerunGate} disabled={rerunLoading} data-testid="admin-live-gate-rerun-button">
              {rerunLoading ? "Rerun..." : "Gate Checks Rerun"}
            </Button>
            <Button type="button" variant="secondary" onClick={autoUnblock} disabled={unblockLoading} data-testid="admin-live-gate-auto-unblock-button">
              <Wrench className="mr-2 h-4 w-4" /> {unblockLoading ? "Blokaj kaldırılıyor..." : "Diğer Blokajları Kaldır"}
            </Button>
          </div>
        </div>
        <p className="mt-3 text-sm text-slate-300" data-testid="admin-live-gate-progress-text">Wizard İlerlemesi: <strong>{doneCount}/10</strong></p>
        {error ? <p className="mt-3 text-sm text-amber-300" data-testid="admin-live-gate-error-text">{error}</p> : null}
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-live-gate-steps-grid">
        {wizardSteps.map((step) => {
          const meta = stateMeta[step.state] || stateMeta.WAIT;
          const Icon = meta.icon;
          const isKillStep = step.id === 4;
          const showFixButton = [3, 8, 9].includes(step.id);

          return (
            <article key={step.id} className="rounded border border-slate-700 bg-slate-900/60 p-4" data-testid={`admin-live-gate-step-card-${step.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase text-slate-400" data-testid={`admin-live-gate-step-index-${step.id}`}>Adım {step.id}</p>
                  <h2 className="text-base font-semibold text-slate-100" data-testid={`admin-live-gate-step-title-${step.id}`}>{step.title}</h2>
                  <p className="mt-1 text-sm text-slate-300" data-testid={`admin-live-gate-step-desc-${step.id}`}>{step.desc}</p>
                  {step.reason ? (
                    <p className="mt-1 text-xs text-amber-300" data-testid={`admin-live-gate-step-reason-${step.id}`}>
                      neden FAIL: {step.reason}
                    </p>
                  ) : null}
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

                {showFixButton ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={!step.unlocked || !!actionLoading[step.id]}
                    onClick={() => runStepFix(step.id)}
                    data-testid={`admin-live-gate-step-fix-button-${step.id}`}
                  >
                    {actionLoading[step.id] ? "Çalışıyor..." : "Tek Tık Fix"}
                  </Button>
                ) : null}

                {isKillStep ? (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={!step.unlocked || !!actionLoading[41]}
                      onClick={async () => {
                        setActionLoading((prev) => ({ ...prev, 41: true }));
                        try {
                          await applyKillSwitch(true);
                          await load();
                        } finally {
                          setActionLoading((prev) => ({ ...prev, 41: false }));
                        }
                      }}
                      data-testid="admin-live-gate-kill-switch-block-button"
                    >
                      {actionLoading[41] ? "Uygulanıyor..." : "Blokaj Koy"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={!step.unlocked || !!actionLoading[42]}
                      onClick={async () => {
                        setActionLoading((prev) => ({ ...prev, 42: true }));
                        try {
                          await applyKillSwitch(false);
                          await load();
                        } finally {
                          setActionLoading((prev) => ({ ...prev, 42: false }));
                        }
                      }}
                      data-testid="admin-live-gate-kill-switch-unblock-button"
                    >
                      {actionLoading[42] ? "Uygulanıyor..." : "Blokaj Kaldır"}
                    </Button>
                  </>
                ) : null}

                <Button type="button" size="sm" variant="outline" disabled={!step.unlocked || step.done || !step.manualDoneAllowed} onClick={() => markStepDone(step.id)} data-testid={`admin-live-gate-step-complete-button-${step.id}`}>
                  Tamamlandı İşaretle
                </Button>
                <Button type="button" size="sm" variant="ghost" disabled={!manualComplete[step.id]} onClick={() => resetStepDone(step.id)} data-testid={`admin-live-gate-step-reset-button-${step.id}`}>
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
