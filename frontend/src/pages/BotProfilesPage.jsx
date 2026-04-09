import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
import { apiClient, classifyApiError } from "@/lib/api";

const initialForm = {
  name: "",
  exchange: "binance",
  market_type: "spot",
  exchange_connection_id: "",
  risk_policy_id: "",
  symbols: "",
  strategy_type: "",
  mode: "live_ready",
  symbol_source_type: "scanner",
  scanner_id: "default",
  symbol_preset: "top_50",
  custom_watchlist_id: "",
  use_template: false,
  timeframe: "15m",
  trend_timeframe: "1h",
  is_enabled: true,
  template_id: "",
  strategy_template_ids: [],
  risk_adaptive_confirmed: false,
  strategy_allocations: [],
};

const EXCHANGE_OPTIONS = [
  { value: "binance", label: "Binance" },
  { value: "bybit", label: "Bybit" },
];

const MARKET_TYPE_OPTIONS = [
  { value: "spot", label: "Spot" },
  { value: "futures", label: "Futures" },
];

const BOT_MODE_OPTIONS = [
  { value: "live_ready", label: "LIVE-READY" },
];

const SYMBOL_PRESET_OPTIONS = [
  { value: "top_50", label: "Top 50 Coins" },
  { value: "top_100", label: "Top 100 Coins" },
  { value: "all_symbols", label: "All Symbols" },
  { value: "custom_list", label: "Custom Selection" },
];

const LEGACY_TOP_FORM = true;
const STRATEGY_PRIORITY_MIN = 1;
const STRATEGY_PRIORITY_MAX = 100;
const STRATEGY_WEIGHT_LIMIT = 1;
const CORE_STRATEGY_IDS = [
  "trend_following",
  "mean_reversion",
  "volatility_breakout",
  "low_vol_scalping",
  "momentum_ignition",
  "volume_profile_reclaim",
  "range_rotation",
  "funding_rate_carry",
  "basis_arbitrage",
  "orderflow_imbalance",
  "news_sentiment_reaction",
  "scalping",
];

const toNum = (value) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
};

const parseApiErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  const normalizeKnownCode = (text) => {
    const code = String(text || "").trim().toLowerCase();
    if (!code) return "";
    if (code === "exchange_connection_required") return "LIVE-READY için Kullanılacak Cüzdan seçimi zorunlu.";
    if (code === "exchange_connection_not_found") return "Seçilen cüzdan bağlantısı bulunamadı.";
    if (code === "mock_mode_removed_live_ready_required") return "MOCK/PAPER kaldırıldı. Sadece LIVE-READY kullanılabilir.";
    if (code === "authentication required" || code === "not authenticated") return "Oturum doğrulaması düştü. Lütfen tekrar giriş yapın.";
    if (code === "session_device_mismatch") return "Oturum cihaz doğrulaması uyuşmadı. Lütfen tekrar giriş yapın.";
    if (code === "strategy_allocation_required") return "En az bir strateji için weight girin.";
    if (code === "strategy_allocation_weight_limit_exceeded") return "Weight toplamı 1.0 değerini geçemez.";
    if (code === "strategy_allocation_priority_out_of_range") return "Priority 1 ile 100 arasında olmalıdır.";
    return "";
  };

  if (Array.isArray(detail)) {
    const text = detail.map((item) => item?.msg || item?.message || "").filter(Boolean).join(", ");
    if (text) return text;
  }
  if (typeof detail === "string" && detail.trim()) {
    const known = normalizeKnownCode(detail);
    if (known) return known;
    return detail;
  }
  if (detail && typeof detail === "object") {
    const blockingReasons = Array.isArray(detail.blocking_reasons)
      ? detail.blocking_reasons.map((item) => item?.code || item?.message || "").filter(Boolean)
      : [];
    if (blockingReasons.length > 0) {
      const base = detail.message || detail.code || detail.error || detail.detail || fallback;
      return `${base} (${blockingReasons.join(", ")})`;
    }
    const known = normalizeKnownCode(detail.message || detail.code || detail.error || detail.detail);
    if (known) return known;
    return detail.message || detail.code || detail.error || detail.detail || fallback;
  }
  const knownFromMessage = normalizeKnownCode(error?.message || "");
  if (knownFromMessage) return knownFromMessage;
  const status = Number(error?.response?.status || 0);
  if (status > 0) {
    return `${fallback} (HTTP ${status})`;
  }
  return fallback;
};

const getConnectionSourceMeta = (connection) => {
  const snapshot = connection?.readiness_snapshot && typeof connection.readiness_snapshot === "object"
    ? connection.readiness_snapshot
    : {};
  const source = String(snapshot?.source || "").toLowerCase();
  const label = String(connection?.account_label || "").toUpperCase();
  return {
    source,
    isSettingsSynced: source === "phase4_exchange_settings_sync" || label.startsWith("SETTINGS "),
  };
};

const getConnectionRanking = (connection) => {
  const snapshot = connection?.readiness_snapshot && typeof connection.readiness_snapshot === "object"
    ? connection.readiness_snapshot
    : {};
  const { isSettingsSynced } = getConnectionSourceMeta(connection);
  const health = String(connection?.connection_health || snapshot?.connection_health || "").toLowerCase();
  const canTradeEffective = Boolean(connection?.can_trade_effective);
  const onlineTradeScore = health === "online" && canTradeEffective ? 1 : 0;
  const availableBalance = toNum(snapshot.available_balance ?? snapshot.wallet_balance ?? snapshot.total_wallet_balance);
  const walletScore = availableBalance > 0 ? 1 : 0;
  const defaultScore = connection?.is_default ? 1 : 0;
  const updatedAt = String(connection?.updated_at || "");
  return {
    onlineTradeScore,
    walletScore,
    settingsScore: isSettingsSynced ? 1 : 0,
    defaultScore,
    updatedAt,
  };
};

const toCanonicalStrategyOptions = (items = []) => {
  const enabledRows = (items || [])
    .filter((item) => Boolean(item?.is_enabled) && Boolean(item?.in_production_path));
  const byId = new Map(enabledRows.map((item) => [String(item.strategy_id || ""), item]));

  return CORE_STRATEGY_IDS.slice(0, 12).map((strategyId, idx) => {
    const item = byId.get(strategyId) || {};
    return {
      id: String(item.strategy_id || `canonical-${idx}`),
      strategy_id: strategyId,
      name: String(item.strategy_id || strategyId).replaceAll("_", " "),
      strategy_family: String(item.strategy_family || "general"),
      market_regime: String(item.market_regime || "mixed"),
      entry_long: item.entry_long || {},
      exit_long: item.exit_long || {},
    };
  });
};

const toStrategyAllocationRows = (canonicalOptions = [], existingRows = []) => {
  const existingMap = new Map(
    (existingRows || [])
      .filter((row) => row && row.strategy_id)
      .map((row) => [
        String(row.strategy_id),
        {
          family: String(row.family || row.strategy_family || "general"),
          weight: Number(row.weight || 0),
          priority: Number(row.priority || 50),
        },
      ]),
  );

  return (canonicalOptions || []).slice(0, 12).map((item, index) => {
    const strategyId = String(item.strategy_id || `strategy_${index + 1}`);
    const existing = existingMap.get(strategyId);
    return {
      strategy_id: strategyId,
      family: String(existing?.family || item.strategy_family || "general"),
      weight: Number.isFinite(Number(existing?.weight)) ? Number(existing.weight) : 0,
      priority: Number.isFinite(Number(existing?.priority)) ? Number(existing.priority) : Math.min(STRATEGY_PRIORITY_MAX, index + 1),
    };
  });
};

const pickPrimaryStrategyId = (rows = [], fallback = "") => {
  const activeRows = (rows || []).filter((row) => Number(row.weight || 0) > 0);
  if (activeRows.length === 0) return String(fallback || "");
  activeRows.sort((a, b) => {
    const byPriority = Number(a.priority || 100) - Number(b.priority || 100);
    if (byPriority !== 0) return byPriority;
    const byWeight = Number(b.weight || 0) - Number(a.weight || 0);
    if (byWeight !== 0) return byWeight;
    return String(a.strategy_id || "").localeCompare(String(b.strategy_id || ""));
  });
  return String(activeRows[0]?.strategy_id || fallback || "");
};

export const BotProfilesPage = () => {
  const location = useLocation();
  const [items, setItems] = useState([]);
  const [strategyPerformance, setStrategyPerformance] = useState({ items: [] });
  const [riskPolicies, setRiskPolicies] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [canonicalStrategies, setCanonicalStrategies] = useState([]);
  const [exchangeConnections, setExchangeConnections] = useState([]);
  const [watchlists, setWatchlists] = useState([]);
  const [isApplyingPreset, setIsApplyingPreset] = useState(false);
  const [selectedBot, setSelectedBot] = useState(null);
  const [detailTab, setDetailTab] = useState("overview");
  const [botStatus, setBotStatus] = useState(null);
  const [botPerformance, setBotPerformance] = useState(null);
  const [botLogs, setBotLogs] = useState([]);
  const [botTrades, setBotTrades] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [deletingBotId, setDeletingBotId] = useState("");
  const [form, setForm] = useState(initialForm);
  const [formErrors, setFormErrors] = useState({});
  const [symbolSource, setSymbolSource] = useState("crypto");
  const [symbolMode, setSymbolMode] = useState("all_market_symbols");
  const [selectedSymbols, setSelectedSymbols] = useState([]);

  const fetchItems = useCallback(async () => {
    const serviceRequests = [
      {
        key: "bot_profiles",
        label: "Bot listesi servisi",
        request: () => apiClient.get("/bot-profiles"),
      },
      {
        key: "strategy_performance",
        label: "Strategy performance servisi",
        request: () => apiClient.get("/user/live/strategy-performance", { params: { window: "24h" } }),
      },
      {
        key: "strategy_templates",
        label: "Template servisi",
        request: () => apiClient.get("/strategy-templates"),
      },
      {
        key: "canonical_strategies",
        label: "Canonical strategy servisi",
        request: () => apiClient.get("/user/canonical-strategies"),
      },
      {
        key: "exchange_connections",
        label: "Exchange connection servisi",
        request: () => apiClient.get("/user/exchange-connections"),
      },
      {
        key: "risk_policies",
        label: "Risk policy servisi",
        request: () => apiClient.get("/risk-policies"),
      },
    ];

    const results = await Promise.allSettled(serviceRequests.map((item) => item.request()));
    const fulfilled = {};
    const failures = [];

    results.forEach((result, index) => {
      const meta = serviceRequests[index];
      if (result.status === "fulfilled") {
        fulfilled[meta.key] = result.value?.data;
        return;
      }
      failures.push({
        key: meta.key,
        label: meta.label,
        message: parseApiErrorMessage(result.reason, "servise ulaşılamadı"),
        errorClass: classifyApiError(result.reason),
      });
    });

    if (Object.prototype.hasOwnProperty.call(fulfilled, "bot_profiles")) {
      const nextItems = Array.isArray(fulfilled.bot_profiles) ? fulfilled.bot_profiles : [];
      setItems(nextItems);
      setSelectedBot((prev) => {
        if (!prev?.id) return prev;
        return nextItems.find((item) => item.id === prev.id) || null;
      });
    }

    if (Object.prototype.hasOwnProperty.call(fulfilled, "strategy_performance")) {
      setStrategyPerformance(fulfilled.strategy_performance || { items: [] });
    }

    if (Object.prototype.hasOwnProperty.call(fulfilled, "strategy_templates")) {
      setTemplates(Array.isArray(fulfilled.strategy_templates) ? fulfilled.strategy_templates : []);
    }

    if (Object.prototype.hasOwnProperty.call(fulfilled, "canonical_strategies")) {
      setCanonicalStrategies(Array.isArray(fulfilled.canonical_strategies) ? fulfilled.canonical_strategies : []);
    }

    if (Object.prototype.hasOwnProperty.call(fulfilled, "exchange_connections")) {
      setExchangeConnections(Array.isArray(fulfilled.exchange_connections) ? fulfilled.exchange_connections : []);
    }

    if (Object.prototype.hasOwnProperty.call(fulfilled, "risk_policies")) {
      setRiskPolicies(Array.isArray(fulfilled.risk_policies) ? fulfilled.risk_policies : []);
    }

    if (failures.length > 0) {
      const summary = failures.slice(0, 2).map((item) => `${item.label}: ${item.message}`).join(" · ");
      const extra = failures.length > 2 ? ` (+${failures.length - 2} servis)` : "";
      const classes = Array.from(new Set(failures.map((item) => item.errorClass))).join(", ");
      const criticalKeys = new Set(["bot_profiles", "risk_policies", "exchange_connections"]);
      const hasCriticalFailure = failures.some((item) => criticalKeys.has(item.key));
      const toastMethod = hasCriticalFailure ? "error" : "warning";
      toast[toastMethod](`Kısmi yükleme [${classes}]: ${summary}${extra}`);
    }
  }, []);

  const findStrategyParity = (strategyType) => (strategyPerformance?.items || []).find((item) => item.strategy_id === strategyType);

  const strategyLabelMap = useMemo(
    () => ({
      trend_following: "Agresif / Trend Takipçisi",
      mean_reversion: "Muhafazakar / Arbitraj",
      volatility_breakout: "Agresif / Kırılım",
      low_vol_scalping: "Düşük Volatilite / Scalping",
      scalping: "Düşük Volatilite / Scalping",
      momentum_ignition: "Momentum / Ignition",
      volume_profile_reclaim: "Volume Profile / Reclaim",
      range_rotation: "Range Rotation",
      funding_rate_carry: "Funding Carry",
      basis_arbitrage: "Basis Arbitrage",
      orderflow_imbalance: "Orderflow Imbalance",
      news_sentiment_reaction: "News Sentiment",
    }),
    [],
  );

  const activeTemplateOptions = useMemo(() => {
    const latestByCode = new Map();
    for (const item of templates || []) {
      const isActive = String(item?.lifecycle_state || "").toUpperCase() === "ACTIVE";
      if (!isActive) continue;
      const key = String(item.template_code || item.id || "");
      const prev = latestByCode.get(key);
      if (!prev || Number(item.version_num || 0) >= Number(prev.version_num || 0)) {
        latestByCode.set(key, item);
      }
    }
    return Array.from(latestByCode.values())
      .sort((a, b) => Number(b.version_num || 0) - Number(a.version_num || 0))
      .slice(0, 12)
      .map((item) => ({
        id: item.id,
        name: item.name,
        strategy_type: item.strategy_type,
        label: strategyLabelMap[item.strategy_type] || "Nötr / Genel",
      }));
  }, [templates, strategyLabelMap]);

  const canonicalStrategyOptions = useMemo(
    () => toCanonicalStrategyOptions(canonicalStrategies),
    [canonicalStrategies],
  );

  const riskPolicyOptions = useMemo(
    () => (riskPolicies || []).filter((item) => !String(item?.lifecycle_state || "").toUpperCase().includes("DEPRECATED")),
    [riskPolicies],
  );

  const selectedRiskPolicy = useMemo(
    () => riskPolicyOptions.find((item) => item.id === form.risk_policy_id) || null,
    [riskPolicyOptions, form.risk_policy_id],
  );

  const strategyAllocationRows = useMemo(
    () => toStrategyAllocationRows(canonicalStrategyOptions, form.strategy_allocations),
    [canonicalStrategyOptions, form.strategy_allocations],
  );

  const strategyWeightTotal = useMemo(
    () => strategyAllocationRows.reduce((sum, row) => sum + Number(row.weight || 0), 0),
    [strategyAllocationRows],
  );

  const hasStrategyWeightOverflow = strategyWeightTotal > STRATEGY_WEIGHT_LIMIT + 0.0000001;

  const primaryStrategyType = useMemo(
    () => pickPrimaryStrategyId(strategyAllocationRows, form.strategy_type),
    [strategyAllocationRows, form.strategy_type],
  );

  const scopedConnections = useMemo(() => {
    return (exchangeConnections || [])
      .filter((item) => String(item?.exchange || "").toLowerCase() === String(form.exchange || "binance").toLowerCase())
      .filter((item) => String(item?.market_type || "").toLowerCase() === String(form.market_type || "spot").toLowerCase())
      .filter((item) => String(item?.environment || "live").toLowerCase() === "live")
      .sort((a, b) => {
        const aRank = getConnectionRanking(a);
        const bRank = getConnectionRanking(b);
        if (aRank.onlineTradeScore !== bRank.onlineTradeScore) return bRank.onlineTradeScore - aRank.onlineTradeScore;
        if (aRank.walletScore !== bRank.walletScore) return bRank.walletScore - aRank.walletScore;
        if (aRank.settingsScore !== bRank.settingsScore) return bRank.settingsScore - aRank.settingsScore;
        if (aRank.defaultScore !== bRank.defaultScore) return bRank.defaultScore - aRank.defaultScore;
        return bRank.updatedAt.localeCompare(aRank.updatedAt);
      });
  }, [exchangeConnections, form.exchange, form.market_type]);

  const walletConnectionOptions = useMemo(() => {
    return scopedConnections.map((connection) => {
      const snapshot = connection?.readiness_snapshot || {};
      const { isSettingsSynced } = getConnectionSourceMeta(connection);
      const availableBalance = toNum(snapshot.available_balance ?? snapshot.wallet_balance ?? snapshot.total_wallet_balance);
      const unrealizedPnl = toNum(snapshot.unrealized_pnl ?? snapshot.total_unrealized_pnl ?? snapshot.realized_pnl);
      const walletLabel = String(connection.market_type || "spot").toLowerCase() === "futures" ? "FUTURES CÜZDAN" : "SPOT CÜZDAN";
      return {
        id: connection.id,
        exchange: connection.exchange,
        market_type: connection.market_type,
        label: `${walletLabel} · ${availableBalance.toFixed(2)} USDT · ${connection.account_label}`,
        available_balance: availableBalance,
        pnl: unrealizedPnl,
        global_activation_active: Boolean(connection.global_activation_active),
        global_activation_flag_key: connection.global_activation_flag_key,
        can_trade_effective: Boolean(connection.can_trade_effective),
        connection_health: String(connection.connection_health || "unknown").toLowerCase(),
        is_settings_synced: isSettingsSynced,
      };
    });
  }, [scopedConnections]);

  const selectedWalletConnection = useMemo(
    () => walletConnectionOptions.find((item) => item.id === form.exchange_connection_id) || null,
    [walletConnectionOptions, form.exchange_connection_id],
  );

  const comboActivationState = useMemo(() => {
    const scoped = scopedConnections;
    const active = scoped.some((item) => {
      const health = String(item?.connection_health || "").toLowerCase();
      return (health === "online" && Boolean(item?.can_trade_effective)) || Boolean(item?.global_activation_active);
    });
    return {
      active,
      hasConnection: scoped.length > 0,
      flag: scoped[0]?.global_activation_flag_key || `is_${form.exchange}_${form.market_type}_active`,
    };
  }, [form.exchange, form.market_type, scopedConnections]);

  const liveReadyBlockedReason = useMemo(() => {
    if (form.mode !== "live_ready") return "";
    if (String(form.exchange || "").toLowerCase() === "bybit") {
      return "Bybit için LIVE-READY bu fazda kapalı. MOCK kullanın.";
    }
    if (!comboActivationState.hasConnection) {
      return "Bağlantınızı doğrulayın (Diagnostics: bağlantı bulunamadı).";
    }
    if (!comboActivationState.active) {
      return "Bağlantınızı doğrulayın (Diagnostics: Passive).";
    }
    if (!selectedWalletConnection) {
      return "Önce cüzdan seçin.";
    }
    if (toNum(selectedWalletConnection.available_balance) <= 0) {
      if (String(selectedWalletConnection.connection_health || "").toLowerCase() === "online") {
        return "Bağlantı online ancak bakiye 0. API yetkilerinizi (Read Balance) kontrol edin ve Revalidate yapın.";
      }
      return "Kullanılabilir bakiye yetersiz, LIVE-READY kilitli.";
    }
    return "";
  }, [comboActivationState.active, comboActivationState.hasConnection, form.exchange, form.mode, selectedWalletConnection]);

  const readBalancePermissionWarning = useMemo(() => {
    if (!selectedWalletConnection) {
      return "";
    }
    const isOnline = String(selectedWalletConnection.connection_health || "").toLowerCase() === "online";
    const hasZeroBalance = toNum(selectedWalletConnection.available_balance) <= 0;
    if (isOnline && hasZeroBalance) {
      return "Bağlantı online fakat bakiye 0 görünüyor. API yetkilerinizi (Read Balance) kontrol edin ve Diagnostics > Revalidate çalıştırın.";
    }
    return "";
  }, [selectedWalletConnection]);

  useEffect(() => {
    const loadDetail = async () => {
      if (!selectedBot?.id) return;
      const requests = [
        { key: "detail", request: () => apiClient.get(`/bot-profiles/${selectedBot.id}/detail`) },
        { key: "performance", request: () => apiClient.get(`/bot-profiles/${selectedBot.id}/performance`) },
        { key: "logs", request: () => apiClient.get(`/bot-profiles/${selectedBot.id}/logs`) },
        { key: "trades", request: () => apiClient.get(`/bot-profiles/${selectedBot.id}/trades`) },
      ];

      const results = await Promise.allSettled(requests.map((item) => item.request()));
      const failures = [];

      results.forEach((result, index) => {
        const key = requests[index].key;
        if (result.status === "fulfilled") {
          const payload = result.value?.data;
          if (key === "detail") setBotStatus(payload || null);
          if (key === "performance") setBotPerformance(payload || null);
          if (key === "logs") setBotLogs(Array.isArray(payload) ? payload : []);
          if (key === "trades") setBotTrades(Array.isArray(payload) ? payload : []);
          return;
        }
        failures.push({ key, message: parseApiErrorMessage(result.reason, "servise ulaşılamadı") });
      });

      if (failures.length > 0 && failures.length < requests.length) {
        const summary = failures.slice(0, 2).map((item) => `${item.key}: ${item.message}`).join(" · ");
        const extra = failures.length > 2 ? ` (+${failures.length - 2} servis)` : "";
        toast.error(`Detail kısmi yüklendi: ${summary}${extra}`);
      }

      if (failures.length === requests.length) {
        toast.error("Bot detail servisleri şu an yanıt vermiyor. Lütfen tekrar deneyin.");
      }
    };
    loadDetail();
  }, [selectedBot]);

  const applyTemplate = (templateId) => {
    const template = (activeTemplateOptions || []).find((item) => item.id === templateId);
    if (!template) return;
    setForm((prev) => ({
      ...prev,
      name: prev.name || `${template.name} Bot`,
      strategy_type: template.strategy_type || prev.strategy_type,
      template_id: template.id,
      strategy_template_ids: prev.strategy_template_ids?.length ? prev.strategy_template_ids : [template.id],
    }));
    toast.success("Template bot formuna aktarıldı");
  };

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  useEffect(() => {
    const queryStrategyId = String(new URLSearchParams(location.search || "").get("strategy_id") || "");
    const queryStrategyExists = canonicalStrategyOptions.some((item) => item.strategy_id === queryStrategyId);

    if (!activeTemplateOptions.length && !canonicalStrategyOptions.length) return;
    setForm((prev) => {
      const mergedAllocations = toStrategyAllocationRows(canonicalStrategyOptions, prev.strategy_allocations);
      const primaryFromAllocations = pickPrimaryStrategyId(mergedAllocations, "");
      const firstCanonical = canonicalStrategyOptions[0]?.strategy_id || "";
      const firstTemplate = activeTemplateOptions[0] || null;

      const nextStrategyType =
        primaryFromAllocations
        ||
        (queryStrategyExists && queryStrategyId)
        || prev.strategy_type
        || firstCanonical
        || firstTemplate?.strategy_type
        || "";

      const matchedTemplate = activeTemplateOptions.find((item) => item.strategy_type === nextStrategyType);
      const nextTemplateId = prev.template_id || matchedTemplate?.id || firstTemplate?.id || "";

      const hasAllocationsChanged = JSON.stringify(mergedAllocations) !== JSON.stringify(prev.strategy_allocations || []);

      if (
        nextStrategyType === prev.strategy_type
        && nextTemplateId === prev.template_id
        && (prev.strategy_template_ids || []).length > 0
        && !hasAllocationsChanged
      ) {
        return prev;
      }

      return {
        ...prev,
        strategy_type: nextStrategyType,
        template_id: nextTemplateId,
        strategy_template_ids: nextTemplateId ? [nextTemplateId] : prev.strategy_template_ids,
        strategy_allocations: mergedAllocations,
      };
    });
  }, [activeTemplateOptions, canonicalStrategyOptions, location.search]);

  useEffect(() => {
    setForm((prev) => {
      const exists = walletConnectionOptions.some((item) => item.id === prev.exchange_connection_id);
      const fallbackConnectionId = exists
        ? prev.exchange_connection_id
        : String(walletConnectionOptions[0]?.id || "");
      if (fallbackConnectionId === prev.exchange_connection_id && prev.mode === "live_ready") return prev;
      return {
        ...prev,
        mode: "live_ready",
        exchange_connection_id: fallbackConnectionId,
      };
    });
  }, [walletConnectionOptions]);

  useEffect(() => {
    if (!riskPolicyOptions.length) return;
    setForm((prev) => {
      if (String(prev.risk_policy_id || "").trim()) return prev;
      return {
        ...prev,
        risk_policy_id: String(riskPolicyOptions[0]?.id || ""),
      };
    });
  }, [riskPolicyOptions]);

  const createUserTemplateFromCanonical = async (canonicalStrategy) => {
    const canonicalCode = String(canonicalStrategy?.strategy_id || "canonical_strategy").trim();
    const entryRules = canonicalStrategy?.entry_long?.rules || ["canonical_entry_signal"];
    const exitRules = canonicalStrategy?.exit_long?.rules || ["canonical_exit_signal"];
    const defaultParams = {
      ema_fast: 20,
      ema_slow: 50,
      rsi_low: 30,
      rsi_high: 70,
      macd_fast: 12,
      macd_slow: 26,
      bb_period: 20,
      adx_min: 20,
    };

    const payload = {
      name: `${canonicalCode} - Bot`,
      template_code: canonicalCode,
      strategy_type: canonicalCode,
      indicator_schema: {
        indicators: ["ema", "rsi", "macd", "bb", "adx"],
        timeframe: "15m",
        params: defaultParams,
      },
      param_schema: {
        ema_fast: { type: "int", default: 20 },
        ema_slow: { type: "int", default: 50 },
        rsi_low: { type: "int", default: 30 },
        rsi_high: { type: "int", default: 70 },
      },
      logic_schema: {
        entry_rules: { long_condition: entryRules.join(" AND "), threshold: 0 },
        exit_rules: { stop_loss_pct: 1.5, take_profit_pct: 3.0, exit_condition: exitRules.join(" OR ") },
        risk_hints: { position_size_hint_pct: 1.5, max_exposure_hint_pct: 20.0 },
      },
      parameters: defaultParams,
      reason_note: "bot_profiles_attach_canonical_strategy",
    };

    try {
      const { data } = await apiClient.post("/user/strategy-templates", payload);
      return data;
    } catch (error) {
      const message = parseApiErrorMessage(error, "Template servisine ulaşılamadı");
      throw new Error(`Template oluşturma hatası: ${message}`);
    }
  };

  const ensureStrategyTemplateId = async (effectiveStrategyType) => {
    const normalizedStrategyType = String(effectiveStrategyType || "").trim();

    if (form.use_template && form.template_id) {
      return form.template_id;
    }

    if (form.use_template && !form.template_id) {
      return null;
    }

    const matchedTemplate = activeTemplateOptions.find((item) => item.strategy_type === normalizedStrategyType);
    if (matchedTemplate?.id) {
      return matchedTemplate.id;
    }

    const selectedCanonicalStrategy = canonicalStrategyOptions.find((item) => item.strategy_id === normalizedStrategyType) || null;
    if (!selectedCanonicalStrategy) {
      return null;
    }

    try {
      const createdTemplate = await createUserTemplateFromCanonical(selectedCanonicalStrategy);
      return createdTemplate?.id || null;
    } catch (error) {
      const message = error?.message || "Template otomatik oluşturulamadı";
      toast.warning(`${message}. Template olmadan devam ediliyor.`);
      return null;
    }
  };

  const loadCustomWatchlists = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/symbol-selector/watchlists", { params: { source: "crypto" } });
      const filtered = (data || []).filter((item) => {
        const exchangeOk = String(item?.exchange || "").toLowerCase() === String(form.exchange || "").toLowerCase();
        const marketOk = String(item?.market_type || "").toLowerCase() === String(form.market_type || "").toLowerCase();
        return exchangeOk && marketOk;
      });
      setWatchlists(filtered);
    } catch {
      setWatchlists([]);
    }
  }, [form.exchange, form.market_type]);

  useEffect(() => {
    loadCustomWatchlists();
  }, [loadCustomWatchlists]);

  const applySymbolPreset = useCallback(async () => {
    const preset = String(form.symbol_preset || "top_50");
    if (preset === "custom_list") {
      const selectedWatchlist = (watchlists || []).find((item) => item.id === form.custom_watchlist_id);
      if (!selectedWatchlist) {
        toast.error("Özel liste seçin");
        return;
      }
      const watchSymbols = (selectedWatchlist.symbols || []).map((item) => String(item || "").toUpperCase()).filter(Boolean);
      setSelectedSymbols(watchSymbols);
      setSymbolMode("manual_selection");
      setForm((prev) => ({
        ...prev,
        symbol_source_type: LEGACY_TOP_FORM ? "scanner" : "manual",
        scanner_id: LEGACY_TOP_FORM ? "default" : prev.scanner_id,
      }));
      return;
    }

    setIsApplyingPreset(true);
    try {
      const effectiveExchange = String(form.exchange || "binance").toLowerCase() === "bybit" ? "binance" : String(form.exchange || "binance").toLowerCase();
      const { data } = await apiClient.get("/symbol-selector/universe", {
        params: {
          source: "crypto",
          exchange: effectiveExchange,
          market_type: form.market_type,
          mode: "all_market_symbols",
          quote_asset_filter: "USDT",
        },
      });
      const rows = Array.isArray(data?.rows) ? data.rows : [];
      let symbols = rows.map((item) => String(item?.symbol || "").toUpperCase()).filter(Boolean);
      if (preset === "top_50") symbols = symbols.slice(0, 50);
      if (preset === "top_100") symbols = symbols.slice(0, 100);

      setSelectedSymbols(symbols);
      setSymbolMode(preset === "all_symbols" ? "all_market_symbols" : "manual_selection");
      setForm((prev) => ({
        ...prev,
        symbol_source_type: LEGACY_TOP_FORM ? "scanner" : "manual",
        scanner_id: LEGACY_TOP_FORM ? "default" : prev.scanner_id,
      }));
      toast.success(`${symbols.length} sembol yüklendi`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preset sembol listesi yüklenemedi");
    } finally {
      setIsApplyingPreset(false);
    }
  }, [form.custom_watchlist_id, form.exchange, form.market_type, form.symbol_preset, watchlists]);

  const updateStrategyAllocationWeight = (strategyId, value) => {
    const numericValue = Number(value);
    const nextWeight = Number.isFinite(numericValue) ? Math.max(0, Math.min(1, numericValue)) : 0;
    setForm((prev) => {
      const rows = toStrategyAllocationRows(canonicalStrategyOptions, prev.strategy_allocations).map((row) => (
        row.strategy_id === strategyId
          ? { ...row, weight: Number(nextWeight.toFixed(6)) }
          : row
      ));
      return {
        ...prev,
        strategy_allocations: rows,
        strategy_type: pickPrimaryStrategyId(rows, prev.strategy_type),
      };
    });
  };

  const updateStrategyAllocationPriority = (strategyId, value) => {
    const numericValue = Number(value);
    const normalizedPriority = Number.isFinite(numericValue)
      ? Math.max(STRATEGY_PRIORITY_MIN, Math.min(STRATEGY_PRIORITY_MAX, Math.round(numericValue)))
      : 50;
    setForm((prev) => {
      const rows = toStrategyAllocationRows(canonicalStrategyOptions, prev.strategy_allocations).map((row) => (
        row.strategy_id === strategyId
          ? { ...row, priority: normalizedPriority }
          : row
      ));
      return {
        ...prev,
        strategy_allocations: rows,
        strategy_type: pickPrimaryStrategyId(rows, prev.strategy_type),
      };
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    const parsedSymbols = (selectedSymbols || []).length
      ? selectedSymbols
      : form.symbols
          .split(",")
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean);
    const nextErrors = {};

    if (!form.name.trim()) {
      nextErrors.name = "Bot Name zorunludur.";
    }
    if (parsedSymbols.length === 0) {
      nextErrors.symbols = "En az bir sembol girin.";
    }
    if ((LEGACY_TOP_FORM || String(form.symbol_source_type || "manual") === "scanner") && !String(form.scanner_id || "").trim()) {
      nextErrors.scanner_id = "Scanner source için scanner_id zorunlu.";
    }
    if (String(form.mode || "live_ready") === "live_ready" && !String(form.exchange_connection_id || "").trim()) {
      nextErrors.exchange_connection_id = "Bot için cüzdan seçimi zorunlu.";
    }
    if (!String(form.strategy_type || "").trim()) {
      nextErrors.strategy_type = "Canonical strateji seçimi zorunlu.";
    }
    const selectedStrategyAllocations = strategyAllocationRows
      .filter((row) => Number(row.weight || 0) > 0)
      .map((row) => ({
        strategy_id: String(row.strategy_id),
        family: String(row.family || "general"),
        weight: Number(Number(row.weight || 0).toFixed(6)),
        priority: Math.max(STRATEGY_PRIORITY_MIN, Math.min(STRATEGY_PRIORITY_MAX, Number(row.priority || 50))),
      }));

    if (selectedStrategyAllocations.length === 0) {
      nextErrors.strategy_allocations = "En az bir stratejiye weight verin.";
    }
    if (hasStrategyWeightOverflow) {
      nextErrors.strategy_allocations = "Weight toplamı 1.0 değerini geçemez.";
    }

    const effectiveStrategyType = pickPrimaryStrategyId(selectedStrategyAllocations, form.strategy_type);
    if (!String(effectiveStrategyType || "").trim()) {
      nextErrors.strategy_type = "Primary strategy belirlenemedi.";
    }

    if (String(form.mode || "live_ready") === "live_ready" && liveReadyBlockedReason) {
      nextErrors.mode = liveReadyBlockedReason;
    }
    setFormErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      toast.error("Form alanlarını kontrol edin");
      return;
    }

    try {
      const strategyTemplateId = await ensureStrategyTemplateId(effectiveStrategyType);
      if (form.use_template && !strategyTemplateId) {
        toast.error("Template seçimi zorunlu");
        return;
      }

      const selectedConnection = walletConnectionOptions.find((item) => item.id === form.exchange_connection_id);
      if (String(form.mode || "live_ready") === "live_ready" && !selectedConnection) {
        toast.error("Seçilen cüzdan bulunamadı");
        return;
      }

      const payload = {
        name: form.name.trim(),
        exchange_connection_id: form.exchange_connection_id || null,
        exchange: selectedConnection?.exchange || form.exchange,
        market_type: selectedConnection?.market_type || form.market_type,
        symbol_source_type: LEGACY_TOP_FORM ? 'scanner' : (form.symbol_source_type || 'manual'),
        scanner_id: LEGACY_TOP_FORM ? (form.scanner_id || 'default') : (form.symbol_source_type === 'scanner' ? (form.scanner_id || null) : null),
        symbols: parsedSymbols,
        strategy_type: effectiveStrategyType,
        strategy_allocations: selectedStrategyAllocations,
        strategy_template_id: strategyTemplateId,
        strategy_template_ids: form.use_template && strategyTemplateId ? [strategyTemplateId] : [],
        timeframe: form.timeframe || "15m",
        trend_timeframe: form.trend_timeframe || "1h",
        mode: "live_ready",
        leverage: Number(selectedRiskPolicy?.max_leverage || 1),
        is_enabled: Boolean(form.is_enabled),
        risk_adaptive_confirmed: false,
        risk_policy_id: form.risk_policy_id || null,
        risk_policy_snapshot: selectedRiskPolicy
          ? {
            id: selectedRiskPolicy.id,
            name: selectedRiskPolicy.name,
            max_leverage: selectedRiskPolicy.max_leverage,
            position_size_pct: selectedRiskPolicy.position_size_pct,
            daily_loss_cutoff_pct: selectedRiskPolicy.daily_loss_cutoff_pct,
            atr_stop_multiplier: selectedRiskPolicy.atr_stop_multiplier,
            risk_reward_ratio: selectedRiskPolicy.risk_reward_ratio,
          }
          : {},
      };

      if (editingId) {
        await apiClient.put(`/bot-profiles/${editingId}`, payload);
        toast.success("Bot profili güncellendi");
      } else {
        await apiClient.post("/bot-profiles", payload);
        toast.success("Bot profili oluşturuldu");
      }
      setEditingId(null);
      setForm(initialForm);
      setSelectedSymbols([]);
      setSymbolMode("all_market_symbols");
      setFormErrors({});
      fetchItems();
    } catch (error) {
      toast.error(parseApiErrorMessage(error, "Bot profili işlemi başarısız"));
    }
  };

  const onEdit = (item) => {
    const existingAllocations = Array.isArray(item?.strategy_allocations) ? item.strategy_allocations : [];
    const mergedAllocations = toStrategyAllocationRows(canonicalStrategyOptions, existingAllocations);
    const derivedStrategyType = pickPrimaryStrategyId(mergedAllocations, item.strategy_type);
    setEditingId(item.id);
    setForm({
      ...initialForm,
      ...item,
      symbols: (item.symbols || []).join(","),
      exchange_connection_id: item.selected_exchange_connection_id || "",
      mode: "live_ready",
      symbol_source_type: LEGACY_TOP_FORM ? "scanner" : (item.symbol_source_type || item.symbol_source || "manual"),
      scanner_id: item.scanner_id || item.symbol_source_summary?.scanner_id || "default",
      template_id: item.strategy_template_id || item.template_id || "",
      strategy_template_ids: item.strategy_template_ids || (item.strategy_template_id ? [item.strategy_template_id] : []),
      strategy_allocations: mergedAllocations,
      strategy_type: derivedStrategyType,
      use_template: Boolean(item.strategy_template_id),
      risk_adaptive_confirmed: false,
      risk_policy_id: item.selected_risk_policy_id || item.risk_policy_id || "",
      timeframe: item.timeframe || "15m",
      trend_timeframe: item.trend_timeframe || "1h",
    });
    setSymbolSource("crypto");
    setSymbolMode("manual_selection");
    setSelectedSymbols(item.symbols || []);
    setFormErrors({});
  };

  const toggleRunning = async (item) => {
    const isRunning = String(item?.status || "").toUpperCase() === "RUNNING" || Boolean(item?.is_running);
    const endpoint = isRunning ? "stop" : "start";
    const expectedState = endpoint === "start" ? "RUNNING" : "STOPPED";
    try {
      await apiClient.post(`/bot-profiles/${item.id}/${endpoint}`);
      toast.success(endpoint === "stop" ? "Bot durduruldu" : "Bot başlatıldı");
      await fetchItems();
    } catch (error) {
      try {
        const statusRes = await apiClient.get(`/bot-profiles/${item.id}/status`);
        const runtimeStatus = String(statusRes?.data?.status || "").toUpperCase();
        if (runtimeStatus === expectedState) {
          toast.success(endpoint === "stop" ? "Bot durduruldu" : "Bot başlatıldı");
          await fetchItems();
          return;
        }
      } catch {
        // status doğrulama da düşerse ana hatayı göstereceğiz
      }

      toast.error(parseApiErrorMessage(error, "Bot durumu değiştirilemedi"));
    }
  };

  const deleteBot = async (item) => {
    if (!window.confirm(`"${item.name}" bot profilini silmek istediğinize emin misiniz?`)) {
      return;
    }

    setDeletingBotId(item.id);
    try {
      await apiClient.delete(`/bot-profiles/${item.id}`);
      if (editingId === item.id) {
        setEditingId(null);
        setForm(initialForm);
        setSelectedSymbols([]);
        setSymbolMode("all_market_symbols");
        setFormErrors({});
      }
      toast.success("Bot profili silindi");
      await fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bot profili silinemedi");
    } finally {
      setDeletingBotId("");
    }
  };

  return (
    <section className="space-y-4" data-testid="bot-profiles-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="bot-profiles-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="bot-profiles-title">Bot Profile Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="bot-profiles-description">Eski bot ekranı aktif. Üst form legacy moda sabitlendi.</p>
      </header>

      <form onSubmit={handleSubmit} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="bot-profile-form">
        <div className="form-group" data-testid="bot-form-group-name">
          <label className="form-label" htmlFor="bot-form-name-input" data-testid="bot-form-name-label">Bot Name</label>
          <Input
            id="bot-form-name-input"
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            data-testid="bot-form-name-input"
            aria-label="Bot Name"
            aria-describedby="bot-form-name-helper bot-form-name-error"
            required
          />
          <p className="form-helper-text" id="bot-form-name-helper" data-testid="bot-form-name-helper">Botu ayırt etmek için benzersiz bir ad girin.</p>
          {formErrors.name && <p className="form-error-text" id="bot-form-name-error" data-testid="bot-form-name-error">{formErrors.name}</p>}
        </div>

        {!LEGACY_TOP_FORM && <div className="form-group" data-testid="bot-form-group-exchange">
          <label className="form-label" htmlFor="bot-form-exchange-select" data-testid="bot-form-exchange-label">Exchange</label>
          <select
            id="bot-form-exchange-select"
            value={form.exchange}
            onChange={(event) => {
              const nextExchange = event.target.value;
              setForm((prev) => ({
                ...prev,
                exchange: nextExchange,
                exchange_connection_id: "",
                mode: "live_ready",
              }));
            }}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-exchange-select"
            aria-label="Exchange"
            aria-describedby="bot-form-exchange-helper"
            required
          >
            {EXCHANGE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
          <p className="form-helper-text" id="bot-form-exchange-helper" data-testid="bot-form-exchange-helper">Exchange + market seçimi Diagnostics global flag ile doğrulanır.</p>
        </div>}

        <div className="form-group" data-testid="bot-form-group-market-type">
          <label className="form-label" htmlFor="bot-form-market-type-select" data-testid="bot-form-market-type-label">Market Type</label>
          <select
            id="bot-form-market-type-select"
            value={form.market_type}
            onChange={(event) => {
              setForm((prev) => ({
                ...prev,
                market_type: event.target.value,
                exchange_connection_id: "",
              }));
            }}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-market-type-select"
            aria-label="Market Type"
            aria-describedby="bot-form-market-type-helper"
            required
          >
            {MARKET_TYPE_OPTIONS.map((market) => (
              <option key={market.value} value={market.value}>{market.label}</option>
            ))}
          </select>
          <p className="form-helper-text" id="bot-form-market-type-helper" data-testid="bot-form-market-type-helper">Spot/Futures seçimi cüzdanı ve preset listeleri otomatik filtreler.</p>
        </div>

        {!LEGACY_TOP_FORM && <div className="form-group" data-testid="bot-form-group-wallet-connection">
          <label className="form-label" htmlFor="bot-form-wallet-connection-select" data-testid="bot-form-wallet-connection-label">Kullanılacak Cüzdan</label>
          <select
            id="bot-form-wallet-connection-select"
            value={form.exchange_connection_id || ""}
            onChange={(event) => {
              const connectionId = event.target.value;
              const selectedConnection = (walletConnectionOptions || []).find((item) => item.id === connectionId);
              setForm((prev) => ({
                ...prev,
                exchange_connection_id: connectionId,
                exchange: selectedConnection?.exchange || prev.exchange,
                market_type: selectedConnection?.market_type || prev.market_type,
              }));
            }}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-wallet-connection-select"
            required
          >
            <option value="">Cüzdan seçin (zorunlu)</option>
            {(walletConnectionOptions || []).map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.label}
              </option>
            ))}
          </select>
          <p className="form-helper-text" data-testid="bot-form-wallet-connection-helper">Bot sadece seçtiğiniz cüzdan bağlantısını kullanır.</p>
          {formErrors.exchange_connection_id && <p className="form-error-text" data-testid="bot-form-wallet-connection-error">{formErrors.exchange_connection_id}</p>}
          <div className="mt-2 rounded border border-slate-700/60 bg-slate-950/50 p-2 text-xs" data-testid="bot-form-wallet-live-balance-box">
            <p data-testid="bot-form-wallet-live-balance-value">Kullanılabilir Bakiye: <strong>{toNum(selectedWalletConnection?.available_balance).toFixed(2)} USDT</strong></p>
            <p data-testid="bot-form-wallet-live-pnl-value">PNL: <strong>{toNum(selectedWalletConnection?.pnl).toFixed(2)}$</strong></p>
            <p data-testid="bot-form-wallet-diagnostics-flag">Diagnostics Flag: {comboActivationState.flag} = {comboActivationState.active ? "true" : "false"}</p>
            {readBalancePermissionWarning && (
              <p className="mt-1 text-amber-300" data-testid="bot-form-wallet-read-balance-warning">{readBalancePermissionWarning}</p>
            )}
          </div>
        </div>}

        {LEGACY_TOP_FORM && (
          <div className="form-group" data-testid="bot-form-group-legacy-binding-summary">
            <label className="form-label" data-testid="bot-form-legacy-binding-label">Legacy Binding</label>
            <div className="rounded border border-slate-700/70 bg-slate-950/60 p-2 text-xs text-slate-300" data-testid="bot-form-legacy-binding-box">
              <p data-testid="bot-form-legacy-binding-source">Symbol Source: <strong>scanner</strong> (default)</p>
              <p data-testid="bot-form-legacy-binding-scanner">Scanner ID: <strong>{form.scanner_id || "default"}</strong></p>
              <p data-testid="bot-form-legacy-binding-wallet">Cüzdan: <strong>{selectedWalletConnection?.label || "otomatik"}</strong></p>
            </div>
          </div>
        )}

        <div className="form-group" data-testid="bot-form-group-symbols">
          <label className="form-label" htmlFor="bot-form-symbols-input" data-testid="bot-form-symbols-label">Symbols</label>
          <div className="mb-2 grid gap-2 md:grid-cols-3" data-testid="bot-form-symbol-preset-grid">
            <label className="space-y-1" data-testid="bot-form-symbol-preset-field">
              <span className="text-xs text-slate-400">Preset List</span>
              <select
                value={form.symbol_preset}
                onChange={(event) => setForm((prev) => ({ ...prev, symbol_preset: event.target.value }))}
                className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm"
                data-testid="bot-form-symbol-preset-select"
              >
                {SYMBOL_PRESET_OPTIONS.map((preset) => (
                  <option key={preset.value} value={preset.value}>{preset.label}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1" data-testid="bot-form-symbol-custom-list-field">
              <span className="text-xs text-slate-400">Custom List</span>
              <select
                value={form.custom_watchlist_id || ""}
                onChange={(event) => setForm((prev) => ({ ...prev, custom_watchlist_id: event.target.value }))}
                className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm"
                data-testid="bot-form-symbol-custom-list-select"
                disabled={form.symbol_preset !== "custom_list"}
              >
                <option value="">Seçiniz</option>
                {(watchlists || []).map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <div className="flex items-end" data-testid="bot-form-symbol-preset-apply-wrap">
              <Button type="button" variant="outline" onClick={applySymbolPreset} disabled={isApplyingPreset} data-testid="bot-form-symbol-preset-apply-button">
                {isApplyingPreset ? "Yükleniyor..." : "Preset Uygula"}
              </Button>
            </div>
          </div>
          <SymbolSelectorPanel
            testIdPrefix="bot-form-symbol-selector"
            exchange={form.exchange === "bybit" ? "binance" : form.exchange}
            marketType={form.market_type}
            source={symbolSource}
            onSourceChange={setSymbolSource}
            mode={symbolMode}
            onModeChange={setSymbolMode}
            selectedSymbols={selectedSymbols}
            onSelectedSymbolsChange={setSelectedSymbols}
            multi
          />
          <Input id="bot-form-symbols-input" value={selectedSymbols.join(",")} readOnly data-testid="bot-form-symbols-input" aria-label="Symbols" aria-describedby="bot-form-symbols-helper bot-form-symbols-error" required />
          <p className="form-helper-text" id="bot-form-symbols-helper" data-testid="bot-form-symbols-helper">Preset + custom list seçimleri market type (spot/futures) ile filtrelenir.</p>
          {formErrors.symbols && <p className="form-error-text" id="bot-form-symbols-error" data-testid="bot-form-symbols-error">{formErrors.symbols}</p>}
        </div>

        {!LEGACY_TOP_FORM && <div className="form-group" data-testid="bot-form-group-symbol-source">
          <label className="form-label" htmlFor="bot-form-symbol-source-select" data-testid="bot-form-symbol-source-label">Symbol Source</label>
          <select id="bot-form-symbol-source-select" value={form.symbol_source_type || "manual"} onChange={(event) => setForm((prev) => ({ ...prev, symbol_source_type: event.target.value }))} className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="bot-form-symbol-source-select">
            <option value="manual">manual</option>
            <option value="scanner">scanner</option>
          </select>
          {String(form.symbol_source_type || "manual") === "scanner" && <Input className="mt-2" value={form.scanner_id || ""} onChange={(event) => setForm((prev) => ({ ...prev, scanner_id: event.target.value }))} placeholder="scanner_id" data-testid="bot-form-scanner-id-input" />}
          {formErrors.scanner_id && <p className="form-error-text" data-testid="bot-form-scanner-id-error">{formErrors.scanner_id}</p>}
        </div>}

        <div className="form-group md:col-span-2" data-testid="bot-form-group-strategy-allocations">
          <label className="form-label" data-testid="bot-form-strategy-allocations-label">Strateji Ağırlık Dağılımı (12)</label>
          <p className="form-helper-text" data-testid="bot-form-strategy-allocations-helper">Kolonlar: strategy_id, family, weight, priority. Weight toplamı 1.0 değerini geçemez. Priority aralığı 1-100.</p>

          <div className="overflow-x-auto rounded border border-slate-700/70" data-testid="bot-form-strategy-allocations-table-wrap">
            <Table data-testid="bot-form-strategy-allocations-table">
              <TableHeader>
                <TableRow>
                  <TableHead data-testid="bot-form-strategy-col-strategy-id">strategy_id</TableHead>
                  <TableHead data-testid="bot-form-strategy-col-family">family</TableHead>
                  <TableHead data-testid="bot-form-strategy-col-weight">weight</TableHead>
                  <TableHead data-testid="bot-form-strategy-col-priority">priority</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {strategyAllocationRows.map((row) => (
                  <TableRow key={row.strategy_id} data-testid={`bot-form-strategy-row-${row.strategy_id}`}>
                    <TableCell className="font-mono text-xs" data-testid={`bot-form-strategy-id-${row.strategy_id}`}>{row.strategy_id}</TableCell>
                    <TableCell className="text-xs" data-testid={`bot-form-strategy-family-${row.strategy_id}`}>{row.family}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={row.weight}
                        onChange={(event) => updateStrategyAllocationWeight(row.strategy_id, event.target.value)}
                        data-testid={`bot-form-strategy-weight-input-${row.strategy_id}`}
                        aria-label={`${row.strategy_id} weight`}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step="1"
                        min={String(STRATEGY_PRIORITY_MIN)}
                        max={String(STRATEGY_PRIORITY_MAX)}
                        value={row.priority}
                        onChange={(event) => updateStrategyAllocationPriority(row.strategy_id, event.target.value)}
                        data-testid={`bot-form-strategy-priority-input-${row.strategy_id}`}
                        aria-label={`${row.strategy_id} priority`}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3" data-testid="bot-form-strategy-allocations-summary">
            <p className={`text-sm ${hasStrategyWeightOverflow ? "text-rose-300" : "text-emerald-300"}`} data-testid="bot-form-strategy-weight-total">
              Toplam Weight: {strategyWeightTotal.toFixed(4)} / {STRATEGY_WEIGHT_LIMIT.toFixed(1)}
            </p>
            <p className="text-sm text-slate-300" data-testid="bot-form-strategy-primary-id">Primary Strategy: <strong>{primaryStrategyType || "-"}</strong></p>
          </div>

          {formErrors.strategy_allocations && <p className="form-error-text" data-testid="bot-form-strategy-allocations-error">{formErrors.strategy_allocations}</p>}
          {formErrors.strategy_type && <p className="form-error-text" data-testid="bot-form-strategy-error">{formErrors.strategy_type}</p>}
        </div>

        {!LEGACY_TOP_FORM && <div className="form-group" data-testid="bot-form-group-risk-policy">
          <label className="form-label" htmlFor="bot-form-risk-policy-select" data-testid="bot-form-risk-policy-label">Risk Policy (Opsiyonel)</label>
          <select
            id="bot-form-risk-policy-select"
            value={form.risk_policy_id || ""}
            onChange={(event) => setForm((prev) => ({ ...prev, risk_policy_id: event.target.value }))}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-risk-policy-select"
          >
            <option value="">Risk policy seçin</option>
            {riskPolicyOptions.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
          <p className="form-helper-text" data-testid="bot-form-risk-policy-helper">Seçilen policy; kaldıraç ve risk limitlerini otomatik enjekte eder.</p>
          {selectedRiskPolicy && (
            <p className="text-xs text-slate-400" data-testid="bot-form-risk-policy-summary">
              Leverage: {selectedRiskPolicy.max_leverage}x · Risk/Trade: %{selectedRiskPolicy.position_size_pct} · SL ATR: {selectedRiskPolicy.atr_stop_multiplier}
            </p>
          )}
          {formErrors.risk_policy_id && <p className="form-error-text" data-testid="bot-form-risk-policy-error">{formErrors.risk_policy_id}</p>}
        </div>}

        {!LEGACY_TOP_FORM && <div className="form-group" data-testid="bot-form-group-template">
          <div className="flex items-center gap-2">
            <input
              id="bot-form-template-toggle"
              type="checkbox"
              checked={Boolean(form.use_template)}
              onChange={(event) => setForm((prev) => ({ ...prev, use_template: event.target.checked, template_id: event.target.checked ? prev.template_id : "" }))}
              data-testid="bot-form-template-toggle-checkbox"
            />
            <label htmlFor="bot-form-template-toggle" className="text-sm text-slate-200" data-testid="bot-form-template-toggle-label">Create from Template (Opsiyonel)</label>
          </div>
          {form.use_template && (
            <>
              <select
                id="bot-form-template-select"
                value={form.template_id}
                onChange={(event) => {
                  const value = event.target.value;
                  setForm((prev) => ({ ...prev, template_id: value, strategy_template_ids: value ? [value] : [] }));
                  applyTemplate(value);
                }}
                className="mt-2 h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                data-testid="bot-form-template-select"
              >
                <option value="">template seçin</option>
                {(activeTemplateOptions || []).map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
              <p className="form-helper-text" data-testid="bot-form-template-helper">Toggle açıksa template seçimi zorunlu olur.</p>
            </>
          )}
        </div>}

        {!LEGACY_TOP_FORM && <div className="form-group" data-testid="bot-form-group-mode">
          <label className="form-label" htmlFor="bot-form-mode-select" data-testid="bot-form-mode-label">Mode</label>
          <select id="bot-form-mode-select" value={form.mode} onChange={(event) => setForm((prev) => ({ ...prev, mode: event.target.value }))} className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="bot-form-mode-select" disabled>
            {BOT_MODE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <p className="form-helper-text" data-testid="bot-form-mode-helper">Sistem genelinde sadece LIVE-READY mod aktiftir.</p>
          {formErrors.mode && <p className="form-error-text" data-testid="bot-form-mode-error">{formErrors.mode}</p>}
        </div>}

        <div className="flex gap-2 md:col-span-2">
          <Button className="bg-orange-500 text-black hover:bg-orange-600" type="submit" data-testid="bot-form-submit-button" disabled={Boolean(liveReadyBlockedReason) || hasStrategyWeightOverflow} title={liveReadyBlockedReason || (hasStrategyWeightOverflow ? "Weight toplamı 1.0 değerini geçemez" : "")}>
            {editingId ? "Güncelle" : "Oluştur"}
          </Button>
          {liveReadyBlockedReason && (
            <p className="self-center text-xs text-amber-300" data-testid="bot-form-live-ready-blocked-warning">{liveReadyBlockedReason}</p>
          )}
          {editingId && (
            <Button
              type="button"
              variant="outline"
              className="border-slate-700 bg-transparent text-slate-200"
              onClick={() => {
                setEditingId(null);
                setForm(initialForm);
                setSelectedSymbols([]);
                setSymbolMode("all_market_symbols");
                setFormErrors({});
              }}
              data-testid="bot-form-cancel-edit-button"
            >
              İptal
            </Button>
          )}
        </div>
      </form>

      <div className="border border-slate-800 bg-slate-900" data-testid="bot-profiles-table-wrapper">
        <Table data-testid="bot-profiles-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="bot-table-head-name">Ad</TableHead>
              <TableHead data-testid="bot-table-head-market">Market</TableHead>
              <TableHead data-testid="bot-table-head-strategy">Strateji</TableHead>
              <TableHead data-testid="bot-table-head-strategy-weights">Weight/Priority</TableHead>
              <TableHead data-testid="bot-table-head-status">Status</TableHead>
              <TableHead data-testid="bot-table-head-mode">Mode</TableHead>
              <TableHead data-testid="bot-table-head-symbols">Semboller</TableHead>
              {!LEGACY_TOP_FORM && <TableHead data-testid="bot-table-head-parity">Backtest ↔ Live</TableHead>}
              {!LEGACY_TOP_FORM && <TableHead data-testid="bot-table-head-health">Health</TableHead>}
              {!LEGACY_TOP_FORM && <TableHead data-testid="bot-table-head-runtime">Runtime</TableHead>}
              <TableHead data-testid="bot-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} data-testid={`bot-table-row-${item.id}`}>
                {(() => {
                  const parity = findStrategyParity(item.strategy_type);
                  return (
                    <>
                <TableCell data-testid={`bot-table-name-${item.id}`}>{item.name}</TableCell>
                <TableCell data-testid={`bot-table-market-${item.id}`}>{item.market_type}</TableCell>
                <TableCell data-testid={`bot-table-strategy-${item.id}`}>{item.strategy_id || item.strategy_type}</TableCell>
                <TableCell className="text-xs" data-testid={`bot-table-strategy-weights-${item.id}`}>
                  {Array.isArray(item.strategy_allocations) && item.strategy_allocations.length > 0
                    ? item.strategy_allocations
                        .slice(0, 3)
                        .map((row) => `${row.strategy_id}:${Number(row.weight || 0).toFixed(2)}@${row.priority}`)
                        .join(" | ")
                    : "-"}
                </TableCell>
                <TableCell data-testid={`bot-table-status-${item.id}`}>{item.status || (item.is_running ? "RUNNING" : "IDLE")}</TableCell>
                <TableCell data-testid={`bot-table-mode-${item.id}`}>{item.mode || "live_ready"}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`bot-table-symbols-${item.id}`}>
                  {Array.isArray(item.symbols) && item.symbols.length > 0
                    ? `${item.symbols.slice(0, 8).join(", ")}${item.symbols.length > 8 ? ` +${item.symbols.length - 8}` : ""}`
                    : (item.symbol_source_summary?.summary || "-")}
                </TableCell>
                {!LEGACY_TOP_FORM && <TableCell data-testid={`bot-table-parity-${item.id}`}>{parity ? `${parity.backtest?.win_rate ?? 0} / ${parity.live?.win_rate ?? 0} / ${parity.deviation_pct ?? 0}%` : "-"}</TableCell>}
                {!LEGACY_TOP_FORM && <TableCell data-testid={`bot-table-health-${item.id}`}>{item.health || "HEALTHY"}</TableCell>}
                {!LEGACY_TOP_FORM && <TableCell data-testid={`bot-table-runtime-${item.id}`}>{item.last_heartbeat || (item.is_running ? "running" : "stopped")}</TableCell>}
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="border-cyan-400 bg-transparent text-cyan-200" onClick={() => setSelectedBot(item)} data-testid={`bot-table-open-detail-${item.id}`}>Detail</Button>
                    <Button size="sm" variant="outline" className="border-slate-600 bg-transparent" onClick={() => onEdit(item)} data-testid={`bot-table-edit-${item.id}`}>
                      Düzenle
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className={`bg-transparent ${(String(item?.status || "").toUpperCase() === "RUNNING" || item?.is_running) ? "border-red-400 text-red-300" : "border-green-400 text-green-300"}`}
                      onClick={() => toggleRunning(item)}
                      data-testid={`bot-table-toggle-running-${item.id}`}
                    >
                      {(String(item?.status || "").toUpperCase() === "RUNNING" || item?.is_running) ? "Stop" : "Start"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-amber-400 bg-transparent text-amber-200"
                      onClick={async () => {
                        try {
                          await apiClient.post(`/bot-profiles/${item.id}/pause`);
                          toast.success('Bot pause edildi');
                          await fetchItems();
                        } catch (error) {
                          toast.error(error?.response?.data?.detail || 'Bot pause işlemi başarısız');
                        }
                      }}
                      data-testid={`bot-table-pause-${item.id}`}
                    >
                      Pause
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-rose-500 bg-transparent text-rose-300"
                      onClick={() => deleteBot(item)}
                      data-testid={`bot-table-delete-${item.id}`}
                      disabled={deletingBotId === item.id}
                    >
                      {deletingBotId === item.id ? "Siliniyor..." : "Sil"}
                    </Button>
                  </div>
                </TableCell>
                    </>
                  );
                })()}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {selectedBot && (
        <section className="space-y-3 rounded-2xl border border-black/20 bg-white/10 p-4" data-testid="bot-detail-panel">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-xl font-bold text-slate-100" data-testid="bot-detail-title">{selectedBot.name}</h3>
              <p className="text-sm text-slate-300" data-testid="bot-detail-subtitle">{selectedBot.strategy_id || selectedBot.strategy_type} · {selectedBot.mode}</p>
            </div>
            <div className="flex flex-wrap gap-2" data-testid="bot-detail-tabs">
              {['overview','runtime','bindings','performance','logs','trades'].map((tab) => (
                <Button key={tab} size="sm" variant={detailTab === tab ? 'default' : 'outline'} onClick={() => setDetailTab(tab)} data-testid={`bot-detail-tab-${tab}`}>{tab}</Button>
              ))}
            </div>
          </div>
          {detailTab === 'overview' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-overview-json">{JSON.stringify((botStatus || {}).runtime_summary || selectedBot, null, 2)}</pre>}
          {detailTab === 'overview' && (
            <div className="rounded-xl border border-black/10 bg-white/70 p-3 text-sm text-black" data-testid="bot-detail-strategy-source-card">
              <p className="font-semibold" data-testid="bot-detail-strategy-source-title">Strategy Source</p>
              <p data-testid="bot-detail-strategy-template-name">template: {botStatus?.strategy_binding?.selected_template_code || botStatus?.strategy_binding?.selected_strategy_template_id || '-'}</p>
              <p data-testid="bot-detail-strategy-template-version">version: {botStatus?.strategy_binding?.selected_template_version || '-'}</p>
              <p data-testid="bot-detail-strategy-template-state">state: {botStatus?.strategy_binding?.selected_template_lifecycle_state || '-'}</p>
              <p data-testid="bot-detail-strategy-runtime-id">runtime strategy: {botStatus?.strategy_binding?.effective_runtime_strategy_id || '-'}</p>
              <p data-testid="bot-detail-strategy-lifecycle">compatibility: {botStatus?.compatibility?.parity || '-'}</p>
              <p data-testid="bot-detail-strategy-last-resolved">last_resolved_at: {botStatus?.strategy_binding?.last_resolved_at || '-'}</p>
              <pre className="mt-2 overflow-x-auto bg-white/60 p-2 text-[11px]" data-testid="bot-detail-strategy-effective-config">{JSON.stringify(botStatus?.strategy_binding?.effective_params || {}, null, 2)}</pre>
            </div>
          )}
          {detailTab === 'runtime' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-runtime-json">{JSON.stringify((botStatus || {}).runtime_summary || {}, null, 2)}</pre>}
          {detailTab === 'bindings' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-bindings-json">{JSON.stringify({ strategy_binding: botStatus?.strategy_binding, risk_binding: botStatus?.risk_binding, execution_binding: botStatus?.execution_binding, binding_validation: botStatus?.binding_validation, compatibility: botStatus?.compatibility, last_execution_summary: botStatus?.last_execution_summary }, null, 2)}</pre>}
          {detailTab === 'performance' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-performance-json">{JSON.stringify(botPerformance || {}, null, 2)}</pre>}
          {detailTab === 'logs' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-logs-json">{JSON.stringify(botLogs || [], null, 2)}</pre>}
          {detailTab === 'trades' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-trades-json">{JSON.stringify(botTrades || [], null, 2)}</pre>}
        </section>
      )}
    </section>
  );
};
