import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ScannerResultsTable } from "@/components/ScannerResultsTable";
import { TradeSymbolSelection } from "@/components/TradeSymbolSelection";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { saveExecutionContext } from "@/lib/userFlowContext";
import { DecisionCard } from "@/pages/user/components/DecisionCard";
import { ExplainabilityDrawer } from "@/pages/user/components/ExplainabilityDrawer";

const scannerQuickPresets = [
  {
    id: "manual-discovery",
    label: "Manual Discovery",
    mode: "MANUAL",
    maxResults: 20,
    note: "Sinyalleri manuel inceleyip onaylamak için.",
  },
  {
    id: "assisted-balanced",
    label: "Semi-Auto Balanced",
    mode: "ASSISTED",
    maxResults: 25,
    note: "Risk ve queue kontrollü yarı otomatik akış.",
  },
  {
    id: "auto-momentum",
    label: "Full Auto Momentum",
    mode: "AUTO",
    maxResults: 30,
    note: "Uygun sinyallerde intent hattını otomatik başlatır.",
  },
];

const AUTO_SCAN_INTERVAL_SECONDS = 180;
const PROFILE_INTERVAL_OPTIONS = [
  { value: 180, label: "3 dakika" },
  { value: 300, label: "5 dakika" },
  { value: 900, label: "15 dakika" },
];

const normalizeIntervalSeconds = (value) => {
  const allowed = new Set(PROFILE_INTERVAL_OPTIONS.map((option) => Number(option.value)));
  const parsed = Number(value || AUTO_SCAN_INTERVAL_SECONDS);
  return allowed.has(parsed) ? parsed : AUTO_SCAN_INTERVAL_SECONDS;
};

const MINIMAL_FILTER_DEFAULTS = {
  rsi_min: "",
  rsi_max: "",
  volume_min: "",
  market_cap_min: "",
  timeframe: "1h",
};

const compactMinimalFilters = (filters) => Object.entries(filters || {}).reduce((acc, [key, value]) => {
  if (value === "" || value === null || typeof value === "undefined") {
    return acc;
  }
  if (key === "timeframe") {
    acc[key] = String(value).trim().toLowerCase();
    return acc;
  }
  const numeric = Number(value);
  if (!Number.isNaN(numeric)) {
    acc[key] = numeric;
  }
  return acc;
}, {});

const REQUEST_HEALTH_WINDOW_MS = 60_000;
const REQUEST_TREND_WINDOW_MS = 300_000;

const buildFiveMinuteTrend = (events, nowTs = Date.now()) => {
  const bucketMs = 60_000;
  const startTs = nowTs - REQUEST_TREND_WINDOW_MS;
  return Array.from({ length: 5 }, (_, index) => {
    const bucketStart = startTs + (index * bucketMs);
    const bucketEnd = bucketStart + bucketMs;
    const bucketEvents = events.filter((item) => item.timestamp >= bucketStart && item.timestamp < bucketEnd);
    const total = bucketEvents.length;
    const success = bucketEvents.filter((item) => item.ok).length;
    const successRatio = total > 0 ? success / total : 1;
    return {
      key: `m${index}`,
      label: `${5 - index}m`,
      total,
      success,
      successRatio,
    };
  });
};

const deriveRequestHealth = (events) => {
  const total = events.length;
  const success = events.filter((event) => event.ok).length;
  const failed = Math.max(total - success, 0);
  const successRatio = total > 0 ? success / total : 1;

  if (total === 0) {
    return {
      total,
      success,
      failed,
      successRatio,
      health: "NO_DATA",
    };
  }
  if (successRatio >= 0.95) {
    return { total, success, failed, successRatio, health: "HEALTHY" };
  }
  if (successRatio >= 0.8) {
    return { total, success, failed, successRatio, health: "DEGRADED" };
  }
  return { total, success, failed, successRatio, health: "CRITICAL" };
};

export const UserScannerPage = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState("ASSISTED");
  const [overview, setOverview] = useState(null);
  const [scannerResults, setScannerResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);
  const [symbolSource, setSymbolSource] = useState("crypto");
  const [symbolMode, setSymbolMode] = useState("all_market_symbols");
  const [selectedSymbols, setSelectedSymbols] = useState([]);
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [automationConfig, setAutomationConfig] = useState(null);
  const [automationProfiles, setAutomationProfiles] = useState([]);
  const [activeProfileId, setActiveProfileId] = useState("");
  const [profileNameInput, setProfileNameInput] = useState("");
  const [profileIntervalInput, setProfileIntervalInput] = useState(AUTO_SCAN_INTERVAL_SECONDS);
  const [autoScanInterval, setAutoScanInterval] = useState(AUTO_SCAN_INTERVAL_SECONDS);
  const [autoRunAlerts, setAutoRunAlerts] = useState([]);
  const [runtimeSnapshot, setRuntimeSnapshot] = useState(null);
  const [liveReadiness, setLiveReadiness] = useState(null);
  const [scannerDailyReport, setScannerDailyReport] = useState(null);
  const [scannerLoadDegraded, setScannerLoadDegraded] = useState(false);
  const [scannerLoadFailures, setScannerLoadFailures] = useState([]);
  const [decisionCards, setDecisionCards] = useState([]);
  const [selectedDecisionSymbol, setSelectedDecisionSymbol] = useState("");
  const [isExplainabilityDrawerOpen, setIsExplainabilityDrawerOpen] = useState(false);
  const [symbolExplainability, setSymbolExplainability] = useState(null);
  const [isExplainabilityLoading, setIsExplainabilityLoading] = useState(false);
  const [isSavingAutomation, setIsSavingAutomation] = useState(false);
  const [selectionSavedAt, setSelectionSavedAt] = useState(null);
  const [selectionHydrated, setSelectionHydrated] = useState(false);
  const [minimalFilters, setMinimalFilters] = useState(MINIMAL_FILTER_DEFAULTS);
  const [requestHealth, setRequestHealth] = useState({
    total: 0,
    success: 0,
    failed: 0,
    successRatio: 1,
    health: "NO_DATA",
    windowSeconds: 60,
    updatedAt: null,
  });
  const [requestTrend, setRequestTrend] = useState(() => buildFiveMinuteTrend([]));
  const profileRunTrackerRef = useRef({});
  const symbolPersistTimerRef = useRef(null);
  const minimalFiltersRef = useRef(MINIMAL_FILTER_DEFAULTS);
  const requestWindowRef = useRef([]);
  const requestTrendRef = useRef([]);

  const activeProfile = useMemo(() => {
    if (!automationProfiles.length) {
      return null;
    }
    return (
      automationProfiles.find((item) => item.id === activeProfileId)
      || automationProfiles.find((item) => item.is_active)
      || automationProfiles[0]
    );
  }, [activeProfileId, automationProfiles]);

  const activeAutomation = activeProfile || automationConfig;

  const activeMinimalFilterChips = useMemo(() => {
    const mapping = {
      rsi_min: "RSI min",
      rsi_max: "RSI max",
      volume_min: "Volume min",
      market_cap_min: "Market Cap min",
      timeframe: "Timeframe",
    };
    return Object.entries(minimalFilters)
      .filter(([key, value]) => key === "timeframe" ? Boolean(value) : value !== "")
      .map(([key, value]) => ({ key, label: `${mapping[key]}: ${value}` }));
  }, [minimalFilters]);

  const activeModeLabel = String(overview?.mode || mode || "ASSISTED").toUpperCase();
  const scannerRunType = activeAutomation?.auto_enabled ? "OTOMATİK TARAMA" : "MANUEL TARAMA";
  const scannerRunTypeDetail = activeAutomation?.auto_enabled
    ? `Zamanlayıcı aktif · ${Number(activeAutomation?.interval_seconds || AUTO_SCAN_INTERVAL_SECONDS)} sn aralık`
    : "Run butonuyla manuel tetikleme";
  const executionPathLabel =
    activeModeLabel === "AUTO"
      ? "BOT_AUTO_ACTIVE"
      : activeModeLabel === "ASSISTED"
        ? "SEMI_AUTO_ACTIVE"
        : "MANUAL_REVIEW_FLOW";

  const requestHealthBadgeClass =
    requestHealth.health === "HEALTHY"
      ? "border-emerald-700 bg-emerald-950/40 text-emerald-300"
      : requestHealth.health === "DEGRADED"
        ? "border-amber-700 bg-amber-950/40 text-amber-300"
        : requestHealth.health === "CRITICAL"
          ? "border-red-700 bg-red-950/40 text-red-300"
          : "border-slate-700 bg-slate-950 text-slate-300";

  const requestTrendPolylinePoints = useMemo(() => {
    const width = 160;
    const height = 32;
    if (!requestTrend.length) {
      return "";
    }
    return requestTrend.map((point, index) => {
      const x = requestTrend.length === 1 ? 0 : (index / (requestTrend.length - 1)) * width;
      const normalized = Math.max(0, Math.min(1, Number(point.successRatio || 0)));
      const y = height - (normalized * height);
      return `${x},${y}`;
    }).join(" ");
  }, [requestTrend]);

  const formatDateLabel = (value) => {
    if (!value) {
      return "-";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "-";
    }
    return parsed.toLocaleString("tr-TR");
  };

  useEffect(() => {
    minimalFiltersRef.current = minimalFilters;
  }, [minimalFilters]);

  const updateRequestHealthWindow = useCallback((settledResponses = []) => {
    const now = Date.now();
    const retained = (requestWindowRef.current || []).filter((item) => now - item.timestamp <= REQUEST_HEALTH_WINDOW_MS);
    const incoming = Array.isArray(settledResponses)
      ? settledResponses.map((item) => ({
        timestamp: now,
        ok: item?.status === "fulfilled",
      }))
      : [];
    const merged = [...retained, ...incoming];
    requestWindowRef.current = merged;

    const retainedTrend = (requestTrendRef.current || []).filter((item) => now - item.timestamp <= REQUEST_TREND_WINDOW_MS);
    const mergedTrend = [...retainedTrend, ...incoming];
    requestTrendRef.current = mergedTrend;

    const metrics = deriveRequestHealth(merged);
    setRequestHealth({
      ...metrics,
      windowSeconds: 60,
      updatedAt: new Date(now).toISOString(),
    });
    setRequestTrend(buildFiveMinuteTrend(mergedTrend, now));
  }, []);

  const loadSymbolExplainability = async (symbol) => {
    if (!symbol) {
      setSymbolExplainability(null);
      return;
    }
    setIsExplainabilityLoading(true);
    try {
      const { data } = await apiClient.get(`/user/explainability/${encodeURIComponent(symbol)}`);
      setSymbolExplainability(data || null);
    } catch (error) {
      setSymbolExplainability(null);
      toast.error(error?.response?.data?.detail || "Explainability yüklenemedi");
    } finally {
      setIsExplainabilityLoading(false);
    }
  };

  const saveAutomationConfig = async ({ autoEnabled, withToast = true } = {}) => {
    const nextEnabled = typeof autoEnabled === "boolean" ? autoEnabled : Boolean(automationConfig?.auto_enabled ?? true);
    setIsSavingAutomation(true);
    try {
      const { data } = await apiClient.put("/user/scanner/automation", {
        auto_enabled: nextEnabled,
        interval_seconds: normalizeIntervalSeconds(autoScanInterval),
        max_results: 25,
        symbol_source: symbolSource,
        symbol_selection_mode: watchlistOnly ? "manual_selection" : symbolMode,
        selected_symbols: selectedSymbols,
      });
      setAutomationConfig(data || null);
      if (withToast) {
        toast.success(nextEnabled ? "3 dakikalık otomatik scanner aktif" : "Otomatik scanner kapatıldı");
      }
      return data;
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Otomasyon ayarı kaydedilemedi");
      throw error;
    } finally {
      setIsSavingAutomation(false);
    }
  };

  const syncAutoRunNotifications = (profiles, { notify = false } = {}) => {
    const tracker = profileRunTrackerRef.current || {};
    const nextTracker = { ...tracker };

    for (const profile of profiles || []) {
      const lastRunId = String(profile?.last_run_id || "");
      const previousRunId = String(tracker?.[profile.id] || "");
      if (notify && lastRunId && previousRunId && lastRunId !== previousRunId && profile?.last_run_status === "success") {
        const newSignalCount = Number(profile?.last_actionable_count || 0);
        if (newSignalCount > 0) {
          toast.success(`Yeni sinyal var: ${profile.name} (${newSignalCount})`);
          setAutoRunAlerts((prev) => [
            {
              id: `${profile.id}-${lastRunId}`,
              profile_name: profile.name,
              signal_count: newSignalCount,
              run_at: profile.last_run_at,
            },
            ...prev,
          ].slice(0, 10));
        }
      }
      if (lastRunId) {
        nextTracker[profile.id] = lastRunId;
      }
    }

    profileRunTrackerRef.current = nextTracker;
  };

  const saveActiveProfile = async ({ autoEnabled, withToast = true } = {}) => {
    if (!activeProfile) {
      return saveAutomationConfig({ autoEnabled, withToast });
    }

    setIsSavingAutomation(true);
    try {
      const nextEnabled = typeof autoEnabled === "boolean" ? autoEnabled : Boolean(activeProfile.auto_enabled);
      const { data } = await apiClient.put(`/user/scanner/automation-profiles/${activeProfile.id}`, {
        name: activeProfile.name,
        auto_enabled: nextEnabled,
        is_active: true,
        interval_seconds: normalizeIntervalSeconds(activeProfile.interval_seconds),
        max_results: 25,
        symbol_source: symbolSource,
        symbol_selection_mode: watchlistOnly ? "manual_selection" : symbolMode,
        selected_symbols: selectedSymbols,
      });
      setAutomationProfiles((prev) => prev.map((item) => (item.id === data.id ? data : { ...item, is_active: false })));
      setActiveProfileId(data.id);
      if (withToast) {
        toast.success(nextEnabled ? `Profil güncellendi: ${data.name}` : `Profil pasif: ${data.name}`);
      }
      return data;
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Profil kaydedilemedi");
      throw error;
    } finally {
      setIsSavingAutomation(false);
    }
  };

  const createAutomationProfile = async () => {
    const profileName = profileNameInput.trim();
    if (!profileName) {
      toast.error("Profil adı zorunlu");
      return;
    }
    setIsSavingAutomation(true);
    try {
      await apiClient.post("/user/scanner/automation-profiles", {
        name: profileName,
        auto_enabled: true,
        is_active: true,
        interval_seconds: normalizeIntervalSeconds(profileIntervalInput),
        max_results: 25,
        symbol_source: symbolSource,
        symbol_selection_mode: watchlistOnly ? "manual_selection" : symbolMode,
        selected_symbols: selectedSymbols,
      });
      setProfileNameInput("");
      await load({ hydrateSelection: true, notifyAutoRuns: false });
      toast.success("Otomasyon profili oluşturuldu");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Profil oluşturulamadı");
    } finally {
      setIsSavingAutomation(false);
    }
  };

  const activateAutomationProfile = async (profileId) => {
    setIsSavingAutomation(true);
    try {
      await apiClient.post(`/user/scanner/automation-profiles/${profileId}/activate`);
      await load({ hydrateSelection: true, notifyAutoRuns: false });
      toast.success("Profil aktif edildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Profil aktif edilemedi");
    } finally {
      setIsSavingAutomation(false);
    }
  };

  const deleteAutomationProfile = async (profileId) => {
    setIsSavingAutomation(true);
    try {
      await apiClient.delete(`/user/scanner/automation-profiles/${profileId}`);
      await load({ hydrateSelection: true, notifyAutoRuns: false });
      toast.success("Profil silindi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Profil silinemedi");
    } finally {
      setIsSavingAutomation(false);
    }
  };

  const load = useCallback(async ({ hydrateSelection = false, silent = false, notifyAutoRuns = false } = {}) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const responses = await Promise.allSettled([
        apiClient.get("/user/signal-mode"),
        apiClient.get("/user/scanner"),
        apiClient.get("/screener", {
          params: {
            limit: 80,
            filters: JSON.stringify(compactMinimalFilters(minimalFiltersRef.current)),
          },
        }),
        apiClient.get("/user/scanner/automation"),
        apiClient.get("/user/scanner/automation-profiles"),
        apiClient.get("/user/decision-cards", { params: { limit: 60 } }),
        apiClient.get("/user/scanner/symbol-selection", { params: { scanner_id: "default" } }),
        apiClient.get("/user/scanner/runtime/snapshot"),
        apiClient.get("/user/scanner/runtime/live-readiness", { params: { window: "24h" } }),
        apiClient.get("/user/scanner/runtime/daily-report", { params: { window: "24h" } }),
      ]);

      updateRequestHealthWindow(responses);

      const failedIndexes = responses
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => item.status === "rejected")
        .map(({ index }) => index);

      const endpointByIndex = {
        0: "signal_mode",
        1: "scanner_overview",
        2: "scanner_results",
        3: "scanner_automation",
        4: "scanner_profiles",
        5: "decision_cards",
        6: "symbol_selection",
        7: "runtime_snapshot",
        8: "live_readiness",
        9: "daily_report",
      };
      const failedKeys = failedIndexes.map((index) => endpointByIndex[index]).filter(Boolean);
      setScannerLoadFailures(failedKeys);
      setScannerLoadDegraded(failedKeys.length > 0);
      if (failedKeys.length > 0 && !silent) {
        toast.error(`Scanner kısmi yüklendi: ${failedKeys.join(", ")}`);
      }

      const modeRes = responses[0].status === "fulfilled" ? responses[0].value : null;
      const overviewRes = responses[1].status === "fulfilled" ? responses[1].value : null;
      const resultsRes = responses[2].status === "fulfilled" ? responses[2].value : null;
      const automationRes = responses[3].status === "fulfilled" ? responses[3].value : null;
      const profilesRes = responses[4].status === "fulfilled" ? responses[4].value : null;
      const cardsRes = responses[5].status === "fulfilled" ? responses[5].value : null;
      const persistedSelectionRes = responses[6].status === "fulfilled" ? responses[6].value : null;
      const runtimeRes = responses[7].status === "fulfilled" ? responses[7].value : null;
      const readinessRes = responses[8].status === "fulfilled" ? responses[8].value : null;
      const dailyRes = responses[9].status === "fulfilled" ? responses[9].value : null;

      setMode((prev) => modeRes?.data?.mode || prev || "ASSISTED");
      setOverview((prev) => overviewRes?.data || prev || null);
      setScannerResults((prev) => resultsRes?.data || prev || []);
      const automation = automationRes?.data || null;
      const profiles = profilesRes?.data || [];
      setAutomationConfig(automation);
      setAutomationProfiles(profiles);
      const cards = cardsRes?.data?.items || [];
      const persistedSelection = persistedSelectionRes?.data || null;
      setRuntimeSnapshot((prev) => runtimeRes?.data || prev || null);
      setLiveReadiness((prev) => readinessRes?.data || prev || null);
      setScannerDailyReport((prev) => dailyRes?.data || prev || null);
      setDecisionCards(cards);
      if (cards.length > 0) {
        const selectedSymbol = selectedDecisionSymbol || cards[0].symbol;
        setSelectedDecisionSymbol(selectedSymbol);
        await loadSymbolExplainability(selectedSymbol);
      } else {
        setSelectedDecisionSymbol("");
        setSymbolExplainability(null);
      }
      syncAutoRunNotifications(profiles, { notify: notifyAutoRuns });

      if (hydrateSelection) {
        const selectedProfile = profiles.find((item) => item.is_active) || profiles[0] || null;
        if (selectedProfile) {
          setActiveProfileId(selectedProfile.id);
          setProfileIntervalInput(normalizeIntervalSeconds(selectedProfile.interval_seconds));
            setAutoScanInterval(normalizeIntervalSeconds(selectedProfile.interval_seconds));
          setSymbolSource(selectedProfile.symbol_source || "crypto");
          setSymbolMode(selectedProfile.symbol_selection_mode || "all_market_symbols");
          setSelectedSymbols(Array.isArray(selectedProfile.selected_symbols) ? selectedProfile.selected_symbols : []);
        } else if (automation) {
          setActiveProfileId("");
            setAutoScanInterval(normalizeIntervalSeconds(automation.interval_seconds));
          setSymbolSource(automation.symbol_source || "crypto");
          setSymbolMode(automation.symbol_selection_mode || "all_market_symbols");
          setSelectedSymbols(Array.isArray(automation.selected_symbols) ? automation.selected_symbols : []);
        }
        if (persistedSelection) {
          setSymbolSource(persistedSelection.symbol_source || "crypto");
          setSymbolMode(persistedSelection.symbol_selection_mode || "all_market_symbols");
          setSelectedSymbols(Array.isArray(persistedSelection.selected_symbols) ? persistedSelection.selected_symbols : []);
          setSelectionSavedAt(persistedSelection.saved_at || null);
        }
          const normalizedMode = String((persistedSelection?.symbol_selection_mode || selectedProfile?.symbol_selection_mode || automation?.symbol_selection_mode || "all_market_symbols")).toLowerCase();
          setWatchlistOnly(normalizedMode === "manual_selection" && Array.isArray(persistedSelection?.selected_symbols || selectedProfile?.selected_symbols || automation?.selected_symbols) && (persistedSelection?.selected_symbols || selectedProfile?.selected_symbols || automation?.selected_symbols || []).length > 0);
        setSelectionHydrated(true);
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  }, [selectedDecisionSymbol, updateRequestHealthWindow]);

  useEffect(() => {
    const timer = setInterval(() => {
      updateRequestHealthWindow([]);
    }, 5000);
    return () => clearInterval(timer);
  }, [updateRequestHealthWindow]);

  useEffect(() => {
    load({ hydrateSelection: true });
  }, [load]);

  useEffect(() => {
    if (!selectionHydrated) {
      return;
    }
    load({ silent: true, notifyAutoRuns: false });
  }, [selectionHydrated, minimalFilters, load]);

  useEffect(() => {
    const timer = setInterval(() => {
      load({ silent: true, notifyAutoRuns: true });
    }, 10000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!watchlistOnly) {
      return;
    }
    if (symbolMode !== "manual_selection") {
      setSymbolMode("manual_selection");
    }
  }, [watchlistOnly, symbolMode]);

  useEffect(() => {
    if (!selectionHydrated) {
      return;
    }
    if (symbolPersistTimerRef.current) {
      clearTimeout(symbolPersistTimerRef.current);
    }
    symbolPersistTimerRef.current = setTimeout(async () => {
      try {
        const { data } = await apiClient.put("/user/scanner/symbol-selection", {
          scanner_id: "default",
          symbol_source: symbolSource,
          symbol_selection_mode: watchlistOnly ? "manual_selection" : symbolMode,
          selected_symbols: selectedSymbols,
        });
        setSelectionSavedAt(data?.saved_at || null);
      } catch {
        // otomatik persist sessiz hataya toleranslı
      }
    }, 700);
    return () => {
      if (symbolPersistTimerRef.current) {
        clearTimeout(symbolPersistTimerRef.current);
      }
    };
  }, [selectionHydrated, symbolMode, symbolSource, selectedSymbols, watchlistOnly]);

  const ensureScannerRunReady = () => {
    if ((selectedSymbols || []).length === 0) {
      toast.error("İşlem için en az bir geçerli USDT/USDC market seçmelisiniz.");
      return false;
    }
    return true;
  };

  const addWatchlistFromResult = async (item) => {
    const symbol = String(item?.symbol || "").trim().toUpperCase();
    if (!symbol) {
      toast.error("Watchlist için sembol bulunamadı");
      return;
    }
    try {
      const { data: lists } = await apiClient.get("/symbol-selector/watchlists", { params: { source: symbolSource } });
      const defaultName = "scanner-watchlist";
      const existing = (lists || []).find((row) => String(row?.name || "").toLowerCase() === defaultName);

      if (existing) {
        const mergedSymbols = Array.from(
          new Set([...(existing.symbols || []).map((value) => String(value || "").toUpperCase()), symbol]),
        );
        await apiClient.put(`/symbol-selector/watchlists/${existing.id}`, {
          name: existing.name,
          symbols: mergedSymbols,
        });
      } else {
        await apiClient.post("/symbol-selector/watchlists", {
          name: defaultName,
          source: symbolSource,
          exchange: "binance",
          market_type: "spot",
          symbols: [symbol],
        });
      }

      setSelectedSymbols((prev) => Array.from(new Set([...(prev || []).map((value) => String(value || "").toUpperCase()), symbol])));
      toast.success(`${symbol} watchlist'e eklendi`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Watchlist güncellenemedi");
    }
  };

  const exportScannerDailyReport = async (format) => {
    try {
      const isCsv = format === "csv";
      const response = await apiClient.get("/user/scanner/runtime/daily-report/export", {
        params: { format, window: "24h" },
        responseType: isCsv ? "blob" : "json",
      });

      const blob = isCsv
        ? new Blob([response.data], { type: "text/csv" })
        : new Blob([JSON.stringify(response.data, null, 2)], { type: "application/json" });

      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = isCsv
        ? `scanner_daily_report_${scannerDailyReport?.date || "latest"}.csv`
        : `scanner_daily_report_${scannerDailyReport?.date || "latest"}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
      toast.success(`Scanner günlük rapor ${format.toUpperCase()} hazır`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Scanner rapor export başarısız");
    }
  };

  const runScanner = async () => {
    if (!ensureScannerRunReady()) {
      return;
    }

    const effectiveMode = watchlistOnly ? "manual_selection" : symbolMode;
    setIsRunning(true);
    try {
      if (activeAutomation?.auto_enabled) {
        await saveActiveProfile({ autoEnabled: true, withToast: false });
      }
      await apiClient.put("/user/signal-mode", { mode });
      const { data } = await apiClient.post("/user/scanner/run", {
        mode,
        max_results: 25,
        symbol_source: symbolSource,
        symbol_selection_mode: effectiveMode,
        selected_symbols: selectedSymbols,
      });
      await load();
      if ((data?.warnings || []).length > 0) {
        toast.warning((data.warnings || []).join(","));
      }
      toast.success("Scanner çalıştırıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Scanner çalıştırılamadı");
    } finally {
      setIsRunning(false);
    }
  };

  const runPreset = async (preset) => {
    if (!ensureScannerRunReady()) {
      return;
    }

    const effectiveMode = watchlistOnly ? "manual_selection" : symbolMode;
    setIsRunning(true);
    try {
      await apiClient.put("/user/signal-mode", { mode: preset.mode });
      setMode(preset.mode);
      const { data } = await apiClient.post("/user/scanner/run", {
        mode: preset.mode,
        max_results: preset.maxResults,
        symbol_source: symbolSource,
        symbol_selection_mode: effectiveMode,
        selected_symbols: selectedSymbols,
      });
      await load();
      if ((data?.warnings || []).length > 0) {
        toast.warning((data.warnings || []).join(","));
      }
      toast.success(`Preset çalıştı: ${preset.label}`);
      if (activeAutomation?.auto_enabled) {
        await saveActiveProfile({ autoEnabled: true, withToast: false });
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preset çalıştırılamadı");
    } finally {
      setIsRunning(false);
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-scanner-loading-skeleton" />;
  }

  const openExecuteFromScanner = (item) => {
    const side = item.signal === "short" ? "sell" : "buy";
    const marketType = item.market_type || "spot";
    saveExecutionContext({
      source: "scanner",
      symbol: item.symbol,
      market_type: marketType,
      side,
      strategy_code: item.strategy_code,
      confidence: item.confidence,
      signal: item.signal,
      score: item.signal_score,
      timestamp: new Date().toISOString(),
      intent_payload: buildIntentPayload(item),
    });
    navigate(`/user/trade?source=scanner&symbol=${encodeURIComponent(item.symbol)}&side=${encodeURIComponent(side)}&market_type=${encodeURIComponent(marketType)}&preset=spot_basic`);
  };

  const openChartFromScanner = (item) => {
    const symbol = String(item?.symbol || "BTCUSDT").trim().toUpperCase();
    navigate(`/user/chart?symbol=${encodeURIComponent(symbol)}&tf=1h`);
  };

  const buildIntentPayload = (item) => ({
    source_type: "scanner",
    source_ref_id: item.id,
    market_type: "spot",
    symbol: item.symbol,
    side: item.signal === "short" ? "sell" : "buy",
    order_type: "market",
    position_size_mode: "fixed_notional",
    position_size_value: 30,
    take_profit_mode: "percent",
    take_profit_value: 2,
    stop_loss_mode: "percent",
    stop_loss_value: 1,
    execution_mode: "signal_follow",
    signal: item.signal,
    score: item.signal_score,
    strategy: item.strategy_code,
    confidence: item.confidence,
    timestamp: new Date().toISOString(),
    scanner_signal_snapshot: {
      symbol: item.symbol,
      signal: item.signal,
      score: item.signal_score,
      strategy: item.strategy_code,
      confidence: item.confidence,
      timestamp: new Date().toISOString(),
    },
  });

  const onSelectDecisionCard = async (symbol) => {
    setSelectedDecisionSymbol(symbol);
    await loadSymbolExplainability(symbol);
    setIsExplainabilityDrawerOpen(true);
  };

  const openSymbolDetail = (symbol) => {
    navigate(`/user/symbol/${encodeURIComponent(symbol)}`);
  };

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-scanner-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-scanner-title">Scanner</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-scanner-description">Responsive scanner + compact table + mobile card yapısı.</p>
      </header>

      <section className="col-span-12 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-request-health-mini-indicator">
        <div className="flex flex-wrap items-center gap-3" data-testid="user-scanner-request-health-row">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="user-scanner-request-health-title">Scanner Request Health</p>
          <span className={`rounded-full border px-2 py-1 text-xs font-semibold ${requestHealthBadgeClass}`} data-testid="user-scanner-request-health-badge">
            {requestHealth.health}
          </span>
          <p className="text-xs text-slate-300" data-testid="user-scanner-request-health-window">
            Son {requestHealth.windowSeconds}s request: <span className="font-semibold">{requestHealth.total}</span>
          </p>
          <p className="text-xs text-slate-300" data-testid="user-scanner-request-health-success-fail">
            ok/fail: <span className="font-semibold">{requestHealth.success}/{requestHealth.failed}</span>
          </p>
          <p className="text-xs text-slate-300" data-testid="user-scanner-request-health-success-ratio">
            başarı oranı: <span className="font-semibold">{(requestHealth.successRatio * 100).toFixed(1)}%</span>
          </p>
          <div className="ml-auto flex items-center gap-2" data-testid="user-scanner-request-health-trend-wrapper">
            <svg width="160" height="32" viewBox="0 0 160 32" className="rounded border border-slate-700 bg-slate-950" data-testid="user-scanner-request-health-trend-sparkline">
              <polyline
                fill="none"
                stroke="#22d3ee"
                strokeWidth="2"
                points={requestTrendPolylinePoints}
                data-testid="user-scanner-request-health-trend-polyline"
              />
            </svg>
            <div className="flex gap-1" data-testid="user-scanner-request-health-trend-labels">
              {requestTrend.map((point) => (
                <span key={point.key} className="text-[10px] text-slate-400" data-testid={`user-scanner-request-health-trend-label-${point.key}`}>
                  {point.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {scannerLoadDegraded && (
        <div className="order-1 col-span-12 rounded border border-amber-700 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="user-scanner-degraded-load-banner">
          Kısmi veri yüklendi. Etkilenen endpointler: {scannerLoadFailures.join(", ") || "-"}
        </div>
      )}

      <section className="order-2 col-span-12 rounded border border-cyan-800/50 bg-cyan-950/20 p-4" data-testid="user-scanner-active-mode-indicator-card">
        <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="user-scanner-active-mode-indicator-title">Scanner Active Mode Indicator</p>
        <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="user-scanner-active-mode-indicator-grid">
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-mode">Active Mode: {activeModeLabel}</p>
          <p className="text-sm font-semibold" data-testid="user-scanner-active-mode-indicator-run-type">Tarama Tipi: {scannerRunType}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-path">Execution Path: {executionPathLabel}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-source">Source: {symbolSource.toUpperCase()}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-symbol-mode">Symbol Mode: {symbolMode}</p>
        </div>
        <p className="mt-2 text-xs text-cyan-100" data-testid="user-scanner-active-mode-indicator-run-type-detail">{scannerRunTypeDetail}</p>
      </section>

      <section className="order-3 col-span-12 rounded border border-emerald-800/50 bg-emerald-950/20 p-4" data-testid="user-scanner-automation-card">
        <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="user-scanner-automation-title">
          {activeProfile ? `Scanner Otomasyon Profili: ${activeProfile.name}` : "Scanner Otomasyon (Legacy)"}
        </p>
        <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="user-scanner-automation-grid">
          <p className="text-sm" data-testid="user-scanner-automation-status">Durum: {activeAutomation?.auto_enabled ? "AKTİF" : "PASİF"}</p>
          <p className="text-sm" data-testid="user-scanner-automation-interval">Periyot: {Number(activeAutomation?.interval_seconds || AUTO_SCAN_INTERVAL_SECONDS)} saniye</p>
          <p className="text-sm" data-testid="user-scanner-automation-last-run">Son Çalışma: {formatDateLabel(activeAutomation?.last_run_at)}</p>
          <p className="text-sm" data-testid="user-scanner-automation-next-run">Sonraki Çalışma: {formatDateLabel(activeAutomation?.next_run_at)}</p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="user-scanner-automation-actions">
          <Button
            type="button"
            variant="outline"
            onClick={() => saveActiveProfile({ autoEnabled: !(activeAutomation?.auto_enabled ?? true) })}
            disabled={isSavingAutomation}
            data-testid="user-scanner-automation-toggle-button"
          >
            {isSavingAutomation ? "Kaydediliyor..." : activeAutomation?.auto_enabled ? "Otomatik Tetiklemeyi Kapat" : "Otomatik Tetiklemeyi Aç"}
          </Button>
          <Button
            type="button"
            onClick={() => saveActiveProfile({ autoEnabled: true })}
            disabled={isSavingAutomation}
            data-testid="user-scanner-automation-save-selection-button"
          >
            {isSavingAutomation ? "Kaydediliyor..." : "Seçimi Kaydet (Otomasyona)"}
          </Button>
        </div>
        <p className="mt-2 text-xs text-emerald-200" data-testid="user-scanner-automation-hint">
          Kaynak + seçim modu + seçili semboller profilde saklanır; otomatik scanner kayıtlı profil periyoduyla çalışır.
        </p>
        <p className="mt-1 text-xs text-emerald-100" data-testid="user-scanner-selection-persisted-at">
          Sembol Kaydı: {formatDateLabel(selectionSavedAt)}
        </p>
      </section>

      <section className="order-4 col-span-12 rounded border border-violet-800/50 bg-violet-950/20 p-4" data-testid="user-scanner-automation-profiles-card">
        <p className="text-xs uppercase tracking-widest text-violet-300" data-testid="user-scanner-automation-profiles-title">Çoklu Otomasyon Profilleri</p>
        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="user-scanner-automation-profiles-create-grid">
          <input
            value={profileNameInput}
            onChange={(event) => setProfileNameInput(event.target.value)}
            placeholder="örn: scalp-3m"
            className="h-10 rounded border border-violet-700 bg-black px-3 text-sm"
            data-testid="user-scanner-automation-profile-name-input"
          />
          <select
            value={profileIntervalInput}
            onChange={(event) => setProfileIntervalInput(Number(event.target.value))}
            className="h-10 rounded border border-violet-700 bg-black px-3 text-sm"
            data-testid="user-scanner-automation-profile-interval-select"
          >
            {PROFILE_INTERVAL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value} data-testid={`user-scanner-automation-profile-interval-option-${option.value}`}>{option.label}</option>
            ))}
          </select>
          <Button type="button" onClick={createAutomationProfile} disabled={isSavingAutomation} data-testid="user-scanner-automation-profile-create-button">
            {isSavingAutomation ? "Kaydediliyor..." : "Profil Oluştur"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => saveActiveProfile({ autoEnabled: activeAutomation?.auto_enabled ?? true })}
            disabled={isSavingAutomation || !activeProfile}
            data-testid="user-scanner-automation-profile-update-button"
          >
            Aktif Profili Güncelle
          </Button>
        </div>
        <div className="mt-3 grid gap-2" data-testid="user-scanner-automation-profiles-list">
          {automationProfiles.length === 0 && (
            <p className="text-xs text-violet-200" data-testid="user-scanner-automation-profiles-empty">Henüz profil yok. İlk profilinizi oluşturabilirsiniz.</p>
          )}
          {automationProfiles.map((profile) => (
            <div key={profile.id} className="flex flex-wrap items-center gap-2 rounded border border-violet-700/60 bg-black/20 p-2" data-testid={`user-scanner-automation-profile-row-${profile.id}`}>
              <span className="text-sm font-semibold" data-testid={`user-scanner-automation-profile-name-${profile.id}`}>{profile.name}</span>
              <span className="text-xs" data-testid={`user-scanner-automation-profile-meta-${profile.id}`}>{Math.round(Number(profile.interval_seconds || 180) / 60)} dk · {profile.auto_enabled ? "aktif" : "pasif"}</span>
              <span className="text-xs" data-testid={`user-scanner-automation-profile-last-run-${profile.id}`}>son: {formatDateLabel(profile.last_run_at)}</span>
              <span className="text-xs" data-testid={`user-scanner-automation-profile-last-actionable-${profile.id}`}>yeni sinyal: {profile.last_actionable_count || 0}</span>
              <Button type="button" variant="outline" onClick={() => activateAutomationProfile(profile.id)} disabled={isSavingAutomation || profile.is_active} data-testid={`user-scanner-automation-profile-activate-button-${profile.id}`}>
                {profile.is_active ? "Aktif" : "Aktif Et"}
              </Button>
              <Button type="button" variant="outline" onClick={() => deleteAutomationProfile(profile.id)} disabled={isSavingAutomation} data-testid={`user-scanner-automation-profile-delete-button-${profile.id}`}>
                Sil
              </Button>
            </div>
          ))}
        </div>
      </section>

      <section className="order-8 col-span-12 rounded border border-amber-800/50 bg-amber-950/20 p-4" data-testid="user-scanner-auto-alerts-card">
        <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="user-scanner-auto-alerts-title">Otomatik Run Uyarıları</p>
        <div className="mt-2 space-y-1" data-testid="user-scanner-auto-alerts-list">
          {autoRunAlerts.length === 0 && <p className="text-xs text-amber-100" data-testid="user-scanner-auto-alerts-empty">Henüz yeni otomatik sinyal bildirimi yok.</p>}
          {autoRunAlerts.map((item) => (
            <p key={item.id} className="text-xs" data-testid={`user-scanner-auto-alert-item-${item.id}`}>
              {item.profile_name}: +{item.signal_count} sinyal · {formatDateLabel(item.run_at)}
            </p>
          ))}
        </div>
      </section>

      <section className="order-9 col-span-12 rounded border border-blue-800/50 bg-blue-950/20 p-4" data-testid="user-decision-card-section">
        <div className="flex items-center justify-between" data-testid="user-decision-card-header">
          <p className="text-xs uppercase tracking-widest text-blue-300" data-testid="user-decision-card-title">Symbol-level Decision Cards</p>
          <div className="flex items-center gap-2" data-testid="user-decision-card-toolbar-actions">
            <p className="text-xs text-blue-100" data-testid="user-decision-card-auto-refresh-label">Auto Refresh: 10s</p>
            <Button variant="outline" onClick={() => load({ silent: true })} data-testid="user-decision-card-refresh-button">Kartları Yenile</Button>
          </div>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="user-decision-card-grid">
          {decisionCards.length === 0 && <p className="text-xs text-blue-100" data-testid="user-decision-card-empty">Henüz decision card üretilmedi.</p>}
          {decisionCards.map((card) => (
            <DecisionCard
              key={card.symbol}
              card={card}
              onOpenExplainability={onSelectDecisionCard}
              onOpenSymbolDetail={openSymbolDetail}
            />
          ))}
        </div>
      </section>

      <section className="order-10 col-span-12 rounded border border-fuchsia-800/50 bg-fuchsia-950/20 p-4" data-testid="user-explainability-panel">
        <p className="text-xs uppercase tracking-widest text-fuchsia-300" data-testid="user-explainability-title">User Explainability Panel</p>
        {!selectedDecisionSymbol && <p className="mt-2 text-xs" data-testid="user-explainability-empty">Önce bir symbol decision card seçin.</p>}
        {selectedDecisionSymbol && (
          <div className="mt-2 flex flex-wrap items-center gap-3" data-testid="user-explainability-content">
            <p className="text-sm" data-testid="user-explainability-selected-symbol">Symbol: {selectedDecisionSymbol}</p>
            <Button type="button" size="sm" variant="outline" onClick={() => setIsExplainabilityDrawerOpen(true)} data-testid="user-explainability-open-drawer-button">
              Explainability Drawer Aç
            </Button>
            {isExplainabilityLoading && <p className="text-xs" data-testid="user-explainability-loading">Yükleniyor...</p>}
            {!isExplainabilityLoading && symbolExplainability && (
              <p className="text-xs text-fuchsia-100" data-testid="user-explainability-final-decision">Final Decision: {symbolExplainability.final_decision}</p>
            )}
          </div>
        )}
      </section>

      <ExplainabilityDrawer
        isOpen={isExplainabilityDrawerOpen}
        onOpenChange={setIsExplainabilityDrawerOpen}
        selectedSymbol={selectedDecisionSymbol}
        isLoading={isExplainabilityLoading}
        explainability={symbolExplainability}
        formatDateLabel={formatDateLabel}
      />

      <section className="order-5 col-span-12 space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-control-section">
        <div data-testid="user-scanner-control-header">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-control-kicker">Scanner Control</p>
          <h3 className="text-base font-semibold" data-testid="user-scanner-control-title">Run & Automation</h3>
        </div>
        <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2" data-testid="user-scanner-scan-type-indicator-card">
          <p className="text-xs text-slate-400" data-testid="user-scanner-scan-type-indicator-label">Tarama Durumu</p>
          <p className="text-sm font-semibold text-emerald-300" data-testid="user-scanner-scan-type-indicator-value">{scannerRunType}</p>
          <p className="text-xs text-slate-400" data-testid="user-scanner-scan-type-indicator-detail">{scannerRunTypeDetail}</p>
        </div>
        <div className="flex flex-wrap items-end gap-3" data-testid="user-scanner-controls">
          <label className="space-y-1" htmlFor="user-scanner-mode-select" data-testid="user-scanner-mode-field">
            <span className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-mode-label">Signal Mode</span>
            <select
              id="user-scanner-mode-select"
              className="h-10 border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              data-testid="user-scanner-mode-select"
              aria-label="Signal modu"
            >
              <option value="ASSISTED">ASSISTED</option>
              <option value="AUTO">AUTO</option>
              <option value="MANUAL">MANUAL</option>
            </select>
          </label>

          <label className="space-y-1" data-testid="user-scanner-auto-scan-interval-field">
            <span className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-auto-scan-interval-label">Auto Scan Interval</span>
            <select
              value={autoScanInterval}
              onChange={(event) => setAutoScanInterval(Number(event.target.value))}
              className="h-10 border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              data-testid="user-scanner-auto-scan-interval-select"
            >
              {PROFILE_INTERVAL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} data-testid={`user-scanner-auto-scan-interval-option-${option.value}`}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <Button onClick={runScanner} disabled={isRunning} data-testid="user-scanner-run-button" aria-label="Scanner çalıştır">
            {isRunning ? "Çalışıyor..." : "Scanner Run"}
          </Button>
          <Button variant="outline" onClick={load} data-testid="user-scanner-refresh-button" aria-label="Scanner verisini yenile">Yenile</Button>
          <Button
            variant="outline"
            onClick={() => saveActiveProfile({ autoEnabled: !(activeAutomation?.auto_enabled ?? false) })}
            disabled={isSavingAutomation}
            data-testid="user-scanner-auto-scan-toggle-button"
          >
            Auto Scan {activeAutomation?.auto_enabled ? "ON" : "OFF"}
          </Button>
          <Button variant="outline" onClick={() => setCompactMode((previous) => !previous)} data-testid="user-scanner-compact-mode-toggle" aria-label="Compact mode aç/kapat">
            {compactMode ? "Compact: ON" : "Compact: OFF"}
          </Button>
        </div>

        <div className="grid gap-2 rounded border border-slate-800 bg-slate-950 p-3 md:grid-cols-2" data-testid="user-scanner-live-scan-timer-section">
          <p className="text-sm" data-testid="user-scanner-last-scan-value">Last Scan: {formatDateLabel(activeAutomation?.last_run_at || overview?.latest_generated_at)}</p>
          <p className="text-sm" data-testid="user-scanner-next-scan-value">Next Scan: {formatDateLabel(activeAutomation?.next_run_at)}</p>
        </div>
      </section>

      <section className="order-6 col-span-12" data-testid="user-scanner-symbol-selection-section">
        <TradeSymbolSelection
          source={symbolSource}
          onSourceChange={setSymbolSource}
          mode={symbolMode}
          onModeChange={setSymbolMode}
          selectedSymbols={selectedSymbols}
          onSelectedSymbolsChange={setSelectedSymbols}
          watchlistOnly={watchlistOnly}
          onWatchlistOnlyChange={setWatchlistOnly}
        />
      </section>

      <section className="order-7 col-span-12 space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-minimal-filter-section">
        <div data-testid="user-scanner-minimal-filter-header">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-minimal-filter-kicker">Filter Layer</p>
          <h3 className="text-base font-semibold" data-testid="user-scanner-minimal-filter-title">Minimal Set</h3>
        </div>

        <div className="grid grid-cols-12 gap-3" data-testid="user-scanner-minimal-filter-grid">
          <label className="col-span-6 md:col-span-2" data-testid="user-scanner-filter-rsi-min-field">
            <span className="text-xs text-slate-400" data-testid="user-scanner-filter-rsi-min-label">rsi_min</span>
            <input
              type="number"
              value={minimalFilters.rsi_min}
              onChange={(event) => setMinimalFilters((prev) => ({ ...prev, rsi_min: event.target.value }))}
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              data-testid="user-scanner-filter-rsi-min-input"
            />
          </label>
          <label className="col-span-6 md:col-span-2" data-testid="user-scanner-filter-rsi-max-field">
            <span className="text-xs text-slate-400" data-testid="user-scanner-filter-rsi-max-label">rsi_max</span>
            <input
              type="number"
              value={minimalFilters.rsi_max}
              onChange={(event) => setMinimalFilters((prev) => ({ ...prev, rsi_max: event.target.value }))}
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              data-testid="user-scanner-filter-rsi-max-input"
            />
          </label>
          <label className="col-span-6 md:col-span-3" data-testid="user-scanner-filter-volume-min-field">
            <span className="text-xs text-slate-400" data-testid="user-scanner-filter-volume-min-label">volume_min</span>
            <input
              type="number"
              value={minimalFilters.volume_min}
              onChange={(event) => setMinimalFilters((prev) => ({ ...prev, volume_min: event.target.value }))}
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              data-testid="user-scanner-filter-volume-min-input"
            />
          </label>
          <label className="col-span-6 md:col-span-3" data-testid="user-scanner-filter-market-cap-min-field">
            <span className="text-xs text-slate-400" data-testid="user-scanner-filter-market-cap-min-label">market_cap_min</span>
            <input
              type="number"
              value={minimalFilters.market_cap_min}
              onChange={(event) => setMinimalFilters((prev) => ({ ...prev, market_cap_min: event.target.value }))}
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              data-testid="user-scanner-filter-market-cap-min-input"
            />
          </label>
          <label className="col-span-12 md:col-span-2" data-testid="user-scanner-filter-timeframe-field">
            <span className="text-xs text-slate-400" data-testid="user-scanner-filter-timeframe-label">timeframe</span>
            <select
              value={minimalFilters.timeframe}
              onChange={(event) => setMinimalFilters((prev) => ({ ...prev, timeframe: event.target.value }))}
              className="mt-1 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm"
              data-testid="user-scanner-filter-timeframe-select"
            >
              <option value="15m" data-testid="user-scanner-filter-timeframe-option-15m">15m</option>
              <option value="1h" data-testid="user-scanner-filter-timeframe-option-1h">1h</option>
              <option value="4h" data-testid="user-scanner-filter-timeframe-option-4h">4h</option>
              <option value="1d" data-testid="user-scanner-filter-timeframe-option-1d">1d</option>
            </select>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2" data-testid="user-scanner-minimal-filter-chip-row">
          {activeMinimalFilterChips.map((chip) => (
            <span
              key={chip.key}
              className="inline-flex rounded-full border border-cyan-500/60 bg-cyan-500/15 px-2 py-1 text-xs text-cyan-100"
              data-testid={`user-scanner-filter-chip-${chip.key}`}
            >
              {chip.label}
            </span>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() => setMinimalFilters(MINIMAL_FILTER_DEFAULTS)}
            data-testid="user-scanner-filter-clear-all-button"
          >
            Clear All
          </Button>
        </div>
      </section>

      <section className="order-8 col-span-12 space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-strategy-presets-section">
        <div data-testid="user-scanner-strategy-presets-header">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-strategy-presets-kicker">Strategy Presets</p>
          <h3 className="text-base font-semibold" data-testid="user-scanner-strategy-presets-title">Preset Runner</h3>
        </div>
        <div className="grid gap-3 md:grid-cols-3" data-testid="user-scanner-quick-preset-section">
        {scannerQuickPresets.map((preset) => (
          <article key={preset.id} className="rounded border border-slate-700 bg-slate-950 p-3" data-testid={`user-scanner-quick-preset-card-${preset.id}`}>
            <p className="text-sm font-semibold text-slate-100" data-testid={`user-scanner-quick-preset-title-${preset.id}`}>{preset.label}</p>
            <p className="mt-1 text-xs text-slate-400" data-testid={`user-scanner-quick-preset-note-${preset.id}`}>{preset.note}</p>
            <Button className="mt-3" variant="outline" onClick={() => runPreset(preset)} disabled={isRunning} data-testid={`user-scanner-quick-preset-run-button-${preset.id}`}>
              {isRunning ? "Çalışıyor..." : "Preset Çalıştır"}
            </Button>
          </article>
        ))}
        </div>
      </section>

      <section className="order-1 col-span-12 space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-statistics-section">
        <div data-testid="user-scanner-statistics-header">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-statistics-kicker">Statistics</p>
          <h3 className="text-base font-semibold" data-testid="user-scanner-statistics-title">Scanner Activity & Runtime Metrics</h3>
        </div>

        <div className="grid grid-cols-12 gap-3" data-testid="user-scanner-run-summary-grid">
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-mode-card"><p className="text-xs text-slate-500">Aktif Mode</p><p className="text-lg font-semibold text-orange-400" data-testid="user-scanner-summary-mode-value">{overview?.mode ?? mode}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-result-count-card"><p className="text-xs text-slate-500">Toplam Sonuç</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-result-count-value">{overview?.total_results ?? scannerResults.length}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-actionable-count-card"><p className="text-xs text-slate-500">Son Run ID</p><p className="text-sm font-semibold" data-testid="user-scanner-summary-actionable-count-value">{overview?.latest_run_id ?? "-"}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-pending-count-card"><p className="text-xs text-slate-500">Pending Queue</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-pending-count-value">{overview?.pending_signals ?? "-"}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-selected-symbol-count-card"><p className="text-xs text-slate-500">Selected Symbols</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-selected-symbol-count-value">{selectedSymbols.length}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-runtime-symbols-card"><p className="text-xs text-slate-500">Symbols Scanned</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-runtime-symbols-value">{runtimeSnapshot?.scanner_perf?.symbols_evaluated ?? 0}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-runtime-candidates-card"><p className="text-xs text-slate-500">Candidates</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-runtime-candidates-value">{runtimeSnapshot?.scanner_perf?.decision_scope_symbols ?? 0}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-runtime-qualified-card"><p className="text-xs text-slate-500">Qualified</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-runtime-qualified-value">{runtimeSnapshot?.tiered_scan?.qualification?.qualified_count ?? 0}</p></div>
        </div>
      </section>

      <section className="order-11 col-span-12 space-y-3 rounded border border-cyan-800/50 bg-cyan-950/20 p-4" data-testid="user-scanner-live-readiness-section">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="user-scanner-live-readiness-header">
          <div data-testid="user-scanner-live-readiness-title-wrap">
            <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="user-scanner-live-readiness-kicker">Live Readiness</p>
            <h3 className="text-base font-semibold" data-testid="user-scanner-live-readiness-title">Scanner → Execution Güvenlik Kontrolleri</h3>
          </div>
          <div className="flex flex-wrap gap-2" data-testid="user-scanner-live-readiness-export-actions">
            <Button variant="outline" onClick={() => exportScannerDailyReport("json")} data-testid="user-scanner-live-readiness-export-json-button">Export JSON</Button>
            <Button variant="outline" onClick={() => exportScannerDailyReport("csv")} data-testid="user-scanner-live-readiness-export-csv-button">Export CSV</Button>
          </div>
        </div>

        <div className="grid gap-2 md:grid-cols-3" data-testid="user-scanner-live-readiness-grid">
          <article className="rounded border border-cyan-900 bg-slate-950 p-3" data-testid="user-scanner-live-readiness-symbol-integrity-card">
            <p className="text-xs text-cyan-200" data-testid="user-scanner-live-readiness-symbol-integrity-label">Symbol Integrity</p>
            <p className="text-sm font-semibold" data-testid="user-scanner-live-readiness-symbol-integrity-value">
              {liveReadiness?.symbol_integrity?.ok ? "OK" : "MISMATCH"} ({liveReadiness?.symbol_integrity?.matched ?? 0}/{liveReadiness?.symbol_integrity?.checked ?? 0})
            </p>
          </article>
          <article className="rounded border border-cyan-900 bg-slate-950 p-3" data-testid="user-scanner-live-readiness-risk-guard-card">
            <p className="text-xs text-cyan-200" data-testid="user-scanner-live-readiness-risk-guard-label">Max Risk Guard</p>
            <p className="text-sm font-semibold" data-testid="user-scanner-live-readiness-risk-guard-value">
              max_positions=3 | daily_loss_limit=1% | daily_loss={liveReadiness?.max_risk_guard?.daily_loss_pct ?? 0}%
            </p>
          </article>
          <article className="rounded border border-cyan-900 bg-slate-950 p-3" data-testid="user-scanner-live-readiness-execution-quality-card">
            <p className="text-xs text-cyan-200" data-testid="user-scanner-live-readiness-execution-quality-label">Execution Quality</p>
            <p className="text-sm font-semibold" data-testid="user-scanner-live-readiness-execution-quality-value">
              latency={liveReadiness?.execution_quality?.avg_latency ?? 0}ms | reject={liveReadiness?.execution_quality?.reject_rate ?? 0}
            </p>
          </article>
        </div>

        <pre className="overflow-x-auto rounded border border-cyan-900 bg-slate-950 p-3 text-xs text-cyan-100" data-testid="user-scanner-daily-report-json">
          {JSON.stringify(scannerDailyReport || {}, null, 2)}
        </pre>
      </section>

      <section className="order-12 col-span-12" data-testid="user-scanner-results-main-section">
        <ScannerResultsTable
          results={scannerResults}
          compactMode={compactMode}
          onOpenTrade={openExecuteFromScanner}
          onViewChart={openChartFromScanner}
          onViewCard={(item) => onSelectDecisionCard(item.symbol)}
          onAddWatchlist={addWatchlistFromResult}
        />
      </section>
    </section>
  );
};