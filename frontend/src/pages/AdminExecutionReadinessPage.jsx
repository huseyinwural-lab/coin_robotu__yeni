import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { apiClient } from "@/lib/api";

export const AdminExecutionReadinessPage = () => {
  const [gate, setGate] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [ops, setOps] = useState(null);
  const [checkHistory, setCheckHistory] = useState(null);
  const [compareData, setCompareData] = useState(null);
  const [overrideAnalytics, setOverrideAnalytics] = useState(null);
  const [timelineData, setTimelineData] = useState(null);
  const [historyFilterCheckKey, setHistoryFilterCheckKey] = useState("ALL");
  const [historyFilterStatus, setHistoryFilterStatus] = useState("ALL");
  const [timelineFilter, setTimelineFilter] = useState({ checks: true, overrides: true, mode: true, deploy: true });
  const [flappingWindowSec, setFlappingWindowSec] = useState(300);
  const [flappingThreshold, setFlappingThreshold] = useState(3);
  const [riskWeights, setRiskWeights] = useState({
    fail_rate_weight: 0.4,
    flapping_weight: 0.2,
    override_rate_weight: 0.3,
    stale_weight: 0.1,
  });
  const [crossCheckResult, setCrossCheckResult] = useState(null);
  const [cleanupResult, setCleanupResult] = useState(null);
  const [stateReasonCode, setStateReasonCode] = useState("MANUAL_RISK_ACCEPTANCE");
  const [stateReasonText, setStateReasonText] = useState("Pre-deploy kontroller tamamlandı.");
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideReasonCode, setOverrideReasonCode] = useState("INCIDENT_MITIGATION");
  const [overrideReasonText, setOverrideReasonText] = useState("");
  const [overrideTtl, setOverrideTtl] = useState(15);
  const [modeModalOpen, setModeModalOpen] = useState(false);
  const [targetMode, setTargetMode] = useState("LIVE");
  const [modeReason, setModeReason] = useState("Canary doğrulandı, LIVE geçişi başlatılıyor.");
  const [confirmationPhrase, setConfirmationPhrase] = useState("SWITCH TO LIVE");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [autoRefreshIntervalSec, setAutoRefreshIntervalSec] = useState(30);
  const [newFailPulse, setNewFailPulse] = useState(false);
  const [exportScope, setExportScope] = useState("full");
  const [exportDateFrom, setExportDateFrom] = useState("");
  const [exportDateTo, setExportDateTo] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const previousFailCountRef = useRef(0);

  const expectedPhrase = useMemo(() => {
    if (targetMode === "TESTNET") return "SWITCH TO TESTNET";
    if (targetMode === "SIM") return "SWITCH TO SIM";
    if (targetMode === "PAPER") return "SWITCH TO PAPER";
    if (targetMode === "MOCK") return "SWITCH TO MOCK";
    return "SWITCH TO LIVE";
  }, [targetMode]);

  const deployBlocked = !gate?.deploy_allowed;

  const load = useCallback(async (refreshChecks = false) => {
    setLoading(true);
    try {
      const [
        { data: gateData },
        { data: readinessData },
        { data: opsData },
        { data: historyData },
        { data: comparePayload },
        { data: analyticsPayload },
        { data: timelinePayload },
      ] = await Promise.all([
        apiClient.get(`/phase4/admin/production-gate?refresh_checks=${refreshChecks ? "true" : "false"}`),
        apiClient.get("/admin/execution-readiness"),
        apiClient.get("/phase4/admin/production-gate/ops-overview"),
        apiClient.get("/phase4/admin/production-gate/checks/history?limit=300"),
        apiClient.get("/phase4/admin/production-gate/checks/compare?limit=300"),
        apiClient.get("/phase4/admin/production-gate/override-analytics"),
        apiClient.get("/phase4/admin/production-gate/timeline?limit=400"),
      ]);
      setGate(gateData);
      setReadiness(readinessData);
      setOps(opsData);
      setCheckHistory(historyData);
      setCompareData(comparePayload);
      setOverrideAnalytics(analyticsPayload);
      setTimelineData(timelinePayload);

      const flappingConfig = historyData?.flapping_config || {};
      if (flappingConfig.window_sec) setFlappingWindowSec(Number(flappingConfig.window_sec));
      if (flappingConfig.threshold) setFlappingThreshold(Number(flappingConfig.threshold));

      const nextFailCount = Number(opsData?.active_fail_count || 0);
      if (nextFailCount > previousFailCountRef.current) {
        setNewFailPulse(true);
      }
      previousFailCountRef.current = nextFailCount;
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Production Gate verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  useEffect(() => {
    if (!autoRefreshEnabled) return undefined;
    const timer = setInterval(() => {
      load(false);
    }, Math.max(Number(autoRefreshIntervalSec || 0), 10) * 1000);
    return () => clearInterval(timer);
  }, [autoRefreshEnabled, autoRefreshIntervalSec, load]);

  const runAction = useCallback(
    async (runner, successMessage) => {
      setActionLoading(true);
      try {
        await runner();
        await load(false);
        toast.success(successMessage);
      } catch (error) {
        const detail = error?.response?.data?.detail;
        const fallback = typeof detail === "string" ? detail : detail?.error || "İşlem başarısız";
        toast.error(fallback);
      } finally {
        setActionLoading(false);
      }
    },
    [load]
  );

  const handleChecklistToggle = useCallback(
    async (itemKey, checked) => {
      await runAction(async () => {
        const { data } = await apiClient.patch(`/phase4/admin/production-gate/checklist/${itemKey}`, { checked });
        return data;
      }, "Checklist güncellendi");
    },
    [runAction]
  );

  const handleStateUpdate = useCallback(
    async (targetState) => {
      await runAction(async () => {
        const { data } = await apiClient.post("/phase4/admin/production-gate/state", {
          target_state: targetState,
          reason_code: stateReasonCode,
          reason_text: stateReasonText,
        });
        return data;
      }, `${targetState} işlemi tamamlandı`);
    },
    [runAction, stateReasonCode, stateReasonText]
  );

  const handleRerun = useCallback(
    async (checkKey = null) => {
      await runAction(async () => {
        const path = checkKey
          ? `/phase4/admin/production-gate/checks/${checkKey}/rerun`
          : "/phase4/admin/production-gate/checks/rerun";
        const { data } = await apiClient.post(path);
        return data;
      }, checkKey ? `${checkKey} yeniden çalıştırıldı` : "Tüm kontroller yeniden çalıştırıldı");
    },
    [runAction]
  );

  const handleCreateOverride = useCallback(async () => {
    await runAction(async () => {
      await apiClient.post("/phase4/admin/production-gate/override", {
        reason_code: overrideReasonCode,
        reason_text: overrideReasonText,
        ttl_minutes: Number(overrideTtl),
      });
      setOverrideOpen(false);
      setOverrideReasonText("");
    }, "GO_WITH_OVERRIDE aktif edildi");
  }, [overrideReasonCode, overrideReasonText, overrideTtl, runAction]);

  const handleRevokeOverride = useCallback(async () => {
    if (!gate?.active_override?.override_id) return;
    await runAction(async () => {
      await apiClient.post(
        `/phase4/admin/production-gate/override/${gate.active_override.override_id}/revoke`
      );
    }, "Override revoke edildi");
  }, [gate?.active_override?.override_id, runAction]);

  const handleModeTransition = useCallback(async () => {
    await runAction(async () => {
      await apiClient.post("/phase4/admin/production-gate/mode-transition", {
        target_mode: targetMode,
        reason_text: modeReason,
        confirmation_phrase: confirmationPhrase,
      });
      setModeModalOpen(false);
    }, `${targetMode} geçiş isteği gönderildi`);
  }, [targetMode, modeReason, confirmationPhrase, runAction]);

  const handleApiKeyTestRun = useCallback(
    async (connectionId = null, exchange = null) => {
      await runAction(async () => {
        await apiClient.post("/phase4/admin/production-gate/api-key-tests/run", {
          connection_id: connectionId,
          exchange,
        });
      }, connectionId ? "API key testi çalıştırıldı" : "Tüm API key testleri çalıştırıldı");
    },
    [runAction]
  );

  const handleOrderScenarioRerun = useCallback(
    async (scenarioKey = null) => {
      await runAction(async () => {
        await apiClient.post("/phase4/admin/production-gate/order-scenarios/rerun", {
          scenario_key: scenarioKey,
        });
      }, scenarioKey ? `${scenarioKey} senaryosu yeniden çalıştırıldı` : "Order scenario matrix yeniden çalıştırıldı");
    },
    [runAction]
  );

  const handleHardeningConfigUpdate = useCallback(async () => {
    await runAction(async () => {
      await apiClient.patch("/phase4/admin/production-gate/hardening-config", {
        flapping: {
          window_sec: Number(flappingWindowSec),
          threshold: Number(flappingThreshold),
        },
        risk_weights: {
          fail_rate_weight: Number(riskWeights.fail_rate_weight),
          flapping_weight: Number(riskWeights.flapping_weight),
          override_rate_weight: Number(riskWeights.override_rate_weight),
          stale_weight: Number(riskWeights.stale_weight),
        },
      });
    }, "Hardening config güncellendi");
  }, [flappingWindowSec, flappingThreshold, riskWeights, runAction]);

  const handleRunCleanupJob = useCallback(async () => {
    await runAction(async () => {
      const { data } = await apiClient.post("/phase4/admin/production-gate/history/cleanup?force=true");
      setCleanupResult(data);
    }, "History cleanup job çalıştı");
  }, [runAction]);

  const handleRunCrossCheck = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/phase4/admin/production-gate/system/cross-check");
      setCrossCheckResult(data);
      toast.success("Cross-check tutarlı");
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setCrossCheckResult(detail || { is_consistent: false, mismatches: ["unknown"] });
      toast.error("Cross-check mismatch: FAIL");
    }
  }, []);

  const handleExportJson = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.append("scope", exportScope);
      if (exportDateFrom) {
        params.append("date_from", new Date(exportDateFrom).toISOString());
      }
      if (exportDateTo) {
        params.append("date_to", new Date(exportDateTo).toISOString());
      }

      const { data } = await apiClient.get(`/phase4/admin/production-gate/export/raw?${params.toString()}`);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `production-gate-${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("JSON export hazır");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "JSON export alınamadı");
    }
  }, [exportDateFrom, exportDateTo, exportScope]);

  const failCodesText = useMemo(() => (ops?.active_fail_codes || []).join(", "), [ops?.active_fail_codes]);

  const filteredHistoryItems = useMemo(() => {
    const rows = checkHistory?.items || [];
    return rows.filter((row) => {
      if (historyFilterCheckKey !== "ALL" && row.check_key !== historyFilterCheckKey) return false;
      if (historyFilterStatus !== "ALL" && row.status !== historyFilterStatus) return false;
      return true;
    });
  }, [checkHistory?.items, historyFilterCheckKey, historyFilterStatus]);

  const historyCheckKeys = useMemo(() => {
    const keys = new Set((checkHistory?.items || []).map((item) => item.check_key));
    return ["ALL", ...Array.from(keys)];
  }, [checkHistory?.items]);

  const filteredTimelineItems = useMemo(() => {
    const rows = timelineData?.items || [];
    return rows.filter((item) => {
      if (item.category === "checks" && !timelineFilter.checks) return false;
      if (item.category === "overrides" && !timelineFilter.overrides) return false;
      if (item.category === "mode" && !timelineFilter.mode) return false;
      if (item.category === "deploy" && !timelineFilter.deploy) return false;
      return true;
    });
  }, [timelineData?.items, timelineFilter]);

  const reasonDistribution = useMemo(() => overrideAnalytics?.reason_distribution || {}, [overrideAnalytics?.reason_distribution]);

  const reasonPieStyle = useMemo(() => {
    const entries = Object.entries(reasonDistribution);
    const total = entries.reduce((sum, [, count]) => sum + Number(count || 0), 0);
    if (total <= 0) {
      return { background: "conic-gradient(#334155 0deg 360deg)" };
    }
    const palette = ["#f59e0b", "#ef4444", "#22c55e", "#38bdf8", "#a78bfa", "#fb7185", "#2dd4bf"];
    let current = 0;
    const segments = entries.map(([, count], index) => {
      const share = (Number(count || 0) / total) * 360;
      const next = current + share;
      const color = palette[index % palette.length];
      const segment = `${color} ${current}deg ${next}deg`;
      current = next;
      return segment;
    });
    return { background: `conic-gradient(${segments.join(",")})` };
  }, [reasonDistribution]);

  return (
    <section className="space-y-6" data-testid="admin-production-gate-page">
      <header className="rounded-xl border border-slate-700 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-800 p-5" data-testid="admin-production-gate-header">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="admin-production-gate-header-row">
          <div data-testid="admin-production-gate-header-left">
            <h1 className="text-4xl font-black tracking-tight text-amber-300" data-testid="admin-production-gate-title">Production Gate Control Panel</h1>
            <p className="mt-2 text-sm text-slate-300" data-testid="admin-production-gate-subtitle">Deploy ve LIVE aktivasyonu sadece GO / GO_WITH_OVERRIDE ile açılır.</p>
            <p className={`mt-2 inline-flex rounded-full px-3 py-1 text-xs font-semibold ${gate?.risk_level === "HIGH" ? "bg-red-900 text-red-100" : gate?.risk_level === "MEDIUM" ? "bg-amber-900 text-amber-100" : "bg-emerald-900 text-emerald-100"}`} data-testid="admin-production-gate-risk-badge">
              risk: {gate?.risk_level || "LOW"} ({gate?.risk_score ?? 0})
            </p>
          </div>
          <div className="flex flex-wrap gap-2" data-testid="admin-production-gate-header-actions">
            <Button variant="outline" onClick={() => load(true)} disabled={loading || actionLoading} data-testid="admin-production-gate-refresh-button">Yenile</Button>
            <Button variant="outline" onClick={() => setNewFailPulse(false)} data-testid="admin-production-gate-clear-fail-pulse-button">Yeni FAIL işaretini temizle</Button>
            <Button variant="outline" onClick={handleExportJson} data-testid="admin-production-gate-export-json-button">JSON Export</Button>
            <Button onClick={() => handleRerun()} disabled={actionLoading} data-testid="admin-production-gate-rerun-all-button">Tüm Checkleri Rerun</Button>
          </div>
        </div>

        <div className="mt-4 grid gap-2 md:grid-cols-4" data-testid="admin-production-gate-live-controls-grid">
          <label className="flex items-center gap-2 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200" data-testid="admin-production-gate-auto-refresh-toggle-wrapper">
            <input type="checkbox" checked={autoRefreshEnabled} onChange={(event) => setAutoRefreshEnabled(event.target.checked)} data-testid="admin-production-gate-auto-refresh-toggle" />
            Auto-refresh
          </label>
          <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200" data-testid="admin-production-gate-auto-refresh-interval-wrapper">
            <label className="mr-2" data-testid="admin-production-gate-auto-refresh-interval-label">interval(sec)</label>
            <select value={autoRefreshIntervalSec} onChange={(event) => setAutoRefreshIntervalSec(Number(event.target.value))} data-testid="admin-production-gate-auto-refresh-interval-select" className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs">
              <option value={15}>15</option>
              <option value={30}>30</option>
              <option value={60}>60</option>
              <option value={120}>120</option>
            </select>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200" data-testid="admin-production-gate-export-scope-wrapper">
            <label className="mr-2" data-testid="admin-production-gate-export-scope-label">scope</label>
            <select value={exportScope} onChange={(event) => setExportScope(event.target.value)} data-testid="admin-production-gate-export-scope-select" className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs">
              <option value="full">full</option>
              <option value="summary">summary</option>
              <option value="audit">audit</option>
            </select>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200" data-testid="admin-production-gate-refresh-state-indicator">
            refresh_state: {autoRefreshEnabled ? `active (${autoRefreshIntervalSec}s)` : "paused"}
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 md:col-span-2" data-testid="admin-production-gate-export-date-from-wrapper">
            <label className="mr-2" data-testid="admin-production-gate-export-date-from-label">date_from</label>
            <input type="datetime-local" value={exportDateFrom} onChange={(event) => setExportDateFrom(event.target.value)} data-testid="admin-production-gate-export-date-from-input" className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs" />
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 md:col-span-2" data-testid="admin-production-gate-export-date-to-wrapper">
            <label className="mr-2" data-testid="admin-production-gate-export-date-to-label">date_to</label>
            <input type="datetime-local" value={exportDateTo} onChange={(event) => setExportDateTo(event.target.value)} data-testid="admin-production-gate-export-date-to-input" className="rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs" />
          </div>
        </div>

        <div className="mt-3 rounded-lg border border-slate-700 bg-slate-950 p-3" data-testid="admin-production-gate-hardening-config-panel">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-production-gate-hardening-config-header">
            <p className="text-xs font-semibold text-slate-200" data-testid="admin-production-gate-hardening-config-title">Hardening Config (Flapping + Risk Weights)</p>
            <Button variant="outline" onClick={handleHardeningConfigUpdate} disabled={actionLoading} data-testid="admin-production-gate-hardening-config-save-button">Kaydet</Button>
          </div>
          <div className="mt-2 grid gap-2 text-xs md:grid-cols-3" data-testid="admin-production-gate-hardening-config-grid">
            <label className="flex items-center gap-2" data-testid="admin-production-gate-flapping-window-wrapper">window_sec
              <input type="number" min={60} value={flappingWindowSec} onChange={(event) => setFlappingWindowSec(Number(event.target.value))} className="rounded border border-slate-600 bg-slate-900 px-2 py-1" data-testid="admin-production-gate-flapping-window-input" />
            </label>
            <label className="flex items-center gap-2" data-testid="admin-production-gate-flapping-threshold-wrapper">threshold
              <input type="number" min={2} value={flappingThreshold} onChange={(event) => setFlappingThreshold(Number(event.target.value))} className="rounded border border-slate-600 bg-slate-900 px-2 py-1" data-testid="admin-production-gate-flapping-threshold-input" />
            </label>
            <label className="flex items-center gap-2" data-testid="admin-production-gate-risk-weight-fail-wrapper">fail_w
              <input type="number" step="0.01" min={0} value={riskWeights.fail_rate_weight} onChange={(event) => setRiskWeights((prev) => ({ ...prev, fail_rate_weight: event.target.value }))} className="rounded border border-slate-600 bg-slate-900 px-2 py-1" data-testid="admin-production-gate-risk-weight-fail-input" />
            </label>
            <label className="flex items-center gap-2" data-testid="admin-production-gate-risk-weight-flapping-wrapper">flapping_w
              <input type="number" step="0.01" min={0} value={riskWeights.flapping_weight} onChange={(event) => setRiskWeights((prev) => ({ ...prev, flapping_weight: event.target.value }))} className="rounded border border-slate-600 bg-slate-900 px-2 py-1" data-testid="admin-production-gate-risk-weight-flapping-input" />
            </label>
            <label className="flex items-center gap-2" data-testid="admin-production-gate-risk-weight-override-wrapper">override_w
              <input type="number" step="0.01" min={0} value={riskWeights.override_rate_weight} onChange={(event) => setRiskWeights((prev) => ({ ...prev, override_rate_weight: event.target.value }))} className="rounded border border-slate-600 bg-slate-900 px-2 py-1" data-testid="admin-production-gate-risk-weight-override-input" />
            </label>
            <label className="flex items-center gap-2" data-testid="admin-production-gate-risk-weight-stale-wrapper">stale_w
              <input type="number" step="0.01" min={0} value={riskWeights.stale_weight} onChange={(event) => setRiskWeights((prev) => ({ ...prev, stale_weight: event.target.value }))} className="rounded border border-slate-600 bg-slate-900 px-2 py-1" data-testid="admin-production-gate-risk-weight-stale-input" />
            </label>
          </div>
          <div className="mt-2 text-xs text-slate-300" data-testid="admin-production-gate-risk-explanation-list">
            {(gate?.risk_explanation || []).map((item, index) => (
              <p key={`${item}-${index}`} data-testid={`admin-production-gate-risk-explanation-item-${index}`}>• {item}</p>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="admin-production-gate-hardening-ops-actions">
            <Button variant="outline" onClick={handleRunCleanupJob} disabled={actionLoading} data-testid="admin-production-gate-cleanup-job-button">Cleanup Job Çalıştır</Button>
            <Button variant="outline" onClick={handleRunCrossCheck} disabled={actionLoading} data-testid="admin-production-gate-cross-check-button">Analytics Cross-Check</Button>
          </div>
          <div className="mt-2 text-xs text-slate-300" data-testid="admin-production-gate-hardening-ops-results">
            <p data-testid="admin-production-gate-cleanup-result">cleanup_result: {cleanupResult ? JSON.stringify(cleanupResult) : "-"}</p>
            <p data-testid="admin-production-gate-cross-check-result">cross_check_result: {crossCheckResult ? JSON.stringify(crossCheckResult) : "-"}</p>
          </div>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-production-gate-status-grid">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-configured-state-card">
          <p className="text-xs text-slate-400">Configured State</p>
          <p className="mt-1 text-lg font-semibold text-white" data-testid="admin-production-gate-configured-state-value">{gate?.configured_state || "-"}</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-effective-state-card">
          <p className="text-xs text-slate-400">Effective State</p>
          <p className={`mt-1 text-lg font-semibold ${gate?.effective_state === "GO" ? "text-emerald-300" : gate?.effective_state === "GO_WITH_OVERRIDE" ? "text-amber-300" : "text-red-300"}`} data-testid="admin-production-gate-effective-state-value">
            {gate?.effective_state || "-"}
          </p>
          {gate?.effective_state === "GO_WITH_OVERRIDE" && <p className="mt-1 text-xs text-amber-200" data-testid="admin-production-gate-override-risk-label">RISK OVERRIDE ACTIVE</p>}
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-deploy-status-card">
          <p className="text-xs text-slate-400">Deploy / LIVE</p>
          <p className={`mt-1 text-lg font-semibold ${deployBlocked ? "text-red-300" : "text-emerald-300"}`} data-testid="admin-production-gate-deploy-status-value">{deployBlocked ? "BLOCKED" : "ALLOWED"}</p>
          <p className="mt-1 text-xs text-slate-400" data-testid="admin-production-gate-release-contract-value">release_gate_contract: {gate?.release_gate_contract || "UNKNOWN"}</p>
        </div>
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-3" data-testid="admin-production-gate-readiness-card">
          <p className="text-xs text-slate-400">Execution Readiness</p>
          <p className="mt-1 text-lg font-semibold text-white" data-testid="admin-production-gate-readiness-mode">mode: {readiness?.mode || "-"}</p>
          <p className="mt-1 text-sm text-slate-300" data-testid="admin-production-gate-readiness-final">final_status: {readiness?.final_status || "-"}</p>
        </div>
      </div>

      {deployBlocked && (
        <div className="rounded-lg border border-red-700 bg-red-950/20 p-3 text-sm text-red-200" data-testid="admin-production-gate-blocked-banner">
          HARD BLOCK aktif: Deploy/LIVE aksiyonları 403 ile reddedilir. reason_codes: {(gate?.blocked_reason_codes || []).join(", ") || "state_no_go"}
        </div>
      )}

      {!!ops?.active_fail_count && (
        <div className="rounded-lg border border-rose-700 bg-rose-950/30 p-3 text-sm text-rose-200" data-testid="admin-production-gate-active-fail-banner">
          ACTIVE FAIL ALERT: {ops.active_fail_count} fail bulundu. codes: {failCodesText || "-"}
        </div>
      )}

      {newFailPulse && (
        <div className="rounded-lg border border-amber-600 bg-amber-950/30 p-3 text-sm text-amber-200" data-testid="admin-production-gate-new-fail-banner">
          Yeni FAIL oluştu. Operasyon detay panellerini kontrol edin.
        </div>
      )}

      {gate?.effective_state === "GO_WITH_OVERRIDE" && (
        <div className="rounded-lg border border-amber-700 bg-amber-950/30 p-3 text-sm text-amber-100" data-testid="admin-production-gate-override-active-banner">
          OVERRIDE RISK: GO_WITH_OVERRIDE aktif, süreli bypass modundasınız.
        </div>
      )}

      {!!(gate?.flapping_checks || []).length && (
        <div className="rounded-lg border border-fuchsia-700 bg-fuchsia-950/30 p-3 text-sm text-fuchsia-100" data-testid="admin-production-gate-flapping-banner">
          FLAPPING DETECTED: {(gate?.flapping_checks || []).join(", ")}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-production-gate-main-grid">
        <div className="space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-controls-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-controls-title">Gate Actions</h2>
          <div className="grid gap-2" data-testid="admin-production-gate-reason-form">
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-reason-code-label">reason_code</label>
            <input className="rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={stateReasonCode} onChange={(event) => setStateReasonCode(event.target.value)} data-testid="admin-production-gate-reason-code-input" />
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-reason-text-label">reason_text</label>
            <textarea className="rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" rows={3} value={stateReasonText} onChange={(event) => setStateReasonText(event.target.value)} data-testid="admin-production-gate-reason-text-input" />
          </div>
          <div className="flex flex-wrap gap-2" data-testid="admin-production-gate-state-buttons-row">
            <Button onClick={() => handleStateUpdate("GO")} disabled={actionLoading || !gate?.checklist_complete || !gate?.checks_all_pass || gate?.has_stale_or_running} data-testid="admin-production-gate-go-button">GO</Button>
            <Button variant="destructive" onClick={() => handleStateUpdate("NO_GO")} disabled={actionLoading} data-testid="admin-production-gate-no-go-button">NO_GO</Button>
            <Button variant="outline" onClick={() => setOverrideOpen(true)} disabled={actionLoading} data-testid="admin-production-gate-open-override-modal-button">GO_WITH_OVERRIDE</Button>
            <Button variant="outline" onClick={handleRevokeOverride} disabled={actionLoading || !gate?.active_override?.override_id} data-testid="admin-production-gate-revoke-override-button">Override Revoke</Button>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-3 text-xs text-slate-300" data-testid="admin-production-gate-override-summary-card">
            <p data-testid="admin-production-gate-override-id-value">override_id: {gate?.active_override?.override_id || "-"}</p>
            <p data-testid="admin-production-gate-override-reason-value">reason_code: {gate?.active_override?.reason_code || "-"}</p>
            <p data-testid="admin-production-gate-override-expiry-value">expires_at: {gate?.active_override?.expires_at || "-"}</p>
          </div>
        </div>

        <div className="space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-mode-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-mode-panel-title">Mode Transition Guard</h2>
          <p className="text-xs text-slate-300" data-testid="admin-production-gate-mode-panel-description">MOCK/PAPER → LIVE geçişi onay ifadesi + reason + gate state ile korunur.</p>
          <Button onClick={() => setModeModalOpen(true)} disabled={actionLoading} data-testid="admin-production-gate-open-mode-modal-button">Mode Change</Button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-checklist-panel">
        <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-checklist-title">Pre-deploy Checklist</h2>
        <div className="mt-3 grid gap-2" data-testid="admin-production-gate-checklist-items">
          {(gate?.checklist || []).map((item, index) => (
            <label key={item.item_key} className="flex items-center gap-2 rounded border border-slate-700 bg-slate-950 p-2" data-testid={`admin-production-gate-checklist-item-${item.item_key}`}>
              <input type="checkbox" checked={!!item.checked} onChange={(event) => handleChecklistToggle(item.item_key, event.target.checked)} data-testid={`admin-production-gate-checklist-item-toggle-${item.item_key}`} />
              <span className="text-sm text-white" data-testid={`admin-production-gate-checklist-item-title-${item.item_key}`}>{item.title}</span>
              <span className="ml-auto text-xs text-slate-400" data-testid={`admin-production-gate-checklist-item-status-${item.item_key}`}>{item.checked ? "DONE" : "PENDING"}</span>
              <span className="sr-only" data-testid={`admin-production-gate-checklist-item-index-${index}`}>{index}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-checks-panel">
        <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-checks-title">Automated Checks</h2>
        <div className="mt-3 space-y-2" data-testid="admin-production-gate-checks-list">
          {(gate?.checks || []).map((check) => (
            <div key={check.check_key} className="rounded border border-slate-700 bg-slate-950 p-3" data-testid={`admin-production-gate-check-row-${check.check_key}`}>
              <div className="flex flex-wrap items-center gap-2" data-testid={`admin-production-gate-check-row-header-${check.check_key}`}>
                <p className="text-sm font-semibold text-white" data-testid={`admin-production-gate-check-title-${check.check_key}`}>{check.title}</p>
                <p className={`text-xs ${check.status === "PASS" && !check.stale ? "text-emerald-300" : "text-red-300"}`} data-testid={`admin-production-gate-check-status-${check.check_key}`}>{check.status}{check.stale ? " (STALE)" : ""}</p>
                <Button variant="outline" className="ml-auto" onClick={() => handleRerun(check.check_key)} disabled={actionLoading} data-testid={`admin-production-gate-check-rerun-button-${check.check_key}`}>Rerun</Button>
              </div>
              <p className="mt-2 text-xs text-red-200" data-testid={`admin-production-gate-check-fail-reason-${check.check_key}`}>fail_reason: {check.fail_reason || "-"}</p>
              <p className="mt-1 text-xs text-amber-200" data-testid={`admin-production-gate-check-remediation-${check.check_key}`}>remediation: {check.remediation || "-"}</p>
              <p className="mt-1 text-xs text-sky-200" data-testid={`admin-production-gate-check-runbook-${check.check_key}`}>runbook: {check?.remediation_payload?.runbook_ref || "-"}</p>
            </div>
          ))}
          {(gate?.checks || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-checks-empty">Check listesi boş.</p>}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-production-gate-ops-grid">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-api-key-tests-panel">
          <div className="flex items-center justify-between" data-testid="admin-production-gate-api-key-tests-header">
            <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-api-key-tests-title">API Key Test Control</h2>
            <Button variant="outline" onClick={() => handleApiKeyTestRun()} disabled={actionLoading} data-testid="admin-production-gate-api-key-test-run-all-button">Test API Key (All)</Button>
          </div>
          <div className="mt-3 space-y-2" data-testid="admin-production-gate-api-key-tests-list">
            {(ops?.api_key_tests || []).map((item) => (
              <div key={item.connection_id} className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid={`admin-production-gate-api-key-test-row-${item.connection_id}`}>
                <div className="flex flex-wrap items-center gap-2" data-testid={`admin-production-gate-api-key-test-row-header-${item.connection_id}`}>
                  <p className="text-white" data-testid={`admin-production-gate-api-key-test-exchange-${item.connection_id}`}>{item.exchange} / {item.market_type} / {item.environment}</p>
                  <p className={`${item.success ? "text-emerald-300" : "text-red-300"}`} data-testid={`admin-production-gate-api-key-test-status-${item.connection_id}`}>{item.status}</p>
                  <Button variant="outline" className="ml-auto" onClick={() => handleApiKeyTestRun(item.connection_id, item.exchange)} disabled={actionLoading} data-testid={`admin-production-gate-api-key-test-rerun-button-${item.connection_id}`}>Rerun</Button>
                </div>
                <p className="mt-1 text-slate-300" data-testid={`admin-production-gate-api-key-test-fail-reason-${item.connection_id}`}>fail_reason: {item.fail_reason || "-"}</p>
                <p className="mt-1 text-slate-300" data-testid={`admin-production-gate-api-key-test-response-summary-${item.connection_id}`}>response_summary: {JSON.stringify(item.response_summary || {})}</p>
                <p className="mt-1 text-slate-300" data-testid={`admin-production-gate-api-key-test-last-tested-${item.connection_id}`}>last_tested_at: {item.last_tested_at || "-"}</p>
                <p className="mt-1 text-sky-200" data-testid={`admin-production-gate-api-key-test-runbook-${item.connection_id}`}>runbook: {item.runbook_ref || "-"}</p>
              </div>
            ))}
            {(ops?.api_key_tests || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-api-key-tests-empty">Henüz API key test sonucu yok.</p>}
          </div>
        </div>

        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-permission-breakdown-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-permission-breakdown-title">Permission Breakdown</h2>
          <div className="mt-3 space-y-2" data-testid="admin-production-gate-permission-breakdown-list">
            {(ops?.permission_breakdown || []).map((item, index) => (
              <div key={`${item.exchange}-${index}`} className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid={`admin-production-gate-permission-row-${index}`}>
                <p className="text-white" data-testid={`admin-production-gate-permission-exchange-${index}`}>{item.exchange} / {item.market_type} / {item.environment}</p>
                <p data-testid={`admin-production-gate-permission-read-${index}`}>read: {item.read_status}</p>
                <p data-testid={`admin-production-gate-permission-write-${index}`}>write: {item.write_status}</p>
                <p data-testid={`admin-production-gate-permission-trade-${index}`}>trade: {item.trade_status}</p>
                <p className="text-red-200" data-testid={`admin-production-gate-permission-fail-reason-${index}`}>fail_reason: {item.fail_reason || "-"}</p>
                <p className="text-sky-200" data-testid={`admin-production-gate-permission-runbook-${index}`}>runbook: {item.runbook_ref || "-"}</p>
              </div>
            ))}
            {(ops?.permission_breakdown || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-permission-breakdown-empty">Permission verisi yok.</p>}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-production-gate-health-mode-grid">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-exchange-health-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-exchange-health-title">Exchange Bazlı Health</h2>
          <div className="mt-3 space-y-2" data-testid="admin-production-gate-exchange-health-list">
            {(ops?.exchange_health || []).map((item, index) => (
              <div key={`${item.exchange}-${item.environment}-${index}`} className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid={`admin-production-gate-exchange-health-row-${index}`}>
                <p className="text-white" data-testid={`admin-production-gate-exchange-health-name-${index}`}>{item.exchange} / {item.market_type} / {item.environment}</p>
                <p data-testid={`admin-production-gate-exchange-health-connection-${index}`}>connection: {item.connection_status}</p>
                <p data-testid={`admin-production-gate-exchange-health-auth-${index}`}>auth: {item.auth_status}</p>
                <p data-testid={`admin-production-gate-exchange-health-permission-${index}`}>permission: {item.permission_status}</p>
                <p data-testid={`admin-production-gate-exchange-health-last-checked-${index}`}>last_checked: {item.last_checked_at || "-"}</p>
                <p className="text-red-200" data-testid={`admin-production-gate-exchange-health-fail-reason-${index}`}>fail_reason: {item.fail_reason || "-"}</p>
                <p className="text-amber-200" data-testid={`admin-production-gate-exchange-health-remediation-${index}`}>remediation: {item.remediation || "-"}</p>
                <p className="text-sky-200" data-testid={`admin-production-gate-exchange-health-runbook-${index}`}>runbook: {item.runbook_ref || "-"}</p>
              </div>
            ))}
            {(ops?.exchange_health || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-exchange-health-empty">Exchange health verisi yok.</p>}
          </div>
        </div>

        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-mode-history-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-mode-history-title">Mode History</h2>
          <div className="mt-3 space-y-2" data-testid="admin-production-gate-mode-history-list">
            {(ops?.mode_history || []).map((item, index) => (
              <div key={`${item.changed_at}-${index}`} className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid={`admin-production-gate-mode-history-row-${index}`}>
                <p className="text-white" data-testid={`admin-production-gate-mode-history-transition-${index}`}>{item.from_mode} → {item.to_mode}</p>
                <p data-testid={`admin-production-gate-mode-history-actor-${index}`}>actor: {item.actor_role} / {item.actor_user_id || "system"}</p>
                <p data-testid={`admin-production-gate-mode-history-reason-${index}`}>reason: {item.reason || "-"}</p>
                <p data-testid={`admin-production-gate-mode-history-request-id-${index}`}>request_id: {item.request_id || "-"}</p>
                <p data-testid={`admin-production-gate-mode-history-changed-at-${index}`}>changed_at: {item.changed_at || "-"}</p>
              </div>
            ))}
            {(ops?.mode_history || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-mode-history-empty">Mode history kaydı yok.</p>}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-order-scenarios-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-production-gate-order-scenarios-header">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-order-scenarios-title">Order Test Scenario Matrix</h2>
          <Button variant="outline" onClick={() => handleOrderScenarioRerun()} disabled={actionLoading} data-testid="admin-production-gate-order-scenarios-rerun-all-button">Tüm Senaryoları Rerun</Button>
        </div>
        <div className="mt-3 space-y-2" data-testid="admin-production-gate-order-scenarios-list">
          {(ops?.order_scenarios || []).map((item) => (
            <div key={item.scenario_key} className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid={`admin-production-gate-order-scenario-row-${item.scenario_key}`}>
              <div className="flex flex-wrap items-center gap-2" data-testid={`admin-production-gate-order-scenario-header-${item.scenario_key}`}>
                <p className="text-white" data-testid={`admin-production-gate-order-scenario-label-${item.scenario_key}`}>{item.label}</p>
                <p data-testid={`admin-production-gate-order-scenario-side-${item.scenario_key}`}>side: {item.side}</p>
                <p data-testid={`admin-production-gate-order-scenario-size-bucket-${item.scenario_key}`}>size: {item.size_bucket}</p>
                <p className={`${item.status === "PASS" ? "text-emerald-300" : item.status === "FAIL" ? "text-red-300" : "text-slate-300"}`} data-testid={`admin-production-gate-order-scenario-status-${item.scenario_key}`}>status: {item.status}</p>
                <Button variant="outline" className="ml-auto" onClick={() => handleOrderScenarioRerun(item.scenario_key)} disabled={actionLoading} data-testid={`admin-production-gate-order-scenario-rerun-button-${item.scenario_key}`}>Rerun</Button>
              </div>
              <p data-testid={`admin-production-gate-order-scenario-latency-${item.scenario_key}`}>latency: {item.latency_ms ?? "-"} ms</p>
              <p data-testid={`admin-production-gate-order-scenario-response-summary-${item.scenario_key}`}>response_summary: {item.response_summary || "-"}</p>
              <p className="text-red-200" data-testid={`admin-production-gate-order-scenario-error-summary-${item.scenario_key}`}>error_summary: {item.error_summary || "-"}</p>
              <p data-testid={`admin-production-gate-order-scenario-last-run-${item.scenario_key}`}>last_run: {item.last_run_at || "-"}</p>
            </div>
          ))}
          {(ops?.order_scenarios || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-order-scenarios-empty">Order scenario verisi yok.</p>}
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-audit-panel">
        <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-audit-title">Audit History</h2>
        <div className="mt-3 space-y-2" data-testid="admin-production-gate-audit-list">
          {(gate?.audit_history || []).map((item, index) => (
            <div key={item.id} className="rounded border border-slate-700 bg-slate-950 p-2 text-xs text-slate-200" data-testid={`admin-production-gate-audit-row-${index}`}>
              <p data-testid={`admin-production-gate-audit-action-${index}`}>{item.action}</p>
              <p data-testid={`admin-production-gate-audit-actor-${index}`}>actor: {item.actor_role} / {item.actor_user_id || "system"}</p>
              <p data-testid={`admin-production-gate-audit-state-${index}`}>transition: {item?.details?.previous_state || "-"} → {item?.details?.next_state || "-"}</p>
              <p data-testid={`admin-production-gate-audit-reason-${index}`}>reason: {item?.details?.reason_code || "-"} / {item?.details?.reason_text || "-"}</p>
            </div>
          ))}
          {(gate?.audit_history || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-audit-empty">Audit kaydı bulunamadı.</p>}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-production-gate-history-compare-grid">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-check-history-panel">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-production-gate-check-history-header">
            <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-check-history-title">Check History & Trend</h2>
            <div className="flex gap-2" data-testid="admin-production-gate-check-history-filters">
              <select value={historyFilterCheckKey} onChange={(event) => setHistoryFilterCheckKey(event.target.value)} className="rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-white" data-testid="admin-production-gate-check-history-check-filter-select">
                {historyCheckKeys.map((key) => (
                  <option key={key} value={key}>{key}</option>
                ))}
              </select>
              <select value={historyFilterStatus} onChange={(event) => setHistoryFilterStatus(event.target.value)} className="rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-white" data-testid="admin-production-gate-check-history-status-filter-select">
                <option value="ALL">ALL</option>
                <option value="PASS">PASS</option>
                <option value="FAIL">FAIL</option>
                <option value="WARN">WARN</option>
              </select>
            </div>
          </div>

          <div className="mt-3 grid gap-2 text-xs" data-testid="admin-production-gate-check-history-trend-summary-list">
            {Object.entries(checkHistory?.trend_summary || {}).map(([key, value]) => (
              <div key={key} className="rounded border border-slate-700 bg-slate-950 p-2" data-testid={`admin-production-gate-check-history-trend-summary-${key}`}>
                <p className="text-white" data-testid={`admin-production-gate-check-history-trend-summary-key-${key}`}>{key}</p>
                <p data-testid={`admin-production-gate-check-history-trend-summary-pass-${key}`}>PASS: {value?.PASS || 0}</p>
                <p data-testid={`admin-production-gate-check-history-trend-summary-fail-${key}`}>FAIL: {value?.FAIL || 0}</p>
                <p data-testid={`admin-production-gate-check-history-trend-summary-warn-${key}`}>WARN: {value?.WARN || 0}</p>
              </div>
            ))}
          </div>

          <div className="mt-3 max-h-64 space-y-2 overflow-y-auto" data-testid="admin-production-gate-check-history-items-list">
            {filteredHistoryItems.map((row, index) => (
              <div key={`${row.run_id}-${index}`} className="rounded border border-slate-700 bg-slate-950 p-2 text-xs" data-testid={`admin-production-gate-check-history-item-${index}`}>
                <p className="text-white" data-testid={`admin-production-gate-check-history-item-key-${index}`}>{row.check_key}</p>
                <p data-testid={`admin-production-gate-check-history-item-status-${index}`}>status: {row.status}</p>
                <p data-testid={`admin-production-gate-check-history-item-latency-${index}`}>latency: {row.latency_ms ?? "-"} ms</p>
                <p data-testid={`admin-production-gate-check-history-item-error-${index}`}>error_code: {row.error_code || "-"}</p>
                <p data-testid={`admin-production-gate-check-history-item-run-id-${index}`}>run_id: {row.run_id}</p>
                <p data-testid={`admin-production-gate-check-history-item-flapping-${index}`}>flapping: {row.flapping ? "FLAPPING" : "NO"}</p>
                <p data-testid={`admin-production-gate-check-history-item-flapping-detail-${index}`}>
                  flapping_detail: count={row?.flapping_detail?.count ?? 0}, window_sec={row?.flapping_detail?.window_sec ?? "-"}, severity={row?.flapping_detail?.severity || "LOW"}
                </p>
              </div>
            ))}
            {filteredHistoryItems.length === 0 && (
              <p className="text-xs text-slate-400" data-testid="admin-production-gate-check-history-empty-explained">
                Check history henüz oluşmadı. En az bir rerun çalıştırılmadan trend üretilemez.
              </p>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-compare-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-compare-title">Before / After Remediation Compare</h2>
          <div className="mt-3 max-h-80 space-y-2 overflow-y-auto" data-testid="admin-production-gate-compare-items-list">
            {(compareData?.items || []).map((item, index) => (
              <div key={`${item.run_id}-${index}`} className="rounded border border-slate-700 bg-slate-950 p-2 text-xs" data-testid={`admin-production-gate-compare-item-${index}`}>
                <p className="text-white" data-testid={`admin-production-gate-compare-item-key-${index}`}>{item.check_key}</p>
                <p data-testid={`admin-production-gate-compare-item-state-delta-${index}`}>state_delta: {item.state_delta}</p>
                <p className={`${(item.new_result === "PASS" && item.previous_result !== "PASS") ? "text-emerald-300" : (item.new_result === "FAIL" && item.previous_result === "PASS") ? "text-red-300" : "text-slate-200"}`} data-testid={`admin-production-gate-compare-item-result-delta-${index}`}>
                  previous_result: {item.previous_result} → new_result: {item.new_result}
                </p>
                <p className={`${Number(item.latency_delta_ms || 0) < 0 ? "text-emerald-300" : Number(item.latency_delta_ms || 0) > 0 ? "text-red-300" : "text-slate-300"}`} data-testid={`admin-production-gate-compare-item-latency-delta-${index}`}>
                  latency_delta_ms: {item.latency_delta_ms ?? "-"}
                </p>
                <p data-testid={`admin-production-gate-compare-item-run-count-${index}`}>run_count: {item.run_count}</p>
                <p data-testid={`admin-production-gate-compare-item-improvement-${index}`}>improvement: {item.improvement ? "YES" : "NO"}</p>
                <p data-testid={`admin-production-gate-compare-item-fail-to-pass-${index}`}>fail_to_pass: {item.fail_to_pass ? "YES" : "NO"}</p>
                <p data-testid={`admin-production-gate-compare-item-stability-${index}`}>stability_score: {item.stability_score}</p>
                <p data-testid={`admin-production-gate-compare-item-explanation-${index}`}>explanation: {(item.explanation || []).join(" | ")}</p>
              </div>
            ))}
            {(compareData?.items || []).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-compare-empty">Compare verisi yok. Rerun sonrası delta burada oluşur.</p>}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="admin-production-gate-analytics-timeline-grid">
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-override-analytics-panel">
          <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-override-analytics-title">Override Analytics</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2" data-testid="admin-production-gate-override-analytics-summary-grid">
            <div className="rounded border border-slate-700 bg-slate-950 p-3 text-xs" data-testid="admin-production-gate-override-analytics-metrics-card">
              <p data-testid="admin-production-gate-override-analytics-count">override_count: {overrideAnalytics?.override_count ?? 0}</p>
              <p data-testid="admin-production-gate-override-analytics-rate">override_rate: {overrideAnalytics?.override_rate ?? 0}%</p>
              <p data-testid="admin-production-gate-override-analytics-expiry">expiry_count: {overrideAnalytics?.expiry_count ?? 0}</p>
              <p data-testid="admin-production-gate-override-analytics-revoke">revoke_count: {overrideAnalytics?.revoke_count ?? 0}</p>
            </div>
            <div className="flex items-center justify-center" data-testid="admin-production-gate-override-analytics-pie-wrapper">
              <div className="h-28 w-28 rounded-full border border-slate-600" style={reasonPieStyle} data-testid="admin-production-gate-override-analytics-pie"></div>
            </div>
          </div>

          <div className="mt-3 space-y-2" data-testid="admin-production-gate-override-analytics-reason-list">
            {Object.entries(reasonDistribution).map(([reason, count], index) => (
              <p key={reason} className="text-xs text-slate-200" data-testid={`admin-production-gate-override-analytics-reason-${index}`}>{reason}: {count}</p>
            ))}
            {Object.keys(reasonDistribution).length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-override-analytics-reason-empty">Reason dağılımı için override kaydı bekleniyor.</p>}
          </div>

          <div className="mt-3 space-y-2" data-testid="admin-production-gate-override-analytics-top-checks-list">
            {(overrideAnalytics?.top_override_checks || []).map((item, index) => (
              <p key={`${item.check_key}-${index}`} className="text-xs text-slate-200" data-testid={`admin-production-gate-override-analytics-top-check-${index}`}>{item.check_key}: {item.count}</p>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="admin-production-gate-timeline-panel">
          <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-production-gate-timeline-header">
            <h2 className="text-base font-semibold text-white" data-testid="admin-production-gate-timeline-title">Incident Timeline</h2>
            <div className="flex flex-wrap gap-2 text-xs" data-testid="admin-production-gate-timeline-filters">
              {[
                { key: "checks", label: "checks" },
                { key: "overrides", label: "overrides" },
                { key: "mode", label: "mode" },
                { key: "deploy", label: "deploy" },
              ].map((filter) => (
                <label key={filter.key} className="flex items-center gap-1" data-testid={`admin-production-gate-timeline-filter-${filter.key}`}>
                  <input type="checkbox" checked={timelineFilter[filter.key]} onChange={(event) => setTimelineFilter((prev) => ({ ...prev, [filter.key]: event.target.checked }))} data-testid={`admin-production-gate-timeline-filter-toggle-${filter.key}`} />
                  {filter.label}
                </label>
              ))}
            </div>
          </div>

          <div className="mt-3 max-h-80 space-y-2 overflow-y-auto" data-testid="admin-production-gate-timeline-items-list">
            {filteredTimelineItems.map((item, index) => (
              <div key={`${item.timestamp}-${index}`} className="rounded border border-slate-700 bg-slate-950 p-2 text-xs" data-testid={`admin-production-gate-timeline-item-${index}`}>
                <p className="text-white" data-testid={`admin-production-gate-timeline-item-title-${index}`}>
                  {item.category === "checks" ? "🧪" : item.category === "overrides" ? "🛡️" : item.category === "mode" ? "🔁" : "🚀"} {item.title}
                </p>
                <p data-testid={`admin-production-gate-timeline-item-category-${index}`}>category: {item.category}</p>
                <p data-testid={`admin-production-gate-timeline-item-audit-id-${index}`}>audit_id: {item.audit_id || "-"}</p>
                <p data-testid={`admin-production-gate-timeline-item-request-id-${index}`}>request_id: {item.request_id || "-"}</p>
                <p data-testid={`admin-production-gate-timeline-item-timestamp-${index}`}>timestamp: {item.timestamp}</p>
              </div>
            ))}
            {filteredTimelineItems.length === 0 && <p className="text-xs text-slate-400" data-testid="admin-production-gate-timeline-empty">Seçili filtrelerde timeline kaydı yok.</p>}
          </div>
        </div>
      </div>

      <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
        <DialogContent data-testid="admin-production-gate-override-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-production-gate-override-modal-title">GO_WITH_OVERRIDE</DialogTitle>
            <DialogDescription data-testid="admin-production-gate-override-modal-description">Sadece super_admin, en fazla 30 dakika süreli override açabilir.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="admin-production-gate-override-modal-form">
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-override-reason-code-label">reason_code</label>
            <select className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={overrideReasonCode} onChange={(event) => setOverrideReasonCode(event.target.value)} data-testid="admin-production-gate-override-reason-code-select">
              <option value="INCIDENT_MITIGATION">INCIDENT_MITIGATION</option>
              <option value="THIRD_PARTY_DEGRADATION">THIRD_PARTY_DEGRADATION</option>
              <option value="HOTFIX_VALIDATED">HOTFIX_VALIDATED</option>
              <option value="MANUAL_RISK_ACCEPTANCE">MANUAL_RISK_ACCEPTANCE</option>
            </select>
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-override-reason-text-label">reason_text</label>
            <textarea className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" rows={3} value={overrideReasonText} onChange={(event) => setOverrideReasonText(event.target.value)} data-testid="admin-production-gate-override-reason-text-input" />
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-override-ttl-label">ttl_minutes</label>
            <input type="number" min={1} max={30} className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={overrideTtl} onChange={(event) => setOverrideTtl(event.target.value)} data-testid="admin-production-gate-override-ttl-input" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOverrideOpen(false)} data-testid="admin-production-gate-override-cancel-button">İptal</Button>
            <Button onClick={handleCreateOverride} disabled={actionLoading} data-testid="admin-production-gate-override-submit-button">Override Aç</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={modeModalOpen} onOpenChange={setModeModalOpen}>
        <DialogContent data-testid="admin-production-gate-mode-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-production-gate-mode-modal-title">Mode Change Confirmation</DialogTitle>
            <DialogDescription data-testid="admin-production-gate-mode-modal-description">SIM/TESTNET → LIVE geçişinde Gate hard-block aktifse işlem reddedilir.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="admin-production-gate-mode-modal-form">
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-mode-target-label">target_mode</label>
            <select className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={targetMode} onChange={(event) => { setTargetMode(event.target.value); setConfirmationPhrase(event.target.value === "LIVE" ? "SWITCH TO LIVE" : event.target.value === "TESTNET" ? "SWITCH TO TESTNET" : event.target.value === "SIM" ? "SWITCH TO SIM" : event.target.value === "PAPER" ? "SWITCH TO PAPER" : "SWITCH TO MOCK"); }} data-testid="admin-production-gate-mode-target-select">
              <option value="LIVE">LIVE</option>
              <option value="TESTNET">TESTNET</option>
              <option value="SIM">SIM</option>
              <option value="PAPER">PAPER (legacy)</option>
              <option value="MOCK">MOCK (legacy)</option>
            </select>
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-mode-reason-label">reason_text</label>
            <textarea className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" rows={3} value={modeReason} onChange={(event) => setModeReason(event.target.value)} data-testid="admin-production-gate-mode-reason-input" />
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-mode-confirmation-label">confirmation_phrase ({expectedPhrase})</label>
            <input className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={confirmationPhrase} onChange={(event) => setConfirmationPhrase(event.target.value)} data-testid="admin-production-gate-mode-confirmation-input" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModeModalOpen(false)} data-testid="admin-production-gate-mode-cancel-button">İptal</Button>
            <Button onClick={handleModeTransition} disabled={actionLoading} data-testid="admin-production-gate-mode-submit-button">Geçişi Uygula</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
};
