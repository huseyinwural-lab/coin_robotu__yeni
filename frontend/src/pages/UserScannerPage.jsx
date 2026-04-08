import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ScannerResultsTable } from "@/components/ScannerResultsTable";
import { Button } from "@/components/ui/button";
import { apiClient, classifyApiError } from "@/lib/api";
import { UserIndicatorScreenerPage } from "@/pages/UserIndicatorScreenerPage";
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

const AUTO_SCAN_INTERVAL_SECONDS = 60;
const PROFILE_INTERVAL_OPTIONS = [
  { value: 30, label: "30 saniye" },
  { value: 60, label: "1 dakika" },
  { value: 90, label: "1.5 dakika" },
  { value: 120, label: "2 dakika" },
];

const SIMPLE_SCANNER_V2 = true;
const PURE_LIVE_DISABLE_AUTOMATION = true;

const RUN_CHUNK_SIZE = 20;

const normalizeIntervalSeconds = (value) => {
  const allowed = new Set(PROFILE_INTERVAL_OPTIONS.map((option) => Number(option.value)));
  const parsed = Number(value || AUTO_SCAN_INTERVAL_SECONDS);
  if (allowed.has(parsed)) {
    return parsed;
  }
  if (!Number.isFinite(parsed)) {
    return AUTO_SCAN_INTERVAL_SECONDS;
  }
  if (parsed > 120) {
    return 120;
  }
  if (parsed < 30) {
    return 30;
  }
  return AUTO_SCAN_INTERVAL_SECONDS;
};

const normalizeSymbolsForRun = (symbols) => {
  const unique = Array.from(new Set((symbols || []).map((item) => String(item || "").trim().toUpperCase()).filter(Boolean)));
  return unique.filter((symbol) => symbol.endsWith("USDT") || symbol.endsWith("USDC"));
};

const chunkSymbols = (symbols, size = RUN_CHUNK_SIZE) => {
  if (!Array.isArray(symbols) || symbols.length === 0) {
    return [];
  }
  const chunks = [];
  for (let i = 0; i < symbols.length; i += size) {
    chunks.push(symbols.slice(i, i + size));
  }
  return chunks;
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
const REQUEST_TREND_MAX_WINDOW_MS = 900_000;
const REQUEST_TREND_BUCKETS = 5;
const REQUEST_TREND_OPTIONS = [5, 15];
const SCANNER_ANOMALY_TOAST_PREF_KEY = "scanner-anomaly-toast-enabled-v1";
const SCANNER_ANOMALY_SOUND_PREF_KEY = "scanner-anomaly-sound-enabled-v1";
const SCANNER_RUN_SETTINGS_KEY = "user-scanner-run-settings-v1";
const SCANNER_TOAST_DEDUPE_WINDOW_MS = 8000;

const isAnomalyEligibleEvent = (item) => {
  if (!item) {
    return false;
  }
  if (item.ok) {
    return true;
  }
  return String(item.errorClass || "").toLowerCase() === "trade_blocker";
};

const readScannerAlertPreference = (key, fallbackValue = true) => {
  if (typeof window === "undefined") {
    return fallbackValue;
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === "1") {
      return true;
    }
    if (raw === "0") {
      return false;
    }
    return fallbackValue;
  } catch {
    return fallbackValue;
  }
};

const readScannerRunSettings = () => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(SCANNER_RUN_SETTINGS_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

const buildTrendPoints = (events, windowMinutes = 5, nowTs = Date.now()) => {
  const normalizedWindowMinutes = REQUEST_TREND_OPTIONS.includes(Number(windowMinutes)) ? Number(windowMinutes) : 5;
  const totalWindowMs = normalizedWindowMinutes * 60_000;
  const bucketMs = Math.max(1, Math.floor(totalWindowMs / REQUEST_TREND_BUCKETS));
  const startTs = nowTs - totalWindowMs;
  const labelStep = Math.max(1, Math.round(normalizedWindowMinutes / REQUEST_TREND_BUCKETS));

  return Array.from({ length: REQUEST_TREND_BUCKETS }, (_, index) => {
    const bucketStart = startTs + (index * bucketMs);
    const bucketEnd = bucketStart + bucketMs;
    const bucketEventsRaw = events.filter((item) => item.timestamp >= bucketStart && item.timestamp < bucketEnd);
    const bucketEvents = bucketEventsRaw.filter((item) => isAnomalyEligibleEvent(item));
    const total = bucketEvents.length;
    const success = bucketEvents.filter((item) => item.ok).length;
    const failed = Math.max(total - success, 0);
    const successRatio = total > 0 ? success / total : 1;
    const minutesAgo = Math.max(1, normalizedWindowMinutes - (index * labelStep));
    const infraErrorCount = bucketEventsRaw.filter((item) => String(item.errorClass || "") === "infra_error").length;
    const authErrorCount = bucketEventsRaw.filter((item) => String(item.errorClass || "") === "auth_error").length;

    const endpointMap = bucketEvents.reduce((acc, item) => {
      const endpoint = String(item.endpoint || "unknown_endpoint");
      const current = acc.get(endpoint) || { endpoint, total: 0, success: 0, fail: 0 };
      current.total += 1;
      if (item.ok) {
        current.success += 1;
      } else {
        current.fail += 1;
      }
      acc.set(endpoint, current);
      return acc;
    }, new Map());

    const endpointBreakdown = Array.from(endpointMap.values())
      .map((row) => ({
        ...row,
        successRatio: row.total > 0 ? row.success / row.total : 1,
      }))
      .sort((a, b) => {
        if (b.fail !== a.fail) return b.fail - a.fail;
        if (b.total !== a.total) return b.total - a.total;
        return String(a.endpoint).localeCompare(String(b.endpoint));
      });

    return {
      key: `m${index}`,
      label: `${minutesAgo}m`,
      total,
      success,
      failed,
      successRatio,
      excluded: Math.max(bucketEventsRaw.length - bucketEvents.length, 0),
      infra_error_count: infraErrorCount,
      auth_error_count: authErrorCount,
      endpoint_breakdown: endpointBreakdown,
      most_impacted_endpoint: endpointBreakdown[0]?.endpoint || null,
    };
  });
};

const summarizeEndpointBreakdown = (events, { windowMs = 60_000, nowTs = Date.now() } = {}) => {
  const threshold = nowTs - windowMs;
  const scopedRaw = events.filter((item) => Number(item.timestamp || 0) >= threshold);
  const scoped = scopedRaw.filter((item) => isAnomalyEligibleEvent(item));
  const endpointMap = scoped.reduce((acc, item) => {
    const endpoint = String(item.endpoint || "unknown_endpoint");
    const current = acc.get(endpoint) || { endpoint, total: 0, success: 0, fail: 0 };
    current.total += 1;
    if (item.ok) {
      current.success += 1;
    } else {
      current.fail += 1;
    }
    acc.set(endpoint, current);
    return acc;
  }, new Map());

  const rows = Array.from(endpointMap.values())
    .map((row) => ({
      ...row,
      successRatio: row.total > 0 ? row.success / row.total : 1,
    }))
    .sort((a, b) => {
      if (b.fail !== a.fail) return b.fail - a.fail;
      if (b.total !== a.total) return b.total - a.total;
      return String(a.endpoint).localeCompare(String(b.endpoint));
    });

  const total = scoped.length;
  const success = scoped.filter((item) => item.ok).length;
  const failed = Math.max(total - success, 0);
  const successRatio = total > 0 ? success / total : 1;
  const infraErrorCount = scopedRaw.filter((item) => String(item.errorClass || "") === "infra_error").length;
  const authErrorCount = scopedRaw.filter((item) => String(item.errorClass || "") === "auth_error").length;

  return {
    rows,
    total,
    success,
    failed,
    successRatio,
    excluded: Math.max(scopedRaw.length - scoped.length, 0),
    infraErrorCount,
    authErrorCount,
    mostImpactedEndpoint: rows[0]?.endpoint || null,
  };
};

const toApiErrorMessage = (error, fallback = "İşlem başarısız") => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parsed = detail
      .map((item) => {
        if (!item) return "";
        if (typeof item === "string") return item;
        if (typeof item === "object") {
          return item.msg || item.message || item.type || "";
        }
        return String(item);
      })
      .filter(Boolean)
      .join(" | ");
    if (parsed) {
      return parsed;
    }
  }
  if (detail && typeof detail === "object") {
    return detail.message || detail.msg || detail.code || fallback;
  }
  const generic = error?.message || error?.response?.statusText;
  return generic || fallback;
};

const deriveRequestHealth = (events) => {
  const eligible = events.filter((event) => isAnomalyEligibleEvent(event));
  const total = eligible.length;
  const success = eligible.filter((event) => event.ok).length;
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [mode, setMode] = useState("ASSISTED");
  const [marketType, setMarketType] = useState("spot");
  const [overview, setOverview] = useState(null);
  const [scannerResults, setScannerResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);
  const [symbolSource, setSymbolSource] = useState("crypto");
  const [symbolMode, setSymbolMode] = useState("manual_selection");
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
  const [schedulerState, setSchedulerState] = useState(null);
  const [scannerLoadDegraded, setScannerLoadDegraded] = useState(false);
  const [scannerLoadFailures, setScannerLoadFailures] = useState([]);
  const [decisionCards, setDecisionCards] = useState([]);
  const [selectedDecisionSymbol, setSelectedDecisionSymbol] = useState("");
  const [isExplainabilityDrawerOpen, setIsExplainabilityDrawerOpen] = useState(false);
  const [symbolExplainability, setSymbolExplainability] = useState(null);
  const [isExplainabilityLoading, setIsExplainabilityLoading] = useState(false);
  const [isSavingAutomation, setIsSavingAutomation] = useState(false);
  const [selectionSavedAt, setSelectionSavedAt] = useState(null);
  const [scannerSeedTriggered, setScannerSeedTriggered] = useState(false);
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
  const [selectedTrendWindowMinutes, setSelectedTrendWindowMinutes] = useState(5);
  const [scannerSection, setScannerSection] = useState(SIMPLE_SCANNER_V2 ? "results" : (searchParams.get("section") === "screener" ? "screener" : "results"));
  const [scannerTemplates, setScannerTemplates] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [lastRunEnvelope, setLastRunEnvelope] = useState(null);
  const [lastRunStartBotReport, setLastRunStartBotReport] = useState(null);
  const [requestTrend, setRequestTrend] = useState(() => buildTrendPoints([], 5));
  const [requestEndpointBreakdown, setRequestEndpointBreakdown] = useState({
    oneMinute: summarizeEndpointBreakdown([], { windowMs: 60_000 }),
    fiveMinute: summarizeEndpointBreakdown([], { windowMs: 300_000 }),
  });
  const [requestErrorBreakdown, setRequestErrorBreakdown] = useState({
    auth_error: 0,
    infra_error: 0,
    trade_blocker: 0,
  });
  const [scannerEngineConfig, setScannerEngineConfig] = useState({
    exchange: "binance",
    include_spot: true,
    include_futures: true,
    market_scope: {
      spot_mode: "all",
      futures_mode: "all",
    },
    signal_mode: "manual",
    auto_interval_minutes: 3,
    scan_limit: 2000,
    top_n: 20,
    manual_symbols: [],
    weights: {
      trend: 10,
      volume: 50,
      momentum: 100,
      bollinger: 1,
      max_score: 161,
    },
  });
  const [scannerEngineManualSymbols, setScannerEngineManualSymbols] = useState("");
  const [scannerEngineRun, setScannerEngineRun] = useState({
    status: "empty",
    summary: {
      max_score: 161,
      candidate_count: 0,
      scored_count: 0,
      strong_long_count: 0,
      strong_short_count: 0,
    },
    results: [],
    top_results: [],
    errors: [],
  });
  const [scannerEngineDecisionMap, setScannerEngineDecisionMap] = useState({});
  const [scannerEngineBusy, setScannerEngineBusy] = useState(false);
  const [scannerFailureSummary, setScannerFailureSummary] = useState({
    auth_error: 0,
    infra_error: 0,
    trade_blocker: 0,
  });
  const [anomalyToastEnabled, setAnomalyToastEnabled] = useState(() => readScannerAlertPreference(SCANNER_ANOMALY_TOAST_PREF_KEY, true));
  const [anomalySoundEnabled, setAnomalySoundEnabled] = useState(() => readScannerAlertPreference(SCANNER_ANOMALY_SOUND_PREF_KEY, true));
  const [hoveredTrendPointKey, setHoveredTrendPointKey] = useState(null);
  const profileRunTrackerRef = useRef({});
  const symbolPersistTimerRef = useRef(null);
  const minimalFiltersRef = useRef(MINIMAL_FILTER_DEFAULTS);
  const rotatingScanWindowRef = useRef(0);
  const requestWindowRef = useRef([]);
  const requestTrendRef = useRef([]);
  const selectedTrendWindowRef = useRef(5);
  const anomalyAlertArmedRef = useRef(false);
  const scannerToastTrackerRef = useRef(new Map());
  const initialFullLoadDoneRef = useRef(false);

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

  const scannerEngineNextRunAt = useMemo(() => {
    if (String(scannerEngineConfig?.signal_mode || "manual") !== "auto") {
      return schedulerState?.next_run_at || activeAutomation?.next_run_at || null;
    }
    const baseRaw = scannerEngineRun?.generated_at || activeAutomation?.last_run_at || overview?.latest_generated_at;
    if (!baseRaw) {
      return null;
    }
    const baseDate = new Date(baseRaw);
    if (Number.isNaN(baseDate.getTime())) {
      return null;
    }
    const minutes = [1, 3, 5].includes(Number(scannerEngineConfig?.auto_interval_minutes))
      ? Number(scannerEngineConfig?.auto_interval_minutes)
      : 3;
    return new Date(baseDate.getTime() + (minutes * 60 * 1000)).toISOString();
  }, [
    activeAutomation?.last_run_at,
    activeAutomation?.next_run_at,
    overview?.latest_generated_at,
    scannerEngineConfig?.auto_interval_minutes,
    scannerEngineConfig?.signal_mode,
    scannerEngineRun?.generated_at,
    schedulerState?.next_run_at,
  ]);

  const scannerEngineDecisionApprovalMap = useMemo(() => {
    const rows = scannerEngineRun?.results || [];
    const map = { ...(scannerEngineDecisionMap || {}) };
    rows.forEach((item) => {
      const symbol = String(item?.symbol || "").toUpperCase();
      if (!symbol) {
        return;
      }
      if (item?.decisions && typeof item.decisions === "object") {
        map[symbol] = item.decisions;
      }
    });
    return map;
  }, [scannerEngineDecisionMap, scannerEngineRun?.results]);

  const requestTrendPolylinePoints = useMemo(() => {
    const width = 160;
    const height = 32;
    if (!requestTrend.length) {
      return [];
    }
    return requestTrend.map((point, index) => {
      const x = requestTrend.length === 1 ? 0 : (index / (requestTrend.length - 1)) * width;
      const normalized = Math.max(0, Math.min(1, Number(point.successRatio || 0)));
      const y = height - (normalized * height);
      return {
        ...point,
        x,
        y,
        fail: Math.max(Number(point.total || 0) - Number(point.success || 0), 0),
      };
    });
  }, [requestTrend]);

  const requestTrendPolylinePath = useMemo(() => {
    if (!requestTrendPolylinePoints.length) {
      return "";
    }
    return requestTrendPolylinePoints.map((point) => {
      return `${point.x},${point.y}`;
    }).join(" ");
  }, [requestTrendPolylinePoints]);

  const latestTrendPoint = requestTrendPolylinePoints[requestTrendPolylinePoints.length - 1] || null;
  const hoveredTrendPoint = useMemo(
    () => requestTrendPolylinePoints.find((point) => point.key === hoveredTrendPointKey) || null,
    [hoveredTrendPointKey, requestTrendPolylinePoints],
  );
  const trendDetailPoint = hoveredTrendPoint || latestTrendPoint;

  const latestFailRatio = requestHealth.total > 0
    ? Number((requestHealth.failed / requestHealth.total).toFixed(4))
    : 0;
  const hasAnomaly = Boolean(requestHealth.total > 0 && latestFailRatio > 0.1);

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

  const formatEndpointLabel = (value) => String(value || "unknown_endpoint").replaceAll("_", " ");
  const endpointFailRatio = (row) => {
    const total = Number(row?.total || 0);
    if (total <= 0) {
      return 0;
    }
    return Math.max(0, Math.min(1, Number(row?.fail || 0) / total));
  };

  useEffect(() => {
    minimalFiltersRef.current = minimalFilters;
  }, [minimalFilters]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(SCANNER_ANOMALY_TOAST_PREF_KEY, anomalyToastEnabled ? "1" : "0");
      window.localStorage.setItem(SCANNER_ANOMALY_SOUND_PREF_KEY, anomalySoundEnabled ? "1" : "0");
    } catch {
      // noop
    }
  }, [anomalySoundEnabled, anomalyToastEnabled]);

  const emitScannerToast = useCallback((level, key, message) => {
    if (!message) {
      return;
    }
    const now = Date.now();
    const previous = scannerToastTrackerRef.current.get(key) || 0;
    if (now - previous < SCANNER_TOAST_DEDUPE_WINDOW_MS) {
      return;
    }
    scannerToastTrackerRef.current.set(key, now);
    const notifier = toast[level] || toast.info;
    notifier(message, { id: key });
  }, []);

  const updateRequestHealthWindow = useCallback((settledResponses = []) => {
    const now = Date.now();
    const retained = (requestWindowRef.current || []).filter((item) => now - item.timestamp <= REQUEST_HEALTH_WINDOW_MS);
    const incoming = Array.isArray(settledResponses)
      ? settledResponses.map((item) => {
        const ok = item?.status === "fulfilled";
        const reason = ok ? null : item?.reason;
        return {
          timestamp: now,
          ok,
          endpoint: String(item?.endpoint || item?.meta?.endpoint || "unknown_endpoint"),
          statusCode: ok ? Number(item?.value?.status || 200) : Number(reason?.response?.status || 0),
          errorCode: ok ? "" : String(reason?.response?.data?.code || "").toUpperCase(),
          errorClass: ok ? "success" : classifyApiError(reason),
        };
      })
      : [];
    const merged = [...retained, ...incoming];
    requestWindowRef.current = merged;

    const retainedTrend = (requestTrendRef.current || []).filter((item) => now - item.timestamp <= REQUEST_TREND_MAX_WINDOW_MS);
    const mergedTrend = [...retainedTrend, ...incoming];
    requestTrendRef.current = mergedTrend;

    const metrics = deriveRequestHealth(merged);
    setRequestHealth({
      ...metrics,
      windowSeconds: 60,
      updatedAt: new Date(now).toISOString(),
    });
    setRequestTrend(buildTrendPoints(mergedTrend, selectedTrendWindowRef.current, now));
    setRequestEndpointBreakdown({
      oneMinute: summarizeEndpointBreakdown(mergedTrend, { windowMs: 60_000, nowTs: now }),
      fiveMinute: summarizeEndpointBreakdown(mergedTrend, { windowMs: 300_000, nowTs: now }),
    });

    const latestFailures = merged.filter((item) => !item.ok);
    setRequestErrorBreakdown({
      auth_error: latestFailures.filter((item) => String(item.errorClass || "") === "auth_error").length,
      infra_error: latestFailures.filter((item) => String(item.errorClass || "") === "infra_error").length,
      trade_blocker: latestFailures.filter((item) => String(item.errorClass || "") === "trade_blocker").length,
    });
  }, []);

  const playAnomalyAlertBeep = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }
    const AudioContextRef = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextRef) {
      return;
    }
    try {
      const ctx = new AudioContextRef();
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = 860;
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.09, ctx.currentTime + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.24);
      oscillator.start();
      oscillator.stop(ctx.currentTime + 0.25);
      setTimeout(() => {
        ctx.close().catch(() => {});
      }, 350);
    } catch {
      // noop
    }
  }, []);

  useEffect(() => {
    const now = Date.now();
    selectedTrendWindowRef.current = selectedTrendWindowMinutes;
    setRequestTrend(buildTrendPoints(requestTrendRef.current || [], selectedTrendWindowMinutes, now));
  }, [selectedTrendWindowMinutes]);

  useEffect(() => {
    if (!hasAnomaly) {
      anomalyAlertArmedRef.current = false;
      return;
    }
    if (anomalyAlertArmedRef.current) {
      return;
    }
    anomalyAlertArmedRef.current = true;
    if (anomalyToastEnabled) {
      emitScannerToast(
        "error",
        "scanner-trade-anomaly-alert",
        `Anomaly tespit edildi (trade_blocker): son 1 dakikada fail oranı %${(latestFailRatio * 100).toFixed(1)}`,
      );
    }
    if (anomalySoundEnabled) {
      playAnomalyAlertBeep();
    }
    apiClient.post("/user/scanner/runtime/anomaly-event", {
      source: "scanner_ui",
      fail_ratio: latestFailRatio,
      total_requests: requestHealth.total,
      failed_requests: requestHealth.failed,
      success_requests: requestHealth.success,
      trend_window_minutes: selectedTrendWindowMinutes,
      trend_points: requestTrendPolylinePoints.map((point) => ({
        label: point.label,
        total: point.total,
        success: point.success,
        fail: point.fail,
        success_ratio: Number((point.successRatio || 0).toFixed(4)),
      })),
    }).catch(() => {
      // audit write best effort
    });
  }, [
    anomalySoundEnabled,
    anomalyToastEnabled,
    emitScannerToast,
    hasAnomaly,
    latestFailRatio,
    playAnomalyAlertBeep,
    requestHealth.failed,
    requestHealth.success,
    requestHealth.total,
    requestTrendPolylinePoints,
    selectedTrendWindowMinutes,
  ]);

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
      toast.error(toApiErrorMessage(error, "Explainability yüklenemedi"));
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
        symbol_selection_mode: SIMPLE_SCANNER_V2 ? "manual_selection" : (watchlistOnly ? "manual_selection" : symbolMode),
        selected_symbols: selectedSymbols,
      });
      setAutomationConfig(data || null);
      if (withToast) {
        toast.success(nextEnabled ? "3 dakikalık otomatik scanner aktif" : "Otomatik scanner kapatıldı");
      }
      return data;
    } catch (error) {
      toast.error(toApiErrorMessage(error, "Otomasyon ayarı kaydedilemedi"));
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
        symbol_selection_mode: SIMPLE_SCANNER_V2 ? "manual_selection" : (watchlistOnly ? "manual_selection" : symbolMode),
        selected_symbols: selectedSymbols,
      });
      setAutomationProfiles((prev) => prev.map((item) => (item.id === data.id ? data : { ...item, is_active: false })));
      setActiveProfileId(data.id);
      if (withToast) {
        toast.success(nextEnabled ? `Profil güncellendi: ${data.name}` : `Profil pasif: ${data.name}`);
      }
      return data;
    } catch (error) {
      toast.error(toApiErrorMessage(error, "Profil kaydedilemedi"));
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
        symbol_selection_mode: SIMPLE_SCANNER_V2 ? "manual_selection" : (watchlistOnly ? "manual_selection" : symbolMode),
        selected_symbols: selectedSymbols,
      });
      setProfileNameInput("");
      await load({ hydrateSelection: true, notifyAutoRuns: false });
      toast.success("Otomasyon profili oluşturuldu");
    } catch (error) {
      toast.error(toApiErrorMessage(error, "Profil oluşturulamadı"));
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
      toast.error(toApiErrorMessage(error, "Profil aktif edilemedi"));
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
      toast.error(toApiErrorMessage(error, "Profil silinemedi"));
    } finally {
      setIsSavingAutomation(false);
    }
  };

  const load = useCallback(async ({ hydrateSelection = false, silent = false, notifyAutoRuns = false } = {}) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const requestDescriptors = SIMPLE_SCANNER_V2
        ? [
            { key: "signal_mode", request: apiClient.get("/user/signal-mode", { timeout: 8000 }) },
            { key: "scanner_overview", request: apiClient.get("/user/scanner", { timeout: 12000 }) },
            {
              key: "scanner_results",
              request: apiClient.get("/screener", {
                params: {
                  limit: 120,
                  filters: JSON.stringify(compactMinimalFilters(minimalFiltersRef.current)),
                },
                timeout: 12000,
              }),
            },
            { key: "strategy_templates", request: apiClient.get("/strategy-templates", { timeout: 15000 }) },
            { key: "scanner_automation", request: apiClient.get("/user/scanner/automation", { timeout: 12000 }) },
            { key: "symbol_selection", request: apiClient.get("/user/scanner/symbol-selection", { params: { scanner_id: "default" }, timeout: 12000 }) },
            { key: "scanner_engine_config", request: apiClient.get("/user/scanner-engine/config", { timeout: 12000 }) },
            { key: "scanner_engine_last_run", request: apiClient.get("/user/scanner-engine/last-run", { timeout: 15000 }) },
            { key: "scanner_engine_decision_map", request: apiClient.get("/user/scanner-engine/decision-map", { timeout: 12000 }) },
            { key: "scheduler_next_run", request: apiClient.get("/user/live/scheduler/next-run", { timeout: 12000 }) },
          ]
        : [
            { key: "signal_mode", request: apiClient.get("/user/signal-mode", { timeout: 12000 }) },
            { key: "scanner_overview", request: apiClient.get("/user/scanner", { timeout: 12000 }) },
            {
              key: "scanner_results",
              request: apiClient.get("/screener", {
                params: {
                  limit: 80,
                  filters: JSON.stringify(compactMinimalFilters(minimalFiltersRef.current)),
                },
                timeout: 10000,
              }),
            },
            { key: "strategy_templates", request: apiClient.get("/strategy-templates", { timeout: 15000 }) },
            { key: "scanner_automation", request: apiClient.get("/user/scanner/automation", { timeout: 12000 }) },
            { key: "scanner_profiles", request: apiClient.get("/user/scanner/automation-profiles", { timeout: 12000 }) },
            { key: "decision_cards", request: apiClient.get("/user/decision-cards", { params: { limit: 60 }, timeout: 12000 }) },
            { key: "symbol_selection", request: apiClient.get("/user/scanner/symbol-selection", { params: { scanner_id: "default" }, timeout: 12000 }) },
            { key: "runtime_snapshot", request: apiClient.get("/user/scanner/runtime/snapshot", { timeout: 12000 }) },
            { key: "live_readiness", request: apiClient.get("/user/scanner/runtime/live-readiness", { params: { window: "24h" }, timeout: 12000 }) },
            { key: "daily_report", request: apiClient.get("/user/scanner/runtime/daily-report", { params: { window: "24h" }, timeout: 12000 }) },
            { key: "scanner_engine_config", request: apiClient.get("/user/scanner-engine/config", { timeout: 12000 }) },
            { key: "scanner_engine_last_run", request: apiClient.get("/user/scanner-engine/last-run", { timeout: 15000 }) },
            { key: "scanner_engine_decision_map", request: apiClient.get("/user/scanner-engine/decision-map", { timeout: 12000 }) },
            { key: "scheduler_next_run", request: apiClient.get("/user/live/scheduler/next-run", { timeout: 12000 }) },
          ];
      const responses = await Promise.allSettled(requestDescriptors.map((entry) => entry.request));
      const responsesWithEndpointMeta = responses.map((entry, index) => ({
        ...entry,
        endpoint: requestDescriptors[index]?.key,
      }));

      updateRequestHealthWindow(responsesWithEndpointMeta);

      const failedIndexes = responses
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => item.status === "rejected")
        .map(({ index }) => index);

      const failedEntries = failedIndexes
        .map((index) => {
          const key = requestDescriptors[index]?.key;
          const reason = responses[index]?.reason;
          if (!key) {
            return null;
          }
          return {
            key,
            errorClass: classifyApiError(reason),
            status: Number(reason?.response?.status || 0),
          };
        })
        .filter(Boolean);

      const failedKeys = failedEntries.map((entry) => entry.key);
      const failureSummary = {
        auth_error: failedEntries.filter((entry) => entry.errorClass === "auth_error").length,
        infra_error: failedEntries.filter((entry) => entry.errorClass === "infra_error").length,
        trade_blocker: failedEntries.filter((entry) => entry.errorClass === "trade_blocker").length,
      };
      const infraErrorKeys = failedEntries
        .filter((entry) => entry.errorClass === "infra_error")
        .map((entry) => `${entry.key}${entry.status ? `(${entry.status})` : ""}`);
      const authErrorKeys = failedEntries
        .filter((entry) => entry.errorClass === "auth_error")
        .map((entry) => `${entry.key}${entry.status ? `(${entry.status})` : ""}`);

      const criticalTradeBlockerKeys = (SIMPLE_SCANNER_V2
        ? failedEntries.filter((entry) => entry.key !== "strategy_templates")
        : failedEntries
      )
        .filter((entry) => entry.errorClass === "trade_blocker")
        .map((entry) => entry.key);

      setScannerLoadFailures(failedKeys);
      setScannerFailureSummary(failureSummary);
      setScannerLoadDegraded(failedEntries.length > 0);

      if (!silent && failedEntries.length > 0) {
        if (failureSummary.trade_blocker > 0 && criticalTradeBlockerKeys.length > 0) {
          emitScannerToast(
            "error",
            "scanner-load-trade-blocker",
            `Scanner kısmi yüklendi (trade blocker): ${criticalTradeBlockerKeys.join(", ")}`,
          );
        }
        if (failureSummary.infra_error > 0) {
          emitScannerToast(
            "warning",
            "scanner-load-infra-error",
            `Altyapı sorunu: ${infraErrorKeys.slice(0, 5).join(", ") || `${failureSummary.infra_error} endpoint`} (anomaly hariç).`,
          );
        }
        if (failureSummary.auth_error > 0) {
          emitScannerToast(
            "warning",
            "scanner-load-auth-error",
            `Auth sorunu: ${authErrorKeys.slice(0, 5).join(", ") || `${failureSummary.auth_error} endpoint`} (anomaly hariç).`,
          );
        }
      }

      const byKey = requestDescriptors.reduce((acc, descriptor, index) => {
        const result = responses[index];
        acc[descriptor.key] = result?.status === "fulfilled" ? result.value : null;
        return acc;
      }, {});

      const modeRes = byKey.signal_mode;
      const overviewRes = byKey.scanner_overview;
      const resultsRes = byKey.scanner_results;
      const templatesRes = byKey.strategy_templates;
      const automationRes = byKey.scanner_automation;
      const profilesRes = byKey.scanner_profiles;
      const cardsRes = byKey.decision_cards;
      const persistedSelectionRes = byKey.symbol_selection;
      const runtimeRes = byKey.runtime_snapshot;
      const readinessRes = byKey.live_readiness;
      const dailyRes = byKey.daily_report;
      const schedulerRes = byKey.scheduler_next_run;
      const scannerEngineDecisionMapRes = byKey.scanner_engine_decision_map;
      const scannerEngineConfigRes = byKey.scanner_engine_config;
      const scannerEngineRunRes = byKey.scanner_engine_last_run;

      setMode((prev) => modeRes?.data?.mode || prev || "ASSISTED");
      setOverview((prev) => overviewRes?.data || prev || null);
      const nextScannerResults = Array.isArray(resultsRes?.data) ? resultsRes.data : [];
      setScannerResults((prev) => nextScannerResults || prev || []);
      const activeTemplates = (templatesRes?.data || []).filter((item) => item.is_active);
      setScannerTemplates(activeTemplates);
      setSelectedTemplateId((prev) => prev || activeTemplates[0]?.id || "");
      const automation = automationRes?.data || null;
      const profiles = profilesRes?.data || [];
      setAutomationConfig(automation);
      setAutomationProfiles(profiles);
      const cards = cardsRes?.data?.items || [];
      const persistedSelection = persistedSelectionRes?.data || null;
      setRuntimeSnapshot((prev) => runtimeRes?.data || prev || null);
      setLiveReadiness((prev) => readinessRes?.data || prev || null);
      setScannerDailyReport((prev) => dailyRes?.data || prev || null);
      setSchedulerState((prev) => schedulerRes?.data || prev || null);
      setScannerEngineDecisionMap(() => (scannerEngineDecisionMapRes?.data?.items && typeof scannerEngineDecisionMapRes?.data?.items === "object")
        ? scannerEngineDecisionMapRes.data.items
        : {});
      const nextConfig = scannerEngineConfigRes?.data || {};
      setScannerEngineConfig((prev) => ({ ...prev, ...nextConfig }));
      setScannerEngineManualSymbols((prev) => (prev ? prev : (nextConfig?.manual_symbols || []).join(",")));
      setScannerEngineRun(scannerEngineRunRes?.data || {
        status: "empty",
        summary: { max_score: 161, candidate_count: 0, scored_count: 0, strong_long_count: 0, strong_short_count: 0 },
        results: [],
        top_results: [],
        errors: [],
      });
      setDecisionCards(cards);

      if (!silent && nextScannerResults.length === 0 && !scannerSeedTriggered) {
        try {
          const seedSymbols = Array.isArray(selectedSymbols) && selectedSymbols.length > 0
            ? selectedSymbols.slice(0, 8)
            : ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"];
          await apiClient.post(
            "/user/scanner/run-async",
            {
              mode: mode || "ASSISTED",
              max_results: 40,
              symbol_source: symbolSource || "crypto",
              market_type: marketType || "spot",
              symbol_selection_mode: "manual_selection",
              selected_symbols: seedSymbols,
            },
            { timeout: 12000 },
          );
          setScannerSeedTriggered(true);
          toast.info("Scanner sonuçları boştu; otomatik seed run tetiklendi.");
        } catch {
          // Seed trigger başarısız olsa da normal load devam eder
        }
      }

      if (cards.length > 0) {
        const selectedSymbol = selectedDecisionSymbol || cards[0].symbol;
        setSelectedDecisionSymbol(selectedSymbol);
        loadSymbolExplainability(selectedSymbol);
      } else {
        setSelectedDecisionSymbol("");
        setSymbolExplainability(null);
      }
      syncAutoRunNotifications(profiles, { notify: notifyAutoRuns });

      if (hydrateSelection) {
        const localRunSettings = readScannerRunSettings();
        const selectedProfile = profiles.find((item) => item.is_active) || profiles[0] || null;
        if (selectedProfile) {
          setActiveProfileId(selectedProfile.id);
          setProfileIntervalInput(normalizeIntervalSeconds(selectedProfile.interval_seconds));
            setAutoScanInterval(normalizeIntervalSeconds(selectedProfile.interval_seconds));
          setSymbolSource(selectedProfile.symbol_source || "crypto");
          setSymbolMode(selectedProfile.symbol_selection_mode || (SIMPLE_SCANNER_V2 ? "manual_selection" : "all_market_symbols"));
          setSelectedSymbols(Array.isArray(selectedProfile.selected_symbols) ? selectedProfile.selected_symbols : []);
        } else if (automation) {
          setActiveProfileId("");
            setAutoScanInterval(normalizeIntervalSeconds(automation.interval_seconds));
          setSymbolSource(automation.symbol_source || "crypto");
          setSymbolMode(automation.symbol_selection_mode || (SIMPLE_SCANNER_V2 ? "manual_selection" : "all_market_symbols"));
          setSelectedSymbols(Array.isArray(automation.selected_symbols) ? automation.selected_symbols : []);
        }
        if (persistedSelection) {
          setSymbolSource(persistedSelection.symbol_source || "crypto");
          setSymbolMode(persistedSelection.symbol_selection_mode || (SIMPLE_SCANNER_V2 ? "manual_selection" : "all_market_symbols"));
          setSelectedSymbols(Array.isArray(persistedSelection.selected_symbols) ? persistedSelection.selected_symbols : []);
          setSelectionSavedAt(persistedSelection.saved_at || null);
        }
        if (localRunSettings) {
          if (localRunSettings.mode) {
            setMode(String(localRunSettings.mode).toUpperCase());
          }
          if (localRunSettings.marketType) {
            setMarketType(String(localRunSettings.marketType).toLowerCase());
          }
          if (typeof localRunSettings.watchlistOnly === "boolean") {
            setWatchlistOnly(Boolean(localRunSettings.watchlistOnly));
          }
        }
          const normalizedMode = String((persistedSelection?.symbol_selection_mode || selectedProfile?.symbol_selection_mode || automation?.symbol_selection_mode || (SIMPLE_SCANNER_V2 ? "manual_selection" : "all_market_symbols"))).toLowerCase();
          setWatchlistOnly(normalizedMode === "manual_selection" && Array.isArray(persistedSelection?.selected_symbols || selectedProfile?.selected_symbols || automation?.selected_symbols) && (persistedSelection?.selected_symbols || selectedProfile?.selected_symbols || automation?.selected_symbols || []).length > 0);
        if (SIMPLE_SCANNER_V2) {
          setSymbolMode("manual_selection");
        }
        setSelectionHydrated(true);
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  }, [
    emitScannerToast,
    marketType,
    mode,
    scannerSeedTriggered,
    selectedDecisionSymbol,
    selectedSymbols,
    symbolSource,
    updateRequestHealthWindow,
  ]);

  useEffect(() => {
    const timer = setInterval(() => {
      updateRequestHealthWindow([]);
    }, 5000);
    return () => clearInterval(timer);
  }, [updateRequestHealthWindow]);

  useEffect(() => {
    if (initialFullLoadDoneRef.current) {
      return;
    }
    initialFullLoadDoneRef.current = true;
    load({ hydrateSelection: true });
  }, [load]);

  useEffect(() => {
    if (!selectionHydrated || typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(
        SCANNER_RUN_SETTINGS_KEY,
        JSON.stringify({
          mode: String(mode || "ASSISTED").toUpperCase(),
          marketType: String(marketType || "spot").toLowerCase(),
          watchlistOnly: Boolean(watchlistOnly),
        }),
      );
    } catch {
      // noop
    }
  }, [selectionHydrated, mode, marketType, watchlistOnly]);

  useEffect(() => {
    if (!selectionHydrated) {
      return;
    }
    load({ silent: true, notifyAutoRuns: false });
  }, [selectionHydrated, minimalFilters, load]);

  useEffect(() => {
    const intervalMs = SIMPLE_SCANNER_V2 ? 30_000 : 10_000;
    const timer = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      load({ silent: true, notifyAutoRuns: true });
    }, intervalMs);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (PURE_LIVE_DISABLE_AUTOMATION || !SIMPLE_SCANNER_V2 || !selectionHydrated || !activeAutomation?.id) {
      return;
    }
    if (String(activeAutomation.symbol_selection_mode || "").toLowerCase() === "manual_selection") {
      return;
    }

    let cancelled = false;
    const normalizeAutomationMode = async () => {
      try {
        await apiClient.put("/user/scanner/automation", {
          auto_enabled: Boolean(activeAutomation.auto_enabled),
          interval_seconds: Number(activeAutomation.interval_seconds || autoScanInterval || AUTO_SCAN_INTERVAL_SECONDS),
          max_results: Number(activeAutomation.max_results || 120),
          symbol_source: symbolSource,
          symbol_selection_mode: "manual_selection",
          selected_symbols: selectedSymbols,
        });
        if (!cancelled) {
          setAutomationConfig((prev) => (prev ? { ...prev, symbol_selection_mode: "manual_selection" } : prev));
          setAutomationProfiles((prev) => prev.map((item) => (
            item.id === activeAutomation?.id
              ? { ...item, symbol_selection_mode: "manual_selection" }
              : item
          )));
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(toApiErrorMessage(error, "Automation modu manual_selection olarak sabitlenemedi"));
        }
      }
    };

    normalizeAutomationMode();
    return () => {
      cancelled = true;
    };
  }, [activeAutomation?.id, activeAutomation?.symbol_selection_mode, activeAutomation?.auto_enabled, activeAutomation?.interval_seconds, activeAutomation?.max_results, autoScanInterval, selectedSymbols, selectionHydrated, symbolSource]);

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
          symbol_selection_mode: SIMPLE_SCANNER_V2 ? "manual_selection" : (watchlistOnly ? "manual_selection" : symbolMode),
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
    const validSymbols = normalizeSymbolsForRun(selectedSymbols || []);
    if (validSymbols.length === 0) {
      toast.error("İşlem için en az bir geçerli USDT/USDC market seçmelisiniz.");
      return false;
    }
    return true;
  };

  const executeScannerRunWithChunks = async ({ runMode, maxResults, effectiveMode, selectedForRun, targetMarketType = marketType }) => {
    const runScannerAsync = async (requestPayload) => {
      const normalizedMarketType = String(requestPayload?.market_type || "spot").toLowerCase();
      const endpoint = normalizedMarketType === "both" ? "/user/scanner/run-async-both" : "/user/scanner/run-async";
      const { data: queued } = await apiClient.post(endpoint, requestPayload, { timeout: 12000 });
      const jobId = String(queued?.job_id || "").trim();
      if (!jobId) {
        throw new Error("scanner_async_job_id_missing");
      }

      const deadline = Date.now() + 180_000;
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const { data: job } = await apiClient.get(`/user/scanner/run-async/${jobId}`, { timeout: 10000 });
        const status = String(job?.status || "").toLowerCase();
        if (status === "completed") {
          return job?.result || {};
        }
        if (status === "failed") {
          throw new Error(String(job?.error || "scanner_run_async_failed"));
        }
      }

      throw new Error("scanner_run_async_timeout");
    };

    const symbols = normalizeSymbolsForRun(selectedForRun || []);
    const isChunked = SIMPLE_SCANNER_V2 && targetMarketType !== "both" && effectiveMode === "manual_selection" && symbols.length > RUN_CHUNK_SIZE;

    if (!isChunked) {
      const data = await runScannerAsync({
        mode: runMode,
        max_results: maxResults,
        symbol_source: symbolSource,
        market_type: targetMarketType,
        symbol_selection_mode: effectiveMode,
        selected_symbols: symbols,
        strategy_template_id: selectedTemplateId || null,
      });
      return data;
    }

    const chunks = chunkSymbols(symbols, RUN_CHUNK_SIZE);
    const windowIndex = rotatingScanWindowRef.current % chunks.length;
    const selectedWindow = chunks[windowIndex] || chunks[0] || [];
    rotatingScanWindowRef.current = (windowIndex + 1) % chunks.length;

    const data = await runScannerAsync({
      mode: runMode,
      max_results: Math.min(40, Math.max(10, maxResults)),
      symbol_source: symbolSource,
      market_type: targetMarketType,
      symbol_selection_mode: "manual_selection",
      selected_symbols: selectedWindow,
      strategy_template_id: selectedTemplateId || null,
    });

    const warnings = Array.isArray(data?.warnings) ? [...data.warnings.map((item) => String(item || ""))] : [];
    warnings.push(`rotating_window:${windowIndex + 1}/${chunks.length}`);

    return {
      run_id: data?.run_id || null,
      mode: runMode,
      market_type: targetMarketType,
      symbol_selection_mode: "manual_selection",
      selected_symbols: symbols,
      scanned_window_symbols: selectedWindow,
      result_count: Number(data?.result_count || 0),
      actionable_count: Number(data?.actionable_count || 0),
      non_tradeable_count: Number(data?.non_tradeable_count || 0),
      queued_count: Number(data?.queued_count || 0),
      pending_total: Number(data?.pending_total || 0),
      warnings,
      chunked: true,
      chunk_count: chunks.length,
      chunk_success_count: 1,
      chunk_index: windowIndex + 1,
    };
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
      toast.error(toApiErrorMessage(error, "Watchlist güncellenemedi"));
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
      toast.error(toApiErrorMessage(error, "Scanner rapor export başarısız"));
    }
  };

  const saveScannerEngineConfig = async () => {
    setScannerEngineBusy(true);
    try {
      const manualSymbols = scannerEngineManualSymbols
        .split(/[\s,;]+/)
        .map((item) => String(item || "").trim().toUpperCase())
        .filter(Boolean);

      const includeSpot = Boolean(scannerEngineConfig.include_spot);
      const includeFutures = Boolean(scannerEngineConfig.include_futures);
      const spotMode = "all";
      const futuresMode = "all";
      const inferredScanLimit = 2000;

      const payload = {
        exchange: "binance",
        include_spot: includeSpot,
        include_futures: includeFutures,
        market_scope: {
          spot_mode: spotMode,
          futures_mode: futuresMode,
        },
        signal_mode: scannerEngineConfig.signal_mode || "manual",
        auto_interval_minutes: [1, 3, 5].includes(Number(scannerEngineConfig.auto_interval_minutes))
          ? Number(scannerEngineConfig.auto_interval_minutes)
          : 3,
        scan_limit: inferredScanLimit,
        top_n: Number(scannerEngineConfig.top_n || 20),
        manual_symbols: manualSymbols,
        trend_weight: Number(scannerEngineConfig?.weights?.trend ?? 10),
        volume_weight: Number(scannerEngineConfig?.weights?.volume ?? 50),
        momentum_weight: Number(scannerEngineConfig?.weights?.momentum ?? 100),
        bollinger_weight: Number(scannerEngineConfig?.weights?.bollinger ?? 1),
        reason: "user_scanner_engine_config_save",
      };
      const { data } = await apiClient.post("/user/scanner-engine/config/save", payload);
      setScannerEngineConfig((prev) => ({ ...prev, ...(data?.config || payload) }));
      toast.success("Scanner Engine ayarları kaydedildi");
      await load({ silent: true });
    } catch (error) {
      toast.error(toApiErrorMessage(error, "Scanner Engine ayarı kaydedilemedi"));
    } finally {
      setScannerEngineBusy(false);
    }
  };

  const runScannerEngine = async () => {
    setScannerEngineBusy(true);
    try {
      const { data: queued } = await apiClient.post("/user/scanner-engine/run-async", {
        force_refresh: false,
        reason: "user_scanner_engine_run",
      }, { timeout: 12000 });

      if (queued?.status === "completed_cached") {
        await load({ silent: true });
        toast.success(`Önceki sonuç kullanıldı: ${queued?.summary?.scored_count || 0} sembol skorlandı`);
        return;
      }

      const jobId = String(queued?.job_id || "").trim();
      if (!jobId) {
        throw new Error("scanner_engine_async_job_id_missing");
      }

      const deadline = Date.now() + 240_000;
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const { data: statusData } = await apiClient.get(`/user/scanner-engine/run-async/${jobId}`, { timeout: 10000 });
        const status = String(statusData?.status || "").toLowerCase();
        if (status === "completed") {
          await load({ silent: true });
          toast.success(`Scanner tamamlandı: ${statusData?.summary?.scored_count || 0} sembol skorlandı`);
          return;
        }
        if (status === "failed") {
          throw new Error(String(statusData?.error || "scanner_engine_run_async_failed"));
        }
      }

      throw new Error("scanner_engine_run_async_timeout");
    } catch (error) {
      toast.error(toApiErrorMessage(error, "Scanner Engine run başarısız"));
    } finally {
      setScannerEngineBusy(false);
    }
  };

  useEffect(() => {
    if (SIMPLE_SCANNER_V2) {
      setScannerSection("results");
      return;
    }
    const nextSection = searchParams.get("section") === "screener" ? "screener" : "results";
    setScannerSection(nextSection);
  }, [searchParams]);

  const runPreset = async (preset) => {
    if (!ensureScannerRunReady()) {
      return;
    }

    const effectiveMode = SIMPLE_SCANNER_V2 ? "manual_selection" : (watchlistOnly ? "manual_selection" : symbolMode);
    setIsRunning(true);
    try {
      setMode(preset.mode);
      const data = await executeScannerRunWithChunks({
        runMode: preset.mode,
        maxResults: preset.maxResults,
        effectiveMode,
        selectedForRun: selectedSymbols,
        targetMarketType: marketType,
      });
      setLastRunEnvelope(data);
      setLastRunStartBotReport(null);
      await load();
      if ((data?.warnings || []).length > 0) {
        toast.warning((data.warnings || []).join(","));
      }
      toast.success(`Preset çalıştı: ${preset.label}`);
    } catch (error) {
      toast.error(toApiErrorMessage(error, "Preset çalıştırılamadı"));
    } finally {
      setIsRunning(false);
    }
  };

  if (isLoading) {
    return (
      <section className="space-y-4" data-testid="user-scanner-page">
        <header className="rounded-2xl border border-indigo-900/50 bg-slate-900 p-4" data-testid="user-scanner-header">
          <h2 className="text-4xl font-black uppercase tracking-tight text-indigo-200" data-testid="user-scanner-title">User Scanner</h2>
          <p className="mt-2 text-sm text-slate-400" data-testid="user-scanner-subtitle">Tarama ekranı yükleniyor...</p>
        </header>
        <LoadingSkeleton rows={6} testId="user-scanner-loading-skeleton" />
      </section>
    );
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

  const switchScannerSection = (nextSection) => {
    setScannerSection(nextSection);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("section", nextSection === "screener" ? "screener" : "results");
    setSearchParams(nextParams, { replace: true });
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

      {!SIMPLE_SCANNER_V2 && <section className="order-2 col-span-12 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-section-toggle-panel">
        <div className="flex flex-wrap items-center gap-2" data-testid="user-scanner-section-toggle-group">
          <Button type="button" variant={scannerSection === "results" ? "default" : "outline"} onClick={() => switchScannerSection("results")} data-testid="user-scanner-section-results-button">Scan Results</Button>
          <Button type="button" variant={scannerSection === "screener" ? "default" : "outline"} onClick={() => switchScannerSection("screener")} data-testid="user-scanner-section-screener-button">Indicator Screener</Button>
        </div>
      </section>}

      {!SIMPLE_SCANNER_V2 && scannerSection === "screener" ? (
        <div className="col-span-12" data-testid="user-scanner-embedded-screener-wrapper">
          <UserIndicatorScreenerPage embedded />
        </div>
      ) : (
      <>

      {!SIMPLE_SCANNER_V2 && <section className="col-span-12 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-request-health-mini-indicator">
        <div className="flex flex-wrap items-center gap-3" data-testid="user-scanner-request-health-row">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="user-scanner-request-health-title">Scanner Request Health</p>
          <div className="flex items-center gap-1" data-testid="user-scanner-request-health-trend-window-toggle">
            {REQUEST_TREND_OPTIONS.map((minutes) => (
              <Button
                key={`trend-window-${minutes}`}
                type="button"
                size="sm"
                variant={selectedTrendWindowMinutes === minutes ? "default" : "outline"}
                className="h-7 px-2 text-xs"
                data-testid={`user-scanner-request-health-trend-window-${minutes}m-button`}
                onClick={() => setSelectedTrendWindowMinutes(minutes)}
              >
                {minutes}m
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-1" data-testid="user-scanner-request-health-alert-toggle-group">
            <Button
              type="button"
              size="sm"
              variant={anomalyToastEnabled ? "default" : "outline"}
              className="h-7 px-2 text-xs"
              data-testid="user-scanner-request-health-anomaly-toast-toggle"
              onClick={() => setAnomalyToastEnabled((prev) => !prev)}
            >
              Toast {anomalyToastEnabled ? "Açık" : "Kapalı"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant={anomalySoundEnabled ? "default" : "outline"}
              className="h-7 px-2 text-xs"
              data-testid="user-scanner-request-health-anomaly-sound-toggle"
              onClick={() => setAnomalySoundEnabled((prev) => !prev)}
            >
              Ses {anomalySoundEnabled ? "Açık" : "Kapalı"}
            </Button>
          </div>
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
                points={requestTrendPolylinePath}
                data-testid="user-scanner-request-health-trend-polyline"
              />
              {requestTrendPolylinePoints.map((point) => (
                <circle
                  key={point.key}
                  cx={point.x}
                  cy={point.y}
                  r="2.4"
                  fill="#22d3ee"
                  data-testid={`user-scanner-request-health-trend-point-${point.key}`}
                  onMouseEnter={() => setHoveredTrendPointKey(point.key)}
                  onMouseLeave={() => setHoveredTrendPointKey(null)}
                >
                  <title>{`${point.label}: ok=${point.success}, fail=${point.fail}, success=${(point.successRatio * 100).toFixed(1)}%`}</title>
                </circle>
              ))}
            </svg>
            <div className="flex gap-1" data-testid="user-scanner-request-health-trend-labels">
              {requestTrendPolylinePoints.map((point) => (
                <span
                  key={point.key}
                  className="text-[10px] text-slate-400"
                  data-testid={`user-scanner-request-health-trend-label-${point.key}`}
                  onMouseEnter={() => setHoveredTrendPointKey(point.key)}
                  onMouseLeave={() => setHoveredTrendPointKey(null)}
                >
                  {point.label}
                </span>
              ))}
            </div>
          </div>
        </div>
        {trendDetailPoint && (
          <div className="mt-2 rounded border border-slate-700 bg-slate-950 p-2 text-xs text-slate-300" data-testid="user-scanner-request-health-trend-detail-card">
            <p data-testid="user-scanner-request-health-trend-detail-title">
              Hover detay: <span className="font-semibold text-cyan-300">{trendDetailPoint.label}</span>
            </p>
            <p data-testid="user-scanner-request-health-trend-detail-values">
              total={trendDetailPoint.total}, ok={trendDetailPoint.success}, fail={trendDetailPoint.fail}, success={(trendDetailPoint.successRatio * 100).toFixed(1)}%
            </p>
            <p data-testid="user-scanner-request-health-trend-detail-most-impacted-endpoint">
              most impacted endpoint: <span className="font-semibold text-amber-300">{formatEndpointLabel(trendDetailPoint.most_impacted_endpoint || "n/a")}</span>
            </p>
            <div className="mt-1 grid gap-1" data-testid="user-scanner-request-health-trend-detail-endpoint-list">
              {(trendDetailPoint.endpoint_breakdown || []).slice(0, 3).map((endpointRow, index) => (
                <div key={`${trendDetailPoint.key}-endpoint-${endpointRow.endpoint}`} className="space-y-1" data-testid={`user-scanner-request-health-trend-detail-endpoint-item-${index}`}>
                  <p>
                    {formatEndpointLabel(endpointRow.endpoint)} → ok/fail {endpointRow.success}/{endpointRow.fail}
                  </p>
                  <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800" data-testid={`user-scanner-request-health-trend-detail-endpoint-sparkbar-${index}`}>
                    <div
                      className="h-full bg-rose-400"
                      style={{ width: `${(endpointFailRatio(endpointRow) * 100).toFixed(1)}%` }}
                      data-testid={`user-scanner-request-health-trend-detail-endpoint-sparkbar-fill-${index}`}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        <p
          className={`mt-2 text-xs ${hasAnomaly ? "text-red-300" : "text-emerald-300"}`}
          data-testid="user-scanner-request-health-anomaly-flag"
        >
          {hasAnomaly
            ? `⚠️ Trade anomaly: son 1 dakikada trade_blocker fail oranı %${(latestFailRatio * 100).toFixed(1)} (>10)`
            : `✅ Trade anomaly yok: son 1 dakikada trade_blocker fail oranı %${(latestFailRatio * 100).toFixed(1)} (≤10)`}
        </p>
        <section className="mt-2 grid gap-2 md:grid-cols-2" data-testid="user-scanner-request-health-endpoint-breakdown-card">
          <div className="rounded border border-slate-700 bg-slate-950 p-2 text-xs text-slate-300" data-testid="user-scanner-request-health-endpoint-breakdown-1m-card">
            <p className="font-semibold text-cyan-300" data-testid="user-scanner-request-health-endpoint-breakdown-1m-title">Son 1m Endpoint Katkı</p>
            <p data-testid="user-scanner-request-health-endpoint-breakdown-1m-summary">
              req={requestEndpointBreakdown.oneMinute.total}, ok/fail={requestEndpointBreakdown.oneMinute.success}/{requestEndpointBreakdown.oneMinute.failed}, success={(requestEndpointBreakdown.oneMinute.successRatio * 100).toFixed(1)}%
            </p>
            <p data-testid="user-scanner-request-health-endpoint-breakdown-1m-excluded">
              excluded(auth+infra)={requestEndpointBreakdown.oneMinute.excluded || 0}
            </p>
            <p data-testid="user-scanner-request-health-endpoint-breakdown-1m-most-impacted">
              most impacted: <span className="font-semibold text-amber-300">{formatEndpointLabel(requestEndpointBreakdown.oneMinute.mostImpactedEndpoint || "n/a")}</span>
            </p>
            <div className="mt-1 grid gap-1" data-testid="user-scanner-request-health-endpoint-breakdown-1m-list">
              {requestEndpointBreakdown.oneMinute.rows.slice(0, 5).map((row, index) => (
                <div key={`one-minute-row-${row.endpoint}`} className="space-y-1" data-testid={`user-scanner-request-health-endpoint-breakdown-1m-item-${index}`}>
                  <p>{formatEndpointLabel(row.endpoint)} → ok/fail {row.success}/{row.fail}</p>
                  <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800" data-testid={`user-scanner-request-health-endpoint-breakdown-1m-sparkbar-${index}`}>
                    <div
                      className="h-full bg-rose-400"
                      style={{ width: `${(endpointFailRatio(row) * 100).toFixed(1)}%` }}
                      data-testid={`user-scanner-request-health-endpoint-breakdown-1m-sparkbar-fill-${index}`}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-2 text-xs text-slate-300" data-testid="user-scanner-request-health-endpoint-breakdown-5m-card">
            <p className="font-semibold text-cyan-300" data-testid="user-scanner-request-health-endpoint-breakdown-5m-title">Son 5m Endpoint Katkı</p>
            <p data-testid="user-scanner-request-health-endpoint-breakdown-5m-summary">
              req={requestEndpointBreakdown.fiveMinute.total}, ok/fail={requestEndpointBreakdown.fiveMinute.success}/{requestEndpointBreakdown.fiveMinute.failed}, success={(requestEndpointBreakdown.fiveMinute.successRatio * 100).toFixed(1)}%
            </p>
            <p data-testid="user-scanner-request-health-endpoint-breakdown-5m-excluded">
              excluded(auth+infra)={requestEndpointBreakdown.fiveMinute.excluded || 0}
            </p>
            <p data-testid="user-scanner-request-health-endpoint-breakdown-5m-most-impacted">
              most impacted: <span className="font-semibold text-amber-300">{formatEndpointLabel(requestEndpointBreakdown.fiveMinute.mostImpactedEndpoint || "n/a")}</span>
            </p>
            <div className="mt-1 grid gap-1" data-testid="user-scanner-request-health-endpoint-breakdown-5m-list">
              {requestEndpointBreakdown.fiveMinute.rows.slice(0, 5).map((row, index) => (
                <div key={`five-minute-row-${row.endpoint}`} className="space-y-1" data-testid={`user-scanner-request-health-endpoint-breakdown-5m-item-${index}`}>
                  <p>{formatEndpointLabel(row.endpoint)} → ok/fail {row.success}/{row.fail}</p>
                  <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800" data-testid={`user-scanner-request-health-endpoint-breakdown-5m-sparkbar-${index}`}>
                    <div
                      className="h-full bg-rose-400"
                      style={{ width: `${(endpointFailRatio(row) * 100).toFixed(1)}%` }}
                      data-testid={`user-scanner-request-health-endpoint-breakdown-5m-sparkbar-fill-${index}`}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </section>}

      {scannerLoadDegraded && (
        <div className="order-1 col-span-12 rounded border border-amber-700 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="user-scanner-degraded-load-banner">
          <p data-testid="user-scanner-degraded-load-banner-summary">
            Kısmi veri yüklendi · auth={scannerFailureSummary.auth_error} · infra={scannerFailureSummary.infra_error} · trade_blocker={scannerFailureSummary.trade_blocker}
          </p>
          <p className="mt-1 text-xs text-amber-100" data-testid="user-scanner-degraded-load-banner-endpoints">
            Etkilenen endpointler: {scannerLoadFailures.join(", ") || "-"}
          </p>
        </div>
      )}

      {!SIMPLE_SCANNER_V2 && <section className="order-2 col-span-12 rounded border border-cyan-800/50 bg-cyan-950/20 p-4" data-testid="user-scanner-active-mode-indicator-card">
        <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="user-scanner-active-mode-indicator-title">Scanner Active Mode Indicator</p>
        <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="user-scanner-active-mode-indicator-grid">
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-mode">Active Mode: {activeModeLabel}</p>
          <p className="text-sm font-semibold" data-testid="user-scanner-active-mode-indicator-run-type">Tarama Tipi: {scannerRunType}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-path">Execution Path: {executionPathLabel}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-source">Source: {symbolSource.toUpperCase()}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-symbol-mode">Symbol Mode: {symbolMode}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-market-type">Market: {marketType.toUpperCase()}</p>
        </div>
        <p className="mt-2 text-xs text-cyan-100" data-testid="user-scanner-active-mode-indicator-run-type-detail">{scannerRunTypeDetail}</p>
      </section>}

      {false && !SIMPLE_SCANNER_V2 && <section className="order-3 col-span-12 rounded border border-emerald-800/50 bg-emerald-950/20 p-4" data-testid="user-scanner-automation-card">
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
      </section>}

      {false && !SIMPLE_SCANNER_V2 && <section className="order-4 col-span-12 rounded border border-violet-800/50 bg-violet-950/20 p-4" data-testid="user-scanner-automation-profiles-card">
        <p className="text-xs uppercase tracking-widest text-violet-300" data-testid="user-scanner-automation-profiles-title">Çoklu Otomasyon Profilleri</p>
        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="user-scanner-automation-profiles-create-grid">
          <input
            value={profileNameInput}
            onChange={(event) => setProfileNameInput(event.target.value)}
            placeholder="örn: scalp-3m"
            className="h-10 rounded border border-violet-300 bg-white px-3 text-sm text-slate-900"
            data-testid="user-scanner-automation-profile-name-input"
          />
          <select
            value={profileIntervalInput}
            onChange={(event) => setProfileIntervalInput(Number(event.target.value))}
            className="h-10 rounded border border-violet-300 bg-white px-3 text-sm text-slate-900"
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
            <div key={profile.id} className="flex flex-wrap items-center gap-2 rounded border border-violet-300/80 bg-white p-2 text-slate-900" data-testid={`user-scanner-automation-profile-row-${profile.id}`}>
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
      </section>}

      {!SIMPLE_SCANNER_V2 && <section className="order-8 col-span-12 rounded border border-amber-800/50 bg-amber-950/20 p-4" data-testid="user-scanner-auto-alerts-card">
        <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="user-scanner-auto-alerts-title">Otomatik Run Uyarıları</p>
        <div className="mt-2 space-y-1" data-testid="user-scanner-auto-alerts-list">
          {autoRunAlerts.length === 0 && <p className="text-xs text-amber-100" data-testid="user-scanner-auto-alerts-empty">Henüz yeni otomatik sinyal bildirimi yok.</p>}
          {autoRunAlerts.map((item) => (
            <p key={item.id} className="text-xs" data-testid={`user-scanner-auto-alert-item-${item.id}`}>
              {item.profile_name}: +{item.signal_count} sinyal · {formatDateLabel(item.run_at)}
            </p>
          ))}
        </div>
      </section>}

      {!SIMPLE_SCANNER_V2 && <section className="order-9 col-span-12 rounded border border-blue-800/50 bg-blue-950/20 p-4" data-testid="user-decision-card-section">
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
      </section>}

      {!SIMPLE_SCANNER_V2 && <section className="order-10 col-span-12 rounded border border-fuchsia-800/50 bg-fuchsia-950/20 p-4" data-testid="user-explainability-panel">
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
      </section>}

      {!SIMPLE_SCANNER_V2 && (
        <ExplainabilityDrawer
          isOpen={isExplainabilityDrawerOpen}
          onOpenChange={setIsExplainabilityDrawerOpen}
          selectedSymbol={selectedDecisionSymbol}
          isLoading={isExplainabilityLoading}
          explainability={symbolExplainability}
          formatDateLabel={formatDateLabel}
        />
      )}

      <section className="order-5 col-span-12 space-y-4 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-control-section">
        <div data-testid="user-scanner-control-header">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-control-kicker">Scanner Engine</p>
          <h3 className="text-base font-semibold" data-testid="user-scanner-control-title">Short/Long Decoupled Scanner</h3>
        </div>

        <div className="grid gap-3 xl:grid-cols-7 xl:items-start" data-testid="user-scanner-engine-config-grid">
          <label className="space-y-1" data-testid="user-scanner-engine-market-field">
            <span className="text-xs uppercase tracking-widest text-slate-500">Market</span>
            <input value="BINANCE" disabled className="h-10 border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-scanner-engine-market-input" />
          </label>

          <div className="space-y-2 xl:col-span-2" data-testid="user-scanner-engine-market-types-field">
            <span className="text-xs uppercase tracking-widest text-slate-500">Piyasa Tipi</span>
            <div className="grid gap-2 md:grid-cols-2" data-testid="user-scanner-engine-market-type-rows">
              <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="user-scanner-engine-spot-row">
                <label className="flex items-center gap-2 text-sm" data-testid="user-scanner-engine-spot-label">
                  <input
                    type="checkbox"
                    checked={Boolean(scannerEngineConfig.include_spot)}
                    onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, include_spot: event.target.checked }))}
                    disabled={scannerEngineBusy}
                    data-testid="user-scanner-engine-spot-checkbox"
                  />
                  Spot
                </label>
                {Boolean(scannerEngineConfig.include_spot) && (
                  <select
                    value={"all"}
                    onChange={(event) => setScannerEngineConfig((prev) => ({
                      ...prev,
                      market_scope: { ...(prev.market_scope || {}), spot_mode: event.target.value },
                    }))}
                    disabled={scannerEngineBusy}
                    className="mt-2 h-9 w-full border border-slate-700 bg-black px-2 text-xs"
                    data-testid="user-scanner-engine-spot-scope-select"
                  >
                    <option value="all" data-testid="user-scanner-engine-spot-scope-all">Bütün coinler</option>
                  </select>
                )}
              </div>

              <div className="rounded border border-slate-700 bg-slate-950 p-2" data-testid="user-scanner-engine-futures-row">
                <label className="flex items-center gap-2 text-sm" data-testid="user-scanner-engine-futures-label">
                  <input
                    type="checkbox"
                    checked={Boolean(scannerEngineConfig.include_futures)}
                    onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, include_futures: event.target.checked }))}
                    disabled={scannerEngineBusy}
                    data-testid="user-scanner-engine-futures-checkbox"
                  />
                  Futures
                </label>
                {Boolean(scannerEngineConfig.include_futures) && (
                  <select
                    value={"all"}
                    onChange={(event) => setScannerEngineConfig((prev) => ({
                      ...prev,
                      market_scope: { ...(prev.market_scope || {}), futures_mode: event.target.value },
                    }))}
                    disabled={scannerEngineBusy}
                    className="mt-2 h-9 w-full border border-slate-700 bg-black px-2 text-xs"
                    data-testid="user-scanner-engine-futures-scope-select"
                  >
                    <option value="all" data-testid="user-scanner-engine-futures-scope-all">Bütün coinler</option>
                  </select>
                )}
              </div>
            </div>
          </div>

          <label className="space-y-1" data-testid="user-scanner-engine-manual-symbols-field">
            <span className="text-xs uppercase tracking-widest text-slate-500">Sembol (opsiyonel)</span>
            <input
              value={scannerEngineManualSymbols}
              onChange={(event) => setScannerEngineManualSymbols(event.target.value)}
              placeholder="BTCUSDT,ETHUSDT"
              disabled={scannerEngineBusy}
              className="h-10 border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              data-testid="user-scanner-engine-manual-symbols-input"
            />
          </label>

          <div className="space-y-2" data-testid="user-scanner-engine-signal-mode-field">
            <span className="text-xs uppercase tracking-widest text-slate-500">Tarama Modu</span>
            <div className="flex h-10 items-center gap-3 border border-slate-700 bg-slate-950 px-3 py-2" data-testid="user-scanner-engine-signal-mode-checkbox-wrap">
              <label className="flex items-center gap-1 text-xs" data-testid="user-scanner-engine-signal-mode-manual-label">
                <input
                  type="checkbox"
                  checked={String(scannerEngineConfig.signal_mode || "manual") === "manual"}
                  onChange={() => setScannerEngineConfig((prev) => ({ ...prev, signal_mode: "manual" }))}
                  disabled={scannerEngineBusy}
                  data-testid="user-scanner-engine-signal-mode-manual-checkbox"
                />
                Manuel
              </label>
              <label className="flex items-center gap-1 text-xs" data-testid="user-scanner-engine-signal-mode-auto-label">
                <input
                  type="checkbox"
                  checked={String(scannerEngineConfig.signal_mode || "manual") === "auto"}
                  onChange={() => setScannerEngineConfig((prev) => ({ ...prev, signal_mode: "auto" }))}
                  disabled={scannerEngineBusy}
                  data-testid="user-scanner-engine-signal-mode-auto-checkbox"
                />
                Auto
              </label>

              {String(scannerEngineConfig.signal_mode || "manual") === "auto" && (
                <select
                  value={Number(scannerEngineConfig.auto_interval_minutes || 3)}
                  onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, auto_interval_minutes: Number(event.target.value || 3) }))}
                  disabled={scannerEngineBusy}
                  className="ml-auto h-7 border border-slate-600 bg-black px-2 text-xs"
                  data-testid="user-scanner-engine-auto-interval-select"
                >
                  <option value={1} data-testid="user-scanner-engine-auto-interval-option-1">1 dakika</option>
                  <option value={3} data-testid="user-scanner-engine-auto-interval-option-3">3 dakika</option>
                  <option value={5} data-testid="user-scanner-engine-auto-interval-option-5">5 dakika</option>
                </select>
              )}
            </div>
          </div>

          <div className="space-y-1" data-testid="user-scanner-engine-save-action-wrap">
            <span className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-engine-save-label">Kaydet</span>
            <Button type="button" variant="outline" onClick={saveScannerEngineConfig} disabled={scannerEngineBusy} className="h-10 w-full" data-testid="user-scanner-engine-save-button">Kaydet</Button>
          </div>

          <div className="space-y-1" data-testid="user-scanner-engine-run-action-wrap">
            <span className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-scanner-engine-run-label">Tara</span>
            <Button type="button" variant="outline" onClick={runScannerEngine} disabled={scannerEngineBusy} className="h-10 w-full" data-testid="user-scanner-engine-run-button">Tara</Button>
          </div>
        </div>

        <div className="grid gap-2 rounded border border-slate-800 bg-slate-950 p-3 md:grid-cols-2" data-testid="user-scanner-live-scan-timer-section">
          <p className="text-sm" data-testid="user-scanner-last-scan-value">Last Scan time: {formatDateLabel(scannerEngineRun?.generated_at || activeAutomation?.last_run_at || overview?.latest_generated_at)}</p>
          <p className="text-sm" data-testid="user-scanner-next-scan-value">Next Scan time: {formatDateLabel(scannerEngineNextRunAt)}</p>
        </div>
      </section>

      <section className="order-6 col-span-12 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-parameters-card">
        <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="user-scanner-parameters-title">Çalışma Parametreleri</p>
        <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="user-scanner-parameters-grid">
          <p className="text-sm" data-testid="user-scanner-parameters-market">Market: <span className="font-semibold">{String(marketType || "spot").toUpperCase()}</span></p>
          <p className="text-sm" data-testid="user-scanner-parameters-mode">Signal Mode: <span className="font-semibold">{String(mode || "ASSISTED").toUpperCase()}</span></p>
          <p className="text-sm" data-testid="user-scanner-parameters-auto">Auto Scan: <span className="font-semibold">{activeAutomation?.auto_enabled ? "ON" : "OFF"}</span></p>
          <p className="text-sm" data-testid="user-scanner-parameters-interval">Interval: <span className="font-semibold">{Number(activeAutomation?.interval_seconds || autoScanInterval || AUTO_SCAN_INTERVAL_SECONDS)}s</span></p>
          <p className="text-sm" data-testid="user-scanner-parameters-selected-count">Selected Symbols: <span className="font-semibold">{selectedSymbols.length}</span></p>
          <p className="text-sm" data-testid="user-scanner-parameters-max-results">Max Results: <span className="font-semibold">{SIMPLE_SCANNER_V2 ? 120 : 25}</span></p>
          <p className="text-sm md:col-span-3" data-testid="user-scanner-parameters-selected-sample">
            Örnek Semboller: <span className="font-mono text-xs">{(selectedSymbols || []).slice(0, 12).join(", ") || "-"}{selectedSymbols.length > 12 ? ` +${selectedSymbols.length - 12}` : ""}</span>
          </p>
          <p className="text-sm md:col-span-3" data-testid="user-scanner-parameters-strategy-mapping">Strategy Mapping: <span className="font-semibold">signal.execution_strategy_type = bot.strategy_type</span></p>
        </div>
      </section>

      {!SIMPLE_SCANNER_V2 && <section className="order-7 col-span-12 space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-minimal-filter-section">
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
      </section>}

      {!SIMPLE_SCANNER_V2 && <section className="order-8 col-span-12 space-y-3 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-strategy-presets-section">
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
      </section>}

      {!SIMPLE_SCANNER_V2 && <section className="order-11 col-span-12 space-y-3 rounded border border-cyan-800/50 bg-cyan-950/20 p-4" data-testid="user-scanner-live-readiness-section">
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
      </section>}

      <section className="order-12 col-span-12" data-testid="user-scanner-results-main-section">
        <ScannerResultsTable
          results={scannerResults}
          compactMode={compactMode}
          decisionApprovalMap={scannerEngineDecisionApprovalMap}
          onOpenTrade={openExecuteFromScanner}
          onViewCard={(item) => onSelectDecisionCard(item.symbol)}
          onAddWatchlist={addWatchlistFromResult}
        />
      </section>
      </>
      )}
    </section>
  );
};