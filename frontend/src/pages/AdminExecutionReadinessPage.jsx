import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
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
  const [safetyGate, setSafetyGate] = useState(null);
  const [intentLifecycle, setIntentLifecycle] = useState(null);
  const [runtimeQuarantine, setRuntimeQuarantine] = useState(null);
  const [reconciliationSummary, setReconciliationSummary] = useState(null);
  const [gateTrend, setGateTrend] = useState(null);
  const [interventionTrail, setInterventionTrail] = useState(null);
  const [acceptanceLatest, setAcceptanceLatest] = useState(null);
  const [gateExplain, setGateExplain] = useState(null);
  const [analyticsWindow, setAnalyticsWindow] = useState("7d");
  const [analyticsGateFailures, setAnalyticsGateFailures] = useState(null);
  const [analyticsBlockers, setAnalyticsBlockers] = useState(null);
  const [analyticsRecovery, setAnalyticsRecovery] = useState(null);
  const [anomalySeverityFilter, setAnomalySeverityFilter] = useState("ALL");
  const [anomalyTypeFilter, setAnomalyTypeFilter] = useState("ALL");
  const [anomalies, setAnomalies] = useState(null);
  const [dryRunSymbol, setDryRunSymbol] = useState("BTCUSDT");
  const [dryRunQty, setDryRunQty] = useState("0.001");
  const [dryRunSide, setDryRunSide] = useState("BUY");
  const [dryRunResult, setDryRunResult] = useState(null);
  const [shadowResult, setShadowResult] = useState(null);
  const [p1PanelError, setP1PanelError] = useState("");
  const [selectedAnomalyIntentIds, setSelectedAnomalyIntentIds] = useState([]);
  const [quickActionModal, setQuickActionModal] = useState({ open: false, action: "", intentIds: [] });
  const [loading, setLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const previousFailCountRef = useRef(0);
  const loadInFlightRef = useRef(false);
  const loadRequestRef = useRef(0);
  const hasLoadedRef = useRef(false);

  const expectedPhrase = useMemo(() => {
    if (targetMode === "SIM") return "SWITCH TO SIM";
    if (targetMode === "PAPER") return "SWITCH TO PAPER";
    if (targetMode === "MOCK") return "SWITCH TO MOCK";
    return "SWITCH TO LIVE";
  }, [targetMode]);

  const deployBlocked = !gate?.deploy_allowed;

  const load = useCallback(async (refreshChecks = false, showToastOnError = true) => {
    if (loadInFlightRef.current) {
      return;
    }
    loadInFlightRef.current = true;
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;

    if (!hasLoadedRef.current) {
      setLoading(true);
    } else {
      setIsRefreshing(true);
    }
    setP1PanelError("");

    try {
      const anomalyParams = new URLSearchParams({ window: analyticsWindow });
      if (anomalySeverityFilter !== "ALL") {
        anomalyParams.append("severity", anomalySeverityFilter);
      }
      if (anomalyTypeFilter !== "ALL") {
        anomalyParams.append("type", anomalyTypeFilter);
      }

      const settled = await Promise.allSettled([
        apiClient.get(`/phase4/admin/production-gate?refresh_checks=${refreshChecks ? "true" : "false"}`),
        apiClient.get("/admin/execution-readiness"),
        apiClient.get("/phase4/admin/production-gate/ops-overview"),
        apiClient.get("/phase4/admin/production-gate/checks/history?limit=300"),
        apiClient.get("/phase4/admin/production-gate/checks/compare?limit=300"),
        apiClient.get("/phase4/admin/production-gate/override-analytics"),
        apiClient.get("/phase4/admin/production-gate/timeline?limit=400"),
        apiClient.get(`/execution-safety/gate?force_refresh=${refreshChecks ? "true" : "false"}`),
        apiClient.get("/execution-safety/intents?limit=120&auto_quarantine_stuck=true"),
        apiClient.get("/execution-safety/quarantine?limit=200"),
        apiClient.get("/execution-safety/recovery/reconciliation-summary?limit=600"),
        apiClient.get("/execution-safety/recovery/gate-trends?days=14"),
        apiClient.get("/execution-safety/recovery/intervention-audit?limit=120"),
        Promise.resolve({ data: null }),
        apiClient.get(`/execution-safety/gate/explain?force_refresh=${refreshChecks ? "true" : "false"}&include_trend=true&window=${analyticsWindow}`),
        apiClient.get(`/execution-safety/analytics/gate-failures?window=${analyticsWindow}`),
        apiClient.get(`/execution-safety/analytics/blockers?window=${analyticsWindow}`),
        apiClient.get(`/execution-safety/analytics/recovery?window=${analyticsWindow}`),
        apiClient.get(`/execution-safety/anomalies/false-decisions?${anomalyParams.toString()}`),
      ]);

      if (requestId !== loadRequestRef.current) {
        return;
      }

      const getData = (index) => (settled[index]?.status === "fulfilled" ? settled[index].value?.data : undefined);
      const gateData = getData(0);
      const readinessData = getData(1);
      const opsData = getData(2);
      const historyData = getData(3);
      const comparePayload = getData(4);
      const analyticsPayload = getData(5);
      const timelinePayload = getData(6);
      const safetyGatePayload = getData(7);
      const intentLifecyclePayload = getData(8);
      const quarantinePayload = getData(9);
      const reconciliationPayload = getData(10);
      const trendPayload = getData(11);
      const interventionPayload = getData(12);
      const acceptanceLatestPayload = getData(13);
      const explainPayload = getData(14);
      const analyticsGatePayload = getData(15);
      const analyticsBlockersPayload = getData(16);
      const analyticsRecoveryPayload = getData(17);
      const anomaliesPayload = getData(18);

      if (gateData !== undefined) setGate(gateData);
      if (readinessData !== undefined) setReadiness(readinessData);
      if (opsData !== undefined) setOps(opsData);
      if (historyData !== undefined) setCheckHistory(historyData);
      if (comparePayload !== undefined) setCompareData(comparePayload);
      if (analyticsPayload !== undefined) setOverrideAnalytics(analyticsPayload);
      if (timelinePayload !== undefined) setTimelineData(timelinePayload);
      if (safetyGatePayload !== undefined) setSafetyGate(safetyGatePayload || null);
      if (intentLifecyclePayload !== undefined) setIntentLifecycle(intentLifecyclePayload || null);
      if (quarantinePayload !== undefined) setRuntimeQuarantine(quarantinePayload || null);
      if (reconciliationPayload !== undefined) setReconciliationSummary(reconciliationPayload || null);
      if (trendPayload !== undefined) setGateTrend(trendPayload || null);
      if (interventionPayload !== undefined) setInterventionTrail(interventionPayload || null);
      if (acceptanceLatestPayload !== undefined) setAcceptanceLatest(acceptanceLatestPayload?.latest || null);
      if (explainPayload !== undefined) setGateExplain(explainPayload || null);
      if (analyticsGatePayload !== undefined) setAnalyticsGateFailures(analyticsGatePayload || null);
      if (analyticsBlockersPayload !== undefined) setAnalyticsBlockers(analyticsBlockersPayload || null);
      if (analyticsRecoveryPayload !== undefined) setAnalyticsRecovery(analyticsRecoveryPayload || null);
      if (anomaliesPayload !== undefined) setAnomalies(anomaliesPayload || null);

      const refreshedIntentIds = new Set((anomaliesPayload?.items || []).map((item) => item.intent_id).filter(Boolean));
      setSelectedAnomalyIntentIds((prev) => prev.filter((id) => refreshedIntentIds.has(id)));

      const flappingConfig = historyData?.flapping_config || {};
      if (flappingConfig.window_sec) setFlappingWindowSec(Number(flappingConfig.window_sec));
      if (flappingConfig.threshold) setFlappingThreshold(Number(flappingConfig.threshold));

      const nextFailCount = Number(opsData?.active_fail_count || previousFailCountRef.current || 0);
      if (nextFailCount > previousFailCountRef.current) {
        setNewFailPulse(true);
      }
      previousFailCountRef.current = nextFailCount;

      const errors = settled.filter((item) => item.status === "rejected");
      if (errors.length > 0 && showToastOnError) {
        toast.error(`${errors.length} panel verisi güncellenemedi, kalan veriler korundu`);
      }
      if (!gateData && !readinessData && errors.length > 0) {
        const firstDetail = errors[0]?.reason?.response?.data?.detail;
        const message = typeof firstDetail === "string" ? firstDetail : "Production Gate verisi alınamadı";
        setP1PanelError(message);
      }
      hasLoadedRef.current = true;
    } catch (error) {
      const message = error?.response?.data?.detail || "Production Gate verisi alınamadı";
      setP1PanelError(message);
      if (showToastOnError) {
        toast.error(message);
      }
    } finally {
      if (requestId === loadRequestRef.current) {
        setLoading(false);
        setIsRefreshing(false);
      }
      loadInFlightRef.current = false;
    }
  }, [analyticsWindow, anomalySeverityFilter, anomalyTypeFilter]);

  useEffect(() => {
    load(true, true);
  }, [load]);

  useEffect(() => {
    if (!autoRefreshEnabled) return undefined;
    const timer = setInterval(() => {
      load(false, false);
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

  const handleSafetyQuarantineAction = useCallback(
    async (eventId, action) => {
      await runAction(async () => {
        await apiClient.post(`/execution-safety/quarantine/${eventId}/${action}`);
      }, `Quarantine ${action} tamamlandı`);
    },
    [runAction]
  );

  const handleBatchRecoverStuckIntents = useCallback(
    async (action) => {
      await runAction(async () => {
        await apiClient.post(`/execution-safety/recovery/batch?action=${action}&limit=50`);
      }, `Batch ${action} tamamlandı`);
    },
    [runAction]
  );

  const handleRunAcceptance = useCallback(
    async () => {
      toast.info("Acceptance run devre dışı: platform artık yalnızca live akışı kullanıyor.");
    },
    []
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
    await runAction(async () => {
      const { data } = await apiClient.get("/phase4/admin/production-gate/system/cross-check");
      setCrossCheckResult(data);
    }, "Cross-check tutarlı");
  }, [runAction]);

  const crossCheckSummaryText = useMemo(() => {
    if (!crossCheckResult || typeof crossCheckResult !== "object") {
      return "-";
    }
    const isConsistent = Boolean(crossCheckResult.is_consistent);
    const mismatchCount = Array.isArray(crossCheckResult.mismatches) ? crossCheckResult.mismatches.length : 0;
    const sourceCount = Array.isArray(crossCheckResult.comparison_sources) ? crossCheckResult.comparison_sources.length : 0;
    return `${isConsistent ? "PASS" : "FAIL"} · mismatches=${mismatchCount} · sources=${sourceCount}`;
  }, [crossCheckResult]);

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

  const handleIncidentPackageExport = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/execution-safety/artifacts/incident-export?include_events=false");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `execution-incident-package-${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("Incident paket export hazır");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident paket export alınamadı");
    }
  }, []);

  const handleAnomalyFilterApply = useCallback(async () => {
    try {
      const params = new URLSearchParams({ window: analyticsWindow });
      if (anomalySeverityFilter !== "ALL") {
        params.append("severity", anomalySeverityFilter);
      }
      if (anomalyTypeFilter !== "ALL") {
        params.append("type", anomalyTypeFilter);
      }
      const { data } = await apiClient.get(`/execution-safety/anomalies/false-decisions?${params.toString()}`);
      setAnomalies(data || null);
      const visibleIntentIds = new Set((data?.items || []).map((item) => item.intent_id).filter(Boolean));
      setSelectedAnomalyIntentIds((prev) => prev.filter((intentId) => visibleIntentIds.has(intentId)));
      toast.success("Anomaly filtreleri uygulandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Anomaly filtreleri uygulanamadı");
    }
  }, [analyticsWindow, anomalySeverityFilter, anomalyTypeFilter]);

  const handleAnalyticsCsvExport = useCallback(
    async (dataset) => {
      const endpointMap = {
        gate: "/execution-safety/analytics/gate-failures",
        blockers: "/execution-safety/analytics/blockers",
        recovery: "/execution-safety/analytics/recovery",
      };
      const targetEndpoint = endpointMap[dataset];
      if (!targetEndpoint) {
        toast.error("Geçersiz analytics export tipi");
        return;
      }

      try {
        const params = new URLSearchParams({
          window: analyticsWindow,
          format: "csv",
          page: "1",
          page_size: "2000",
        });
        const response = await apiClient.get(`${targetEndpoint}?${params.toString()}`, { responseType: "blob" });
        const blob = new Blob([response.data], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `execution-safety-${dataset}-${analyticsWindow}-${Date.now()}.csv`;
        link.click();
        URL.revokeObjectURL(url);
        toast.success("CSV export hazır");
      } catch (error) {
        toast.error(error?.response?.data?.detail || "CSV export alınamadı");
      }
    },
    [analyticsWindow]
  );

  const resolveAnomalySelection = useCallback(
    (intentIds = []) => {
      const provided = Array.isArray(intentIds) ? intentIds.filter(Boolean) : [];
      if (provided.length) {
        return Array.from(new Set(provided));
      }
      return Array.from(new Set(selectedAnomalyIntentIds.filter(Boolean)));
    },
    [selectedAnomalyIntentIds]
  );

  const anomaliesList = useMemo(() => anomalies?.items || [], [anomalies?.items]);
  const anomalyTypeOptions = useMemo(
    () => ["ALL", "FALSE_READY", "FALSE_ALLOW", "CORRELATION_BREACH"],
    []
  );
  const selectableAnomalyIntentIds = useMemo(
    () => anomaliesList.map((item) => item.intent_id).filter(Boolean),
    [anomaliesList]
  );
  const allVisibleAnomaliesSelected = useMemo(() => {
    if (!selectableAnomalyIntentIds.length) return false;
    return selectableAnomalyIntentIds.every((intentId) => selectedAnomalyIntentIds.includes(intentId));
  }, [selectableAnomalyIntentIds, selectedAnomalyIntentIds]);

  const executeAnomalyQuickAction = useCallback(
    async (actionKey, rawIntentIds = []) => {
      const endpointMap = {
        retry: "/execution-safety/recovery/bulk-retry",
        reconcile: "/execution-safety/recovery/bulk-reconcile",
        cancel: "/execution-safety/recovery/bulk-cancel",
        escalate: "/execution-safety/recovery/bulk-move-to-quarantine",
      };
      const endpoint = endpointMap[actionKey];
      if (!endpoint) {
        toast.error("Geçersiz quick action");
        return;
      }

      const intentIds = resolveAnomalySelection(rawIntentIds);
      if (!intentIds.length) {
        toast.error("Quick action için intent seçin");
        return;
      }

      const matchedItems = anomaliesList.filter((item) => intentIds.includes(item.intent_id));
      const executableIds = matchedItems
        .filter((item) => (item.allowed_actions || []).includes(actionKey))
        .map((item) => item.intent_id)
        .filter(Boolean);
      const blockedCount = matchedItems.length - executableIds.length;
      if (blockedCount > 0) {
        toast.warning(`${blockedCount} intent için ${actionKey.toUpperCase()} guard nedeniyle bloklandı.`);
      }
      if (!executableIds.length) {
        toast.error("Seçili intentler için bu aksiyon şu an izinli değil.");
        return;
      }

      const hasHighSeverity = matchedItems.some((item) => String(item.severity_level || item.severity || "").toUpperCase() === "HIGH");
      if (hasHighSeverity && !quickActionModal.open) {
        setQuickActionModal({ open: true, action: actionKey, intentIds: executableIds });
        return;
      }
      if (!hasHighSeverity) {
        toast.info("MEDIUM/LOW aksiyon direkt çalışır; kayıt audit trail'e yazılır.");
      }

      await runAction(async () => {
        const payload = {
          selection_mode: "explicit_ids",
          intent_ids: executableIds,
          limit: Math.max(executableIds.length, 1),
          reason: `anomaly_quick_action_${actionKey}`,
          requested_by: "admin-ui",
        };
        await apiClient.post(endpoint, payload);
        setQuickActionModal({ open: false, action: "", intentIds: [] });
        setSelectedAnomalyIntentIds([]);
      }, `${actionKey.toUpperCase()} aksiyonu uygulandı`);
    },
    [anomaliesList, quickActionModal.open, resolveAnomalySelection, runAction]
  );

  const handleAnomalyRowSelect = useCallback((intentId, checked) => {
    if (!intentId) return;
    setSelectedAnomalyIntentIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(intentId);
      else next.delete(intentId);
      return Array.from(next);
    });
  }, []);

  const handleAnomalySelectAll = useCallback(
    (checked) => {
      if (!checked) {
        setSelectedAnomalyIntentIds([]);
        return;
      }
      const visibleIds = anomaliesList.map((item) => item.intent_id).filter(Boolean);
      setSelectedAnomalyIntentIds(Array.from(new Set(visibleIds)));
    },
    [anomaliesList]
  );

  const handleExecutionSimulation = useCallback(
    async (mode) => {
      const normalizedQty = Number(dryRunQty);
      if (!Number.isFinite(normalizedQty) || normalizedQty <= 0) {
        toast.error("Qty değeri 0'dan büyük sayı olmalı");
        return;
      }

      const symbol = String(dryRunSymbol || "").trim().toUpperCase() || "BTCUSDT";
      const side = String(dryRunSide || "BUY").toUpperCase();
      const endpoint = mode === "shadow" ? "/execution-safety/execution/shadow" : "/execution-safety/execution/dry-run";
      const params = new URLSearchParams({
        symbol,
        qty: String(normalizedQty),
        side,
      });

      await runAction(async () => {
        const { data } = await apiClient.post(`${endpoint}?${params.toString()}`);
        if (mode === "shadow") {
          setShadowResult(data || null);
        } else {
          setDryRunResult(data || null);
        }
        return data;
      }, mode === "shadow" ? "Shadow execution tamamlandı" : "Dry-run execution tamamlandı");
    },
    [dryRunQty, dryRunSide, dryRunSymbol, runAction]
  );

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
  const topStuckIntents = useMemo(
    () => (intentLifecycle?.items || []).filter((item) => item.is_stuck).slice(0, 6),
    [intentLifecycle?.items]
  );
  const topQuarantineItems = useMemo(() => (runtimeQuarantine?.items || []).slice(0, 6), [runtimeQuarantine?.items]);

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
            <Button variant="outline" onClick={handleIncidentPackageExport} data-testid="admin-production-gate-export-incident-package-button">Incident Paketi Export</Button>
            <Button variant="outline" onClick={handleRunAcceptance} data-testid="admin-production-gate-run-live-acceptance-button">Acceptance Run (Disabled)</Button>
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
            <p data-testid="admin-production-gate-cross-check-result">cross_check_result: {crossCheckSummaryText}</p>
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

      <div className="grid gap-4 lg:grid-cols-3" data-testid="execution-safety-core-overview-grid">
        <article className="rounded-lg border border-emerald-700/40 bg-slate-900 p-4" data-testid="execution-safety-gate-card">
          <div className="flex items-center justify-between gap-2" data-testid="execution-safety-gate-card-header">
            <h2 className="text-base font-semibold text-emerald-200" data-testid="execution-safety-gate-title">Execution Safety Gate (P0)</h2>
            <Button
              variant="outline"
              onClick={() => load(true)}
              disabled={loading || actionLoading}
              data-testid="execution-safety-gate-refresh-button"
            >
              Force Refresh
            </Button>
          </div>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-gate-state-value">
            gate_state: {safetyGate?.state || safetyGate?.gate_state || "-"}
          </p>
          <p className="mt-1 text-xs text-slate-300" data-testid="execution-safety-gate-readiness-score-value">
            readiness_score: {safetyGate?.score ?? safetyGate?.readiness_score ?? "-"}
          </p>
          <p className="mt-1 text-xs text-slate-300" data-testid="execution-safety-gate-execution-allowed-value">
            execution_allowed: {safetyGate?.execution_authority === "ALLOW" || safetyGate?.execution_allowed ? "true" : "false"}
          </p>
          <p className="mt-1 text-xs text-slate-300" data-testid="execution-safety-gate-bybit-smoke-status">
            bybit_order_smoke: {(safetyGate?.legacy_gate?.bybit_order_smoke?.status || safetyGate?.bybit_order_smoke?.status || "-")} ({(safetyGate?.legacy_gate?.bybit_order_smoke?.reason_code || safetyGate?.bybit_order_smoke?.reason_code || "-")})
          </p>
          <div className="mt-3 rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-safety-gate-hard-blockers-panel">
            <p className="text-xs font-semibold text-rose-200" data-testid="execution-safety-gate-hard-blockers-title">hard_blockers</p>
            {(safetyGate?.blockers || safetyGate?.hard_blockers || []).map((code, index) => (
              <p key={`${code}-${index}`} className="text-xs text-rose-100" data-testid={`execution-safety-gate-hard-blocker-${index}`}>• {code}</p>
            ))}
            {(safetyGate?.blockers || safetyGate?.hard_blockers || []).length === 0 && (
              <p className="text-xs text-slate-400" data-testid="execution-safety-gate-hard-blockers-empty">-</p>
            )}
          </div>
          <div className="mt-3 rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-safety-gate-artifact-panel">
            <p className="text-xs text-slate-200" data-testid="execution-safety-gate-artifact-status">artifact_status: {(safetyGate?.legacy_gate?.artifact?.status || safetyGate?.artifact?.status || "-")}</p>
            <p className="text-xs text-slate-400" data-testid="execution-safety-gate-artifact-local-path">local_path: {(safetyGate?.legacy_gate?.artifact?.local_path || safetyGate?.artifact?.local_path || "-")}</p>
            <p className="text-xs text-slate-400" data-testid="execution-safety-gate-artifact-s3-uri">s3_uri: {(safetyGate?.legacy_gate?.artifact?.s3_uri || safetyGate?.artifact?.s3_uri || "-")}</p>
          </div>
        </article>

        <article className="rounded-lg border border-cyan-700/40 bg-slate-900 p-4" data-testid="execution-safety-intent-lifecycle-card">
          <h2 className="text-base font-semibold text-cyan-200" data-testid="execution-safety-intent-lifecycle-title">Intent State Machine</h2>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-intent-total">total: {intentLifecycle?.total ?? 0}</p>
          <p className="mt-1 text-xs text-slate-300" data-testid="execution-safety-intent-stuck-count">stuck_count: {intentLifecycle?.stuck_count ?? 0}</p>
          <div className="mt-3 rounded border border-slate-700 bg-slate-950 p-2" data-testid="execution-safety-intent-state-counts-panel">
            {Object.entries(intentLifecycle?.state_counts || {}).map(([state, count]) => (
              <p key={state} className="text-xs text-slate-300" data-testid={`execution-safety-intent-state-count-${state.toLowerCase()}`}>
                {state}: {count}
              </p>
            ))}
            {Object.keys(intentLifecycle?.state_counts || {}).length === 0 && (
              <p className="text-xs text-slate-400" data-testid="execution-safety-intent-state-counts-empty">-</p>
            )}
          </div>
          <div className="mt-3 space-y-2" data-testid="execution-safety-intent-stuck-list">
            {topStuckIntents.map((intentItem, index) => (
              <div key={intentItem.intent_id} className="rounded border border-amber-700/40 bg-amber-950/20 p-2" data-testid={`execution-safety-intent-stuck-item-${index}`}>
                <p className="text-xs text-amber-100" data-testid={`execution-safety-intent-stuck-id-${index}`}>intent_id: {intentItem.intent_id}</p>
                <p className="text-xs text-amber-100" data-testid={`execution-safety-intent-stuck-state-${index}`}>state: {intentItem.state}</p>
                <p className="text-xs text-amber-100" data-testid={`execution-safety-intent-stuck-age-${index}`}>age_seconds: {intentItem.age_seconds}</p>
              </div>
            ))}
            {topStuckIntents.length === 0 && (
              <p className="text-xs text-slate-400" data-testid="execution-safety-intent-stuck-empty">stuck intent yok</p>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="execution-safety-intent-batch-actions">
            <Button size="sm" className="bg-cyan-500 text-black hover:bg-cyan-600" onClick={() => handleBatchRecoverStuckIntents("replay")} data-testid="execution-safety-intent-batch-replay-button">
              Batch Replay
            </Button>
            <Button size="sm" variant="outline" className="border-slate-500 text-slate-200" onClick={() => handleBatchRecoverStuckIntents("dismiss")} data-testid="execution-safety-intent-batch-dismiss-button">
              Batch Dismiss
            </Button>
            <Button size="sm" variant="outline" className="border-red-500 text-red-300" onClick={() => handleBatchRecoverStuckIntents("mark_failed")} data-testid="execution-safety-intent-batch-mark-failed-button">
              Batch Mark Failed
            </Button>
          </div>
        </article>

        <article className="rounded-lg border border-red-700/40 bg-slate-900 p-4" data-testid="execution-safety-quarantine-card">
          <h2 className="text-base font-semibold text-red-200" data-testid="execution-safety-quarantine-title">Runtime Quarantine / DLQ</h2>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-quarantine-total">total: {runtimeQuarantine?.total ?? 0}</p>
          <p className="mt-1 text-xs text-slate-300" data-testid="execution-safety-quarantine-redis-state">
            redis_available: {runtimeQuarantine?.queue_metrics?.redis_available ? "true" : "false"}
          </p>
          <p className="mt-1 text-xs text-slate-300" data-testid="execution-safety-quarantine-queue-size">
            runtime_quarantine_queue: {runtimeQuarantine?.queue_metrics?.runtime_quarantine_queue ?? 0}
          </p>
          <div className="mt-3 space-y-2" data-testid="execution-safety-quarantine-items-list">
            {topQuarantineItems.map((row, index) => (
              <div key={row.quarantine_id || row.id} className="rounded border border-slate-700 bg-slate-950 p-2" data-testid={`execution-safety-quarantine-item-${index}`}>
                <p className="text-xs text-slate-200" data-testid={`execution-safety-quarantine-item-entity-${index}`}>{row.entity_type} / {row.event_type}</p>
                <p className="text-xs text-slate-300" data-testid={`execution-safety-quarantine-item-status-${index}`}>status: {row.status}</p>
                <p className="text-xs text-slate-300" data-testid={`execution-safety-quarantine-item-retry-${index}`}>retry: {row.retry_count}/{row.max_retry}</p>
                <div className="mt-2 flex flex-wrap gap-2" data-testid={`execution-safety-quarantine-item-actions-${index}`}>
                  <Button size="sm" className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={() => handleSafetyQuarantineAction(row.quarantine_id || row.id, "replay")} data-testid={`execution-safety-quarantine-item-replay-${index}`}>
                    Replay
                  </Button>
                  <Button size="sm" variant="outline" className="border-slate-500 text-slate-200" onClick={() => handleSafetyQuarantineAction(row.quarantine_id || row.id, "dismiss")} data-testid={`execution-safety-quarantine-item-dismiss-${index}`}>
                    Dismiss
                  </Button>
                  <Button size="sm" variant="outline" className="border-red-500 text-red-300" onClick={() => handleSafetyQuarantineAction(row.quarantine_id || row.id, "mark_failed")} data-testid={`execution-safety-quarantine-item-mark-failed-${index}`}>
                    Mark Failed
                  </Button>
                </div>
              </div>
            ))}
            {topQuarantineItems.length === 0 && (
              <p className="text-xs text-slate-400" data-testid="execution-safety-quarantine-items-empty">quarantine kaydı yok</p>
            )}
          </div>
        </article>
      </div>

      <div className="grid gap-4 lg:grid-cols-4" data-testid="execution-safety-p1-analytics-grid">
        <article className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="execution-safety-reconciliation-card">
          <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-reconciliation-title">Reconciliation Özeti</h3>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-reconciliation-duplicate-count">
            duplicate_external_order_count: {reconciliationSummary?.duplicate_external_order_count ?? 0}
          </p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-reconciliation-missing-external-count">
            filled_without_external_order_count: {reconciliationSummary?.filled_without_external_order_count ?? 0}
          </p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-reconciliation-stuck-intent-count">
            stuck_intent_count: {reconciliationSummary?.stuck_intent_count ?? 0}
          </p>
        </article>

        <article className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="execution-safety-gate-trend-card">
          <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-gate-trend-title">Gate Failure Trend (14g)</h3>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-gate-trend-days">days: {gateTrend?.days ?? "-"}</p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-gate-trend-points">points: {(gateTrend?.items || []).length}</p>
          {(gateTrend?.items || []).slice(-3).map((item, idx) => (
            <p key={`${item.date}-${idx}`} className="text-xs text-slate-400" data-testid={`execution-safety-gate-trend-item-${idx}`}>
              {item.date}: total={item.total} blocked={item?.states?.BLOCKED || 0}
            </p>
          ))}
        </article>

        <article className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="execution-safety-intervention-audit-card">
          <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-intervention-audit-title">Manual Intervention Trail</h3>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-intervention-audit-total">total: {interventionTrail?.total ?? 0}</p>
          {(interventionTrail?.items || []).slice(0, 3).map((item, idx) => (
            <p key={`${item.id}-${idx}`} className="text-xs text-slate-400" data-testid={`execution-safety-intervention-audit-item-${idx}`}>
              {item.action} / {item.actor_role} / {item.entity_id}
            </p>
          ))}
        </article>

        <article className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="execution-safety-acceptance-card">
          <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-acceptance-title">Acceptance (Legacy Disabled)</h3>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-acceptance-latest-id">latest_run: {acceptanceLatest?.payload?.acceptance_run_id || acceptanceLatest?.artifact_id || "-"}</p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-acceptance-latest-proof-type">proof_type: {acceptanceLatest?.payload?.proof_type || "-"}</p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-acceptance-latest-created-at">created_at: {acceptanceLatest?.created_at || "-"}</p>
        </article>

        <article className="rounded-lg border border-slate-700 bg-slate-900 p-4" data-testid="execution-safety-gate-explain-card">
          <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-gate-explain-title">Gate Explainability</h3>
          <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-gate-explain-score">score: {gateExplain?.score ?? "-"}</p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-gate-explain-state">state: {gateExplain?.state || "-"}</p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-gate-explain-confidence">confidence_band: {gateExplain?.confidence_band || "-"}</p>
          <p className="text-xs text-slate-300" data-testid="execution-safety-gate-explain-override">override_reason: {gateExplain?.override_reason || "-"}</p>
          <div className="mt-2 space-y-1" data-testid="execution-safety-gate-explain-components-list">
            {(gateExplain?.components || []).map((item, idx) => (
              <p key={`${item.name}-${idx}`} className="text-xs text-slate-400" data-testid={`execution-safety-gate-explain-component-${idx}`}>
                {item.name}: weight={item.weight} score={item.score}
              </p>
            ))}
          </div>
        </article>
      </div>

      <div className="space-y-4 rounded-lg border border-indigo-700/40 bg-slate-900 p-4" data-testid="execution-safety-p1-sprint2-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-safety-p1-sprint2-header">
          <div data-testid="execution-safety-p1-sprint2-header-left">
            <h2 className="text-base font-semibold text-indigo-200" data-testid="execution-safety-p1-sprint2-title">P1 Sprint-2: Analytics & Anomaly Ops</h2>
            <p className="text-xs text-slate-300" data-testid="execution-safety-p1-sprint2-subtitle">7g/30g analitik, false decision anomaly ve dry-run/shadow operasyon paneli.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="execution-safety-p1-sprint2-header-controls">
            <label className="text-xs text-slate-300" data-testid="execution-safety-p1-window-label">window</label>
            <select
              value={analyticsWindow}
              onChange={(event) => setAnalyticsWindow(event.target.value)}
              className="rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-white"
              data-testid="execution-safety-p1-window-select"
            >
              <option value="7d">7d</option>
              <option value="30d">30d</option>
            </select>
            <Button
              variant="outline"
              onClick={() => load(false)}
              disabled={loading || actionLoading}
              data-testid="execution-safety-p1-refresh-button"
            >
              Analytics Yenile
            </Button>
            <Button
              variant="outline"
              onClick={() => handleAnalyticsCsvExport("gate")}
              disabled={loading || actionLoading}
              data-testid="execution-safety-p1-export-gate-csv-button"
            >
              Gate CSV
            </Button>
            <Button
              variant="outline"
              onClick={() => handleAnalyticsCsvExport("blockers")}
              disabled={loading || actionLoading}
              data-testid="execution-safety-p1-export-blockers-csv-button"
            >
              Blockers CSV
            </Button>
            <Button
              variant="outline"
              onClick={() => handleAnalyticsCsvExport("recovery")}
              disabled={loading || actionLoading}
              data-testid="execution-safety-p1-export-recovery-csv-button"
            >
              Recovery CSV
            </Button>
          </div>
        </div>

        {loading && !analyticsGateFailures && !analyticsBlockers && !analyticsRecovery && (
          <div className="grid gap-4 lg:grid-cols-3" data-testid="execution-safety-p1-loading-skeleton-grid">
            <Skeleton className="h-28 w-full bg-slate-800" data-testid="execution-safety-p1-loading-skeleton-item-0" />
            <Skeleton className="h-28 w-full bg-slate-800" data-testid="execution-safety-p1-loading-skeleton-item-1" />
            <Skeleton className="h-28 w-full bg-slate-800" data-testid="execution-safety-p1-loading-skeleton-item-2" />
          </div>
        )}

        {!!p1PanelError && (
          <div className="rounded border border-red-700/50 bg-red-950/20 p-3" data-testid="execution-safety-p1-error-state">
            <p className="text-xs text-red-200" data-testid="execution-safety-p1-error-message">{p1PanelError}</p>
            <Button
              variant="outline"
              className="mt-2"
              onClick={() => load(true)}
              disabled={loading || actionLoading}
              data-testid="execution-safety-p1-error-retry-button"
            >
              Yeniden Dene
            </Button>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-3" data-testid="execution-safety-p1-metrics-grid">
          <article className="rounded-lg border border-slate-700 bg-slate-950 p-3" data-testid="execution-safety-p1-gate-failure-card">
            <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-p1-gate-failure-title">Gate Failure Analytics</h3>
            <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-p1-gate-failure-total">total_evaluations: {analyticsGateFailures?.total_evaluations ?? 0}</p>
            <p className="text-xs text-slate-300" data-testid="execution-safety-p1-gate-failure-blocked">blocked_count: {analyticsGateFailures?.blocked_count ?? 0}</p>
            <p className="text-xs text-slate-300" data-testid="execution-safety-p1-gate-failure-degraded">degraded_count: {analyticsGateFailures?.degraded_count ?? 0}</p>
            <p className="text-xs text-slate-300" data-testid="execution-safety-p1-gate-failure-ready">ready_count: {analyticsGateFailures?.ready_count ?? 0}</p>
            <p className="text-xs text-amber-200" data-testid="execution-safety-p1-gate-failure-rate">
              failure_rate: {((Number(analyticsGateFailures?.failure_rate || 0) || 0) * 100).toFixed(2)}%
            </p>
            <div className="mt-2 space-y-1" data-testid="execution-safety-p1-gate-failure-timeseries-list">
              {(analyticsGateFailures?.timeseries || []).slice(-5).map((item, index) => (
                <p key={`${item.date}-${index}`} className="text-xs text-slate-400" data-testid={`execution-safety-p1-gate-failure-timeseries-item-${index}`}>
                  {item.date}: blocked={item.blocked} / total={item.total}
                </p>
              ))}
              {(analyticsGateFailures?.timeseries || []).length === 0 && (
                <p className="text-xs text-slate-500" data-testid="execution-safety-p1-gate-failure-timeseries-empty">timeseries verisi yok</p>
              )}
            </div>
          </article>

          <article className="rounded-lg border border-slate-700 bg-slate-950 p-3" data-testid="execution-safety-p1-blockers-card">
            <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-p1-blockers-title">Top Blockers</h3>
            <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-p1-blockers-window">window: {analyticsBlockers?.window || analyticsWindow}</p>
            <div className="mt-2 space-y-1" data-testid="execution-safety-p1-blockers-list">
              {(analyticsBlockers?.top_blockers || []).slice(0, 8).map((item, index) => (
                <p key={`${item.code}-${index}`} className="text-xs text-slate-300" data-testid={`execution-safety-p1-blocker-item-${index}`}>
                  {item.code}: {item.count}
                </p>
              ))}
              {(analyticsBlockers?.top_blockers || []).length === 0 && (
                <p className="text-xs text-slate-500" data-testid="execution-safety-p1-blockers-empty">hard blocker verisi yok</p>
              )}
            </div>
            <p className="mt-2 text-xs text-slate-400" data-testid="execution-safety-p1-blockers-distribution-size">
              distribution_days: {(analyticsBlockers?.distribution || []).length}
            </p>
          </article>

          <article className="rounded-lg border border-slate-700 bg-slate-950 p-3" data-testid="execution-safety-p1-recovery-card">
            <h3 className="text-sm font-semibold text-slate-100" data-testid="execution-safety-p1-recovery-title">Recovery Analytics</h3>
            <p className="mt-2 text-xs text-slate-300" data-testid="execution-safety-p1-recovery-window">window: {analyticsRecovery?.window || analyticsWindow}</p>
            <p className="text-xs text-slate-300" data-testid="execution-safety-p1-recovery-retry-rate">
              retry_success_rate: {((Number(analyticsRecovery?.retry_success_rate || 0) || 0) * 100).toFixed(2)}%
            </p>
            <p className="text-xs text-slate-300" data-testid="execution-safety-p1-recovery-reconcile-rate">
              reconcile_success_rate: {((Number(analyticsRecovery?.reconcile_success_rate || 0) || 0) * 100).toFixed(2)}%
            </p>
            <p className="text-xs text-slate-300" data-testid="execution-safety-p1-recovery-quarantine-rate">
              quarantine_rate: {((Number(analyticsRecovery?.quarantine_rate || 0) || 0) * 100).toFixed(2)}%
            </p>
            <p className="text-xs text-emerald-300" data-testid="execution-safety-p1-recovery-avg-time">
              avg_recovery_time_sec: {analyticsRecovery?.avg_recovery_time_sec ?? 0}
            </p>
          </article>
        </div>

        <div className="grid gap-4 lg:grid-cols-2" data-testid="execution-safety-p1-anomaly-simulation-grid">
          <article className="rounded-lg border border-rose-700/40 bg-slate-950 p-3" data-testid="execution-safety-p1-anomaly-card">
            <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-safety-p1-anomaly-header">
              <h3 className="text-sm font-semibold text-rose-200" data-testid="execution-safety-p1-anomaly-title">False Decision Anomaly Detection</h3>
              <p className="text-xs text-rose-100" data-testid="execution-safety-p1-anomaly-total">total_anomalies: {anomalies?.total_anomalies ?? 0}</p>
            </div>
            <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="execution-safety-p1-anomaly-filter-grid">
              <div data-testid="execution-safety-p1-anomaly-severity-filter-wrapper">
                <label className="text-xs text-slate-300" data-testid="execution-safety-p1-anomaly-severity-filter-label">severity</label>
                <select
                  value={anomalySeverityFilter}
                  onChange={(event) => setAnomalySeverityFilter(event.target.value)}
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-white"
                  data-testid="execution-safety-p1-anomaly-severity-filter-select"
                >
                  <option value="ALL">ALL</option>
                  <option value="HIGH">HIGH</option>
                  <option value="MEDIUM">MEDIUM</option>
                </select>
              </div>
              <div data-testid="execution-safety-p1-anomaly-type-filter-wrapper">
                <label className="text-xs text-slate-300" data-testid="execution-safety-p1-anomaly-type-filter-label">type</label>
                <select
                  value={anomalyTypeFilter}
                  onChange={(event) => setAnomalyTypeFilter(event.target.value)}
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-white"
                  data-testid="execution-safety-p1-anomaly-type-filter-select"
                >
                  {anomalyTypeOptions.map((optionValue) => (
                    <option key={optionValue} value={optionValue}>{optionValue}</option>
                  ))}
                </select>
              </div>
              <div className="flex items-end" data-testid="execution-safety-p1-anomaly-filter-apply-wrapper">
                <Button
                  variant="outline"
                  onClick={handleAnomalyFilterApply}
                  disabled={loading || actionLoading}
                  className="w-full"
                  data-testid="execution-safety-p1-anomaly-filter-apply-button"
                >
                  Filtre Uygula
                </Button>
              </div>
            </div>
            <div className="mt-2 rounded border border-slate-700/70 bg-slate-900/80 p-2" data-testid="execution-safety-p1-anomaly-quick-actions-panel">
              <div className="flex flex-wrap items-center justify-between gap-2" data-testid="execution-safety-p1-anomaly-quick-actions-header">
                <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="execution-safety-p1-anomaly-select-all-wrapper">
                  <input
                    type="checkbox"
                    checked={allVisibleAnomaliesSelected}
                    onChange={(event) => handleAnomalySelectAll(event.target.checked)}
                    data-testid="execution-safety-p1-anomaly-select-all-checkbox"
                  />
                  Tümünü seç ({selectedAnomalyIntentIds.length})
                </label>
                <p className="text-[11px] text-slate-400" data-testid="execution-safety-p1-anomaly-high-modal-rule">HIGH aksiyonlarda onay modalı zorunlu.</p>
              </div>
              <div className="mt-2 flex flex-wrap gap-2" data-testid="execution-safety-p1-anomaly-quick-actions-buttons">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => executeAnomalyQuickAction("retry")}
                  disabled={actionLoading}
                  data-testid="execution-safety-p1-anomaly-quick-action-retry-button"
                >
                  Retry
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => executeAnomalyQuickAction("reconcile")}
                  disabled={actionLoading}
                  data-testid="execution-safety-p1-anomaly-quick-action-reconcile-button"
                >
                  Reconcile
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => executeAnomalyQuickAction("cancel")}
                  disabled={actionLoading}
                  data-testid="execution-safety-p1-anomaly-quick-action-cancel-button"
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => executeAnomalyQuickAction("escalate")}
                  disabled={actionLoading}
                  data-testid="execution-safety-p1-anomaly-quick-action-escalate-button"
                >
                  Escalate
                </Button>
              </div>
            </div>
            <div className="mt-3 max-h-64 space-y-2 overflow-y-auto" data-testid="execution-safety-p1-anomaly-items-list">
              {anomaliesList.slice(0, 20).map((item, index) => (
                <div
                  key={`${item.intent_id || "unknown"}-${index}`}
                  className={`rounded border p-2 ${String(item.severity_level || item.severity || "").toUpperCase() === "HIGH" ? "border-rose-500/70 bg-rose-950/30" : "border-rose-800/40 bg-rose-950/20"}`}
                  data-testid={`execution-safety-p1-anomaly-item-${index}`}
                >
                  <div className="mb-1 flex items-start justify-between gap-2" data-testid={`execution-safety-p1-anomaly-item-header-${index}`}>
                    <label className="flex items-center gap-2 text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-select-wrapper-${index}`}>
                      <input
                        type="checkbox"
                        checked={!!item.intent_id && selectedAnomalyIntentIds.includes(item.intent_id)}
                        disabled={!item.intent_id}
                        onChange={(event) => handleAnomalyRowSelect(item.intent_id, event.target.checked)}
                        data-testid={`execution-safety-p1-anomaly-item-select-checkbox-${index}`}
                      />
                      select
                    </label>
                    {String(item.severity_level || item.severity || "").toUpperCase() === "HIGH" && (
                      <span className="rounded bg-rose-600/20 px-2 py-0.5 text-[10px] text-rose-100" data-testid={`execution-safety-p1-anomaly-item-high-highlight-${index}`}>HIGH PRIORITY</span>
                    )}
                  </div>
                  <p className="text-xs text-rose-100" data-testid={`execution-safety-p1-anomaly-item-type-${index}`}>type: {item.type}</p>
                  <p className="text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-severity-${index}`}>severity: {item.severity_level || item.severity}</p>
                  <p className="text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-risk-${index}`}>severity_score: {item.severity_score ?? item.risk_score}</p>
                  <p className="text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-impact-${index}`}>impact: {item.impact || "-"}</p>
                  <p className="text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-priority-${index}`}>priority: {item.priority ?? "-"}</p>
                  <p className="text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-guard-reason-${index}`}>guard_reason: {item.action_guard?.reason || "-"}</p>
                  <p className="text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-intent-${index}`}>intent_id: {item.intent_id || "-"}</p>
                  <p className="text-xs text-slate-300" data-testid={`execution-safety-p1-anomaly-item-detected-at-${index}`}>detected_at: {item.detected_at || "-"}</p>
                  <p className="text-xs text-amber-200" data-testid={`execution-safety-p1-anomaly-item-reason-${index}`}>reason: {item.reason || "-"}</p>
                  <div className="mt-1 space-y-1" data-testid={`execution-safety-p1-anomaly-item-recommended-actions-${index}`}>
                    {(item.recommended_actions || []).slice(0, 2).map((action, actionIdx) => (
                      <p key={`${action.action}-${actionIdx}`} className="text-[11px] text-cyan-200" data-testid={`execution-safety-p1-anomaly-item-recommended-action-${index}-${actionIdx}`}>
                        {action.action} ({action.confidence}) - {action.reason}
                      </p>
                    ))}
                    {!(item.recommended_actions || []).length && (
                      <p className="text-[11px] text-slate-500" data-testid={`execution-safety-p1-anomaly-item-recommended-action-empty-${index}`}>öneri bulunamadı</p>
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1" data-testid={`execution-safety-p1-anomaly-item-inline-actions-${index}`}>
                    <a
                      href={item.intent_id ? `/admin/execution/operator-center?intent_id=${encodeURIComponent(item.intent_id)}` : "#"}
                      className={`inline-flex items-center rounded border px-2 py-1 text-xs ${item.intent_id ? "border-slate-600 text-slate-200" : "pointer-events-none border-slate-700 text-slate-500"}`}
                      data-testid={`execution-safety-p1-anomaly-item-inline-drilldown-${index}`}
                    >
                      Drilldown
                    </a>
                    <Button size="sm" variant="outline" onClick={() => executeAnomalyQuickAction("retry", [item.intent_id])} disabled={actionLoading || !item.intent_id || !(item.allowed_actions || []).includes("retry")} data-testid={`execution-safety-p1-anomaly-item-inline-retry-${index}`}>Retry</Button>
                    <Button size="sm" variant="outline" onClick={() => executeAnomalyQuickAction("reconcile", [item.intent_id])} disabled={actionLoading || !item.intent_id || !(item.allowed_actions || []).includes("reconcile")} data-testid={`execution-safety-p1-anomaly-item-inline-reconcile-${index}`}>Reconcile</Button>
                    <Button size="sm" variant="outline" onClick={() => executeAnomalyQuickAction("cancel", [item.intent_id])} disabled={actionLoading || !item.intent_id || !(item.allowed_actions || []).includes("cancel")} data-testid={`execution-safety-p1-anomaly-item-inline-cancel-${index}`}>Cancel</Button>
                    <Button size="sm" variant="outline" onClick={() => executeAnomalyQuickAction("escalate", [item.intent_id])} disabled={actionLoading || !item.intent_id || !(item.allowed_actions || []).includes("escalate")} data-testid={`execution-safety-p1-anomaly-item-inline-escalate-${index}`}>Escalate</Button>
                  </div>
                </div>
              ))}
              {anomaliesList.length === 0 && (
                <p className="text-xs text-slate-500" data-testid="execution-safety-p1-anomaly-empty">Seçili filtrelere göre anomaly bulunamadı.</p>
              )}
            </div>
          </article>

          <article className="rounded-lg border border-cyan-700/40 bg-slate-950 p-3" data-testid="execution-safety-p1-simulation-card">
            <h3 className="text-sm font-semibold text-cyan-200" data-testid="execution-safety-p1-simulation-title">Hybrid Dry-run / Shadow Execution</h3>
            <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="execution-safety-p1-simulation-form-grid">
              <div data-testid="execution-safety-p1-simulation-symbol-wrapper">
                <label className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-symbol-label">symbol</label>
                <input
                  value={dryRunSymbol}
                  onChange={(event) => setDryRunSymbol(event.target.value)}
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-white"
                  data-testid="execution-safety-p1-simulation-symbol-input"
                />
              </div>
              <div data-testid="execution-safety-p1-simulation-qty-wrapper">
                <label className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-qty-label">qty</label>
                <input
                  value={dryRunQty}
                  onChange={(event) => setDryRunQty(event.target.value)}
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-white"
                  data-testid="execution-safety-p1-simulation-qty-input"
                />
              </div>
              <div data-testid="execution-safety-p1-simulation-side-wrapper">
                <label className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-side-label">side</label>
                <select
                  value={dryRunSide}
                  onChange={(event) => setDryRunSide(event.target.value)}
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-white"
                  data-testid="execution-safety-p1-simulation-side-select"
                >
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" data-testid="execution-safety-p1-simulation-action-buttons">
              <Button
                onClick={() => handleExecutionSimulation("dry-run")}
                disabled={actionLoading}
                data-testid="execution-safety-p1-simulation-run-dry-button"
              >
                Dry-run Execute
              </Button>
              <Button
                variant="outline"
                onClick={() => handleExecutionSimulation("shadow")}
                disabled={actionLoading}
                data-testid="execution-safety-p1-simulation-run-shadow-button"
              >
                Shadow Execute
              </Button>
            </div>

            <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="execution-safety-p1-simulation-results-grid">
              <div className="rounded border border-slate-700 bg-slate-900 p-2" data-testid="execution-safety-p1-simulation-dry-result-card">
                <p className="text-xs font-semibold text-slate-200" data-testid="execution-safety-p1-simulation-dry-result-title">dry_run_result</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-dry-mode">mode: {dryRunResult?.mode || "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-dry-intent-id">intent_id: {dryRunResult?.intent_id || "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-dry-fill">expected_fill_price: {dryRunResult?.expected_fill_price ?? "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-dry-pnl">expected_pnl: {dryRunResult?.expected_pnl ?? "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-dry-degrade">degrade_mode: {dryRunResult ? (dryRunResult?.degrade_mode ? "true" : "false") : "-"}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-900 p-2" data-testid="execution-safety-p1-simulation-shadow-result-card">
                <p className="text-xs font-semibold text-slate-200" data-testid="execution-safety-p1-simulation-shadow-result-title">shadow_result</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-shadow-mode">mode: {shadowResult?.mode || "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-shadow-intent-id">intent_id: {shadowResult?.intent_id || "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-shadow-fill">expected_fill_price: {shadowResult?.expected_fill_price ?? "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-shadow-pnl">expected_pnl: {shadowResult?.expected_pnl ?? "-"}</p>
                <p className="text-xs text-slate-300" data-testid="execution-safety-p1-simulation-shadow-degrade">degrade_mode: {shadowResult ? (shadowResult?.degrade_mode ? "true" : "false") : "-"}</p>
              </div>
            </div>
          </article>
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

      <Dialog
        open={quickActionModal.open}
        onOpenChange={(open) => {
          if (!open) {
            setQuickActionModal({ open: false, action: "", intentIds: [] });
          }
        }}
      >
        <DialogContent data-testid="execution-safety-p1-high-action-confirmation-modal">
          <DialogHeader>
            <DialogTitle data-testid="execution-safety-p1-high-action-confirmation-modal-title">HIGH Severity Aksiyon Onayı</DialogTitle>
            <DialogDescription data-testid="execution-safety-p1-high-action-confirmation-modal-description">
              HIGH anomaly için {quickActionModal.action?.toUpperCase()} aksiyonu onay gerektirir. Bu işlem audit trail’e yazılır.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1 text-xs text-slate-300" data-testid="execution-safety-p1-high-action-confirmation-modal-body">
            <p data-testid="execution-safety-p1-high-action-confirmation-modal-action">action: {quickActionModal.action || "-"}</p>
            <p data-testid="execution-safety-p1-high-action-confirmation-modal-count">intent_count: {quickActionModal.intentIds.length}</p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setQuickActionModal({ open: false, action: "", intentIds: [] })}
              data-testid="execution-safety-p1-high-action-confirmation-modal-cancel-button"
            >
              Vazgeç
            </Button>
            <Button
              onClick={() => executeAnomalyQuickAction(quickActionModal.action, quickActionModal.intentIds)}
              disabled={actionLoading}
              data-testid="execution-safety-p1-high-action-confirmation-modal-confirm-button"
            >
              Onayla
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
            <DialogDescription data-testid="admin-production-gate-mode-modal-description">SIM/PAPER/MOCK → LIVE geçişinde Gate hard-block aktifse işlem reddedilir.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2" data-testid="admin-production-gate-mode-modal-form">
            <label className="text-xs text-slate-300" data-testid="admin-production-gate-mode-target-label">target_mode</label>
            <select className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white" value={targetMode} onChange={(event) => { setTargetMode(event.target.value); setConfirmationPhrase(event.target.value === "LIVE" ? "SWITCH TO LIVE" : event.target.value === "SIM" ? "SWITCH TO SIM" : event.target.value === "PAPER" ? "SWITCH TO PAPER" : "SWITCH TO MOCK"); }} data-testid="admin-production-gate-mode-target-select">
              <option value="LIVE">LIVE</option>
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
