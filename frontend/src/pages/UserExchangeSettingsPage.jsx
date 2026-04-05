import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const initialForm = {
  exchange: "binance",
  mode: "live",
  api_key: "",
  api_secret: "",
};

const initialConnectionForm = {
  account_label: "",
  exchange: "binance",
  market_type: "spot",
  environment: "live",
  api_key: "",
  api_secret: "",
  is_default: false,
};

const fallbackVenue = {
  exchange: "binance",
  market_type: "futures",
  environment: "live",
};

const USER_EXCHANGE_SYMBOL_STORAGE_KEY = "user-exchange-selected-symbol-v1";

const AUTO_DEFAULT_LABEL_CANDIDATES = new Set([
  "default",
  "default binance spot live",
  "default binance / spot / live",
  "default-binance-spot-live",
  "default_binance_spot_live",
]);

const normalizeProfileLabel = (label) => String(label || "")
  .trim()
  .toLowerCase()
  .replaceAll("_", " ")
  .replaceAll("-", " ")
  .replaceAll("/", " ")
  .replace(/\s+/g, " ");

const isAutoDefaultProfile = (profile) => {
  const label = normalizeProfileLabel(profile?.account_label);
  if (!AUTO_DEFAULT_LABEL_CANDIDATES.has(label)) return false;
  return String(profile?.exchange || "").toLowerCase() === "binance"
    && String(profile?.market_type || "").toLowerCase() === "spot"
    && String(profile?.environment || "").toLowerCase() === "live";
};

const normalizeSymbolSelection = (symbols) => {
  if (!Array.isArray(symbols)) {
    return [];
  }
  return Array.from(
    new Set(symbols.map((item) => String(item || "").trim().toUpperCase()).filter(Boolean)),
  );
};

const isSameSymbolSelection = (left, right) => {
  const l = normalizeSymbolSelection(left);
  const r = normalizeSymbolSelection(right);
  if (l.length !== r.length) {
    return false;
  }
  return l.every((value, index) => value === r[index]);
};

const initialFuturesContext = {
  leverage: 3,
  margin_mode: "cross",
  position_side: "BOTH",
  risk_per_trade_pct: 20,
  max_daily_trades: 10,
  atr_stop_multiplier: 3,
};

export const UserExchangeSettingsPage = ({ embedded = false, mode = "management" }) => {
  const [activeTab, setActiveTab] = useState(mode === "diagnostics" ? "test" : "overview");
  const [settings, setSettings] = useState(null);
  const [permission, setPermission] = useState(null);
  const [validateResult, setValidateResult] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [ticker, setTicker] = useState(null);
  const [latestQuality, setLatestQuality] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testOrderResult, setTestOrderResult] = useState(null);
  const [lifecycleEvidence, setLifecycleEvidence] = useState(null);
  const [testOrderBanner, setTestOrderBanner] = useState("");
  const [riskSettings, setRiskSettings] = useState(null);
  const [riskPreview, setRiskPreview] = useState(null);
  const [portfolioOverview, setPortfolioOverview] = useState(null);
  const [futuresContext, setFuturesContext] = useState(initialFuturesContext);
  const [venueOptions, setVenueOptions] = useState([]);
  const [selectedVenue, setSelectedVenue] = useState(fallbackVenue);
  const [venueAccess, setVenueAccess] = useState(null);
  const [connectionProfiles, setConnectionProfiles] = useState([]);
  const [activeProfileId, setActiveProfileId] = useState("");
  const [connectionForm, setConnectionForm] = useState(initialConnectionForm);
  const [editingConnectionId, setEditingConnectionId] = useState("");
  const [isConnectionSaving, setIsConnectionSaving] = useState(false);
  const [validatingConnectionId, setValidatingConnectionId] = useState("");
  const [connectionErrors, setConnectionErrors] = useState({});
  const [riskFormErrors, setRiskFormErrors] = useState({});
  const [symbolSelectorSource, setSymbolSelectorSource] = useState("crypto");
  const [symbolSelectorMode, setSymbolSelectorMode] = useState("all_market_symbols");
  const [symbolSelectorSelection, setSymbolSelectorSelection] = useState([]);
  const [selectedSymbol, setSelectedSymbol] = useState("");

  const visibleConnectionProfiles = useMemo(
    () => (connectionProfiles || []).filter((item) => !isAutoDefaultProfile(item)),
    [connectionProfiles],
  );

  const exchangeOptions = useMemo(() => {
    const list = [...new Set(venueOptions.map((item) => item.exchange))];
    return list.length ? list : [fallbackVenue.exchange];
  }, [venueOptions]);

  const marketTypeOptions = useMemo(() => {
    const list = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === selectedVenue.exchange)
          .map((item) => item.market_type),
      ),
    ];
    return list.length ? list : [fallbackVenue.market_type];
  }, [selectedVenue.exchange, venueOptions]);

  const environmentOptions = useMemo(() => {
    const list = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === selectedVenue.exchange && item.market_type === selectedVenue.market_type)
          .map((item) => item.environment),
      ),
    ].filter((env) => String(env || "").toLowerCase() === "live");
    return list.length ? list : ["live"];
  }, [selectedVenue.exchange, selectedVenue.market_type, venueOptions]);

  const connectionHealthOverview = useMemo(() => {
    const summary = { total: 0, online: 0, degraded: 0, offline: 0, unknown: 0 };
    for (const profile of visibleConnectionProfiles || []) {
      summary.total += 1;
      const health = String(profile?.connection_health || "unknown").toLowerCase();
      if (health === "online") summary.online += 1;
      else if (health === "degraded") summary.degraded += 1;
      else if (health === "offline") summary.offline += 1;
      else summary.unknown += 1;
    }
    return summary;
  }, [visibleConnectionProfiles]);

  const getMarketProfileStatus = useCallback((marketType) => {
    const forMarket = (visibleConnectionProfiles || []).filter((item) => String(item?.market_type || "").toLowerCase() === marketType);
    const preferred = forMarket.find((item) => item.is_default) || forMarket[0] || null;
    const active = Boolean(
      preferred
      && String(preferred?.connection_health || "").toLowerCase() === "online"
      && Boolean(preferred?.can_trade_effective)
    );
    return {
      profile: preferred,
      active,
    };
  }, [visibleConnectionProfiles]);

  const spotProfileStatus = useMemo(() => getMarketProfileStatus("spot"), [getMarketProfileStatus]);
  const futuresProfileStatus = useMemo(() => getMarketProfileStatus("futures"), [getMarketProfileStatus]);

  const selectedConnectionProfile = useMemo(() => {
    if (!visibleConnectionProfiles.length) {
      return null;
    }

    const activeExplicit = visibleConnectionProfiles.find((item) => item.id === activeProfileId);
    if (activeExplicit) return activeExplicit;

    const exactDefault = visibleConnectionProfiles.find(
      (item) => item.is_default
        && item.exchange === selectedVenue.exchange
        && item.market_type === selectedVenue.market_type
        && item.environment === selectedVenue.environment,
    );
    if (exactDefault) return exactDefault;

    const exactAny = visibleConnectionProfiles.find(
      (item) => item.exchange === selectedVenue.exchange
        && item.market_type === selectedVenue.market_type
        && item.environment === selectedVenue.environment,
    );
    if (exactAny) return exactAny;

    return visibleConnectionProfiles.find((item) => item.is_default) || visibleConnectionProfiles[0] || null;
  }, [activeProfileId, selectedVenue.environment, selectedVenue.exchange, selectedVenue.market_type, visibleConnectionProfiles]);

  const actionRequiredProfiles = useMemo(
    () => (visibleConnectionProfiles || []).filter((item) => Boolean(item?.action_required)),
    [visibleConnectionProfiles],
  );

  useEffect(() => {
    if (!visibleConnectionProfiles.length) return;
    const preferred = visibleConnectionProfiles.find((item) => item.is_default) || visibleConnectionProfiles[0];
    if (preferred && preferred.id !== activeProfileId) {
      setActiveProfileId(preferred.id);
    }
  }, [activeProfileId, visibleConnectionProfiles]);

  useEffect(() => {
    if (!selectedConnectionProfile) return;
    setSelectedVenue({
      exchange: selectedConnectionProfile.exchange,
      market_type: selectedConnectionProfile.market_type,
      environment: selectedConnectionProfile.environment,
    });
  }, [selectedConnectionProfile]);

  const selectedHealthTimeline = useMemo(
    () => (selectedConnectionProfile?.health_history || []).slice().reverse().slice(0, 8),
    [selectedConnectionProfile],
  );

  const formatConnectionTime = (value) => {
    if (!value) return "-";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "-";
    return parsed.toLocaleString("tr-TR");
  };

  const formatRate = (value) => {
    if (value === null || value === undefined) return "-";
    const number = Number(value);
    if (Number.isNaN(number)) return "-";
    return `${number.toFixed(1)}%`;
  };

  const formatMs = (value) => {
    if (value === null || value === undefined) return "-";
    const num = Number(value);
    if (Number.isNaN(num)) return "-";
    return `${num.toFixed(2)} ms`;
  };

  const systemHealthBuckets = useMemo(() => {
    const raw = selectedConnectionProfile?.health_bucket_metrics || {};
    return ["1m", "5m", "15m"].map((key) => ({
      key,
      ...(raw[key] || {
        success: 0,
        fail: 0,
        success_rate: null,
        latency_samples: 0,
        jitter_p95_p50_ms: null,
        jitter_stddev_ms: null,
      }),
    }));
  }, [selectedConnectionProfile]);

  const selectedHealthDiagnostics = useMemo(() => {
    const health = String(selectedConnectionProfile?.connection_health || "unknown").toLowerCase();
    const reason = String(selectedConnectionProfile?.connection_health_reason || "").toLowerCase();
    const actionMessage = selectedConnectionProfile?.action_required_message || "";
    const nextRetry = selectedConnectionProfile?.next_retry_in_seconds;

    const reasonLabels = {
      missing_credentials: "API key/secret eksik",
      invalid_key: "API key geçersiz",
      ip_restriction: "IP whitelist kısıtı",
      missing_trade_permission: "Trade izni kapalı",
      rate_limit: "Rate limit nedeniyle beklemede",
      validation_failed: "Doğrulama başarısız",
      network_error: "Ağ bağlantı hatası",
      timeout: "Zaman aşımı",
      exchange_unreachable: "Borsa erişilemez",
    };

    const reasonLabel = reasonLabels[reason] || (reason || "belirsiz");
    const retryLabel = typeof nextRetry === "number" ? `${nextRetry}s` : "-";

    const toneClass =
      health === "online"
        ? "border-emerald-700/60 bg-emerald-900/20 text-emerald-200"
        : health === "degraded"
          ? "border-amber-700/60 bg-amber-900/20 text-amber-200"
          : "border-rose-700/60 bg-rose-900/20 text-rose-200";

    const recommendation =
      health === "online"
        ? "Bağlantı sağlıklı görünüyor."
        : actionMessage || "API bilgilerini ve Test & Validation adımlarını kontrol edin.";

    return {
      health,
      reason,
      reasonLabel,
      actionMessage,
      recommendation,
      retryLabel,
      toneClass,
    };
  }, [selectedConnectionProfile]);

  const profileHealthClass = (health) => {
    const normalized = String(health || "unknown").toLowerCase();
    if (normalized === "online") return "border-emerald-700/70 text-emerald-300 bg-emerald-900/20";
    if (normalized === "degraded") return "border-amber-700/70 text-amber-300 bg-amber-900/20";
    if (normalized === "offline") return "border-rose-700/70 text-rose-300 bg-rose-900/20";
    return "border-slate-700 text-slate-300 bg-slate-900/40";
  };

  const permissionBadges = (profile) => {
    const permissions = new Set((profile?.permission_snapshot || []).map((item) => String(item || "").toLowerCase()));
    return [
      { key: "read", active: permissions.has("read") },
      { key: "write", active: permissions.has("write") },
      { key: "trade", active: permissions.has("trade") },
      { key: "withdraw", active: permissions.has("withdraw"), danger: true },
    ];
  };

  const selectedAccountSnapshot = useMemo(() => {
    const snapshot = selectedConnectionProfile?.readiness_snapshot || {};
    return {
      available_balance: snapshot.available_balance ?? snapshot.free_balance ?? null,
      wallet_equity: snapshot.wallet_balance ?? snapshot.equity ?? snapshot.account_equity ?? null,
      open_order_margin: snapshot.open_order_margin ?? snapshot.order_margin ?? null,
      unrealized_pnl: snapshot.unrealized_pnl ?? snapshot.upnl ?? null,
      last_sync_time: selectedConnectionProfile?.last_validated_at || snapshot.last_sync_at || snapshot.validation_timestamp || null,
      stale_state: !selectedConnectionProfile?.last_validated_at,
    };
  }, [selectedConnectionProfile]);

  const selectedRateLimitState = useMemo(() => {
    const snapshot = selectedConnectionProfile?.readiness_snapshot || {};
    return {
      throttle_state: snapshot.throttle_state || snapshot.rate_limit_state || "unknown",
      retry_after: snapshot.retry_after_seconds ?? snapshot.next_retry_in_seconds ?? null,
      recent_hits: snapshot.recent_rate_limit_hits ?? snapshot.validation_fail_24h ?? 0,
    };
  }, [selectedConnectionProfile]);

  const loadAll = useCallback(async () => {
    try {
      const [settingsRes, permissionRes, readinessRes, riskRes, overviewRes, venueOptionsRes, connectionsRes] = await Promise.all([
        apiClient.get("/phase4/exchange-settings"),
        apiClient.get("/phase4/permission-status"),
        apiClient.get("/exchange/readiness-checklist", {
          params: {
            exchange: selectedVenue.exchange,
            market_type: selectedVenue.market_type,
            environment: selectedVenue.environment,
          },
        }),
        apiClient.get("/user-risk/settings"),
        apiClient.get("/user/portfolio"),
        apiClient.get("/venues/options"),
        apiClient.get("/user/exchange-connections"),
      ]);
      setSettings(settingsRes.data);
      setPermission(permissionRes.data);
      setReadiness(readinessRes.data);
      setRiskSettings(riskRes.data);
      setPortfolioOverview(overviewRes.data);
      const allowedVenueOptions = (venueOptionsRes.data || []).filter((item) => item.exchange !== "-");
      setVenueOptions(allowedVenueOptions);
      setConnectionProfiles(connectionsRes.data || []);
      setSelectedVenue((prev) => {
        const previousStillAvailable = allowedVenueOptions.find(
          (item) => item.exchange === prev.exchange && item.market_type === prev.market_type && item.environment === prev.environment,
        );
        if (previousStillAvailable) {
          return prev;
        }
        return allowedVenueOptions[0] || fallbackVenue;
      });
      setForm((prev) => ({
        ...prev,
        exchange: settingsRes.data?.exchange || prev.exchange,
        mode: settingsRes.data?.mode || prev.mode,
      }));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange ayarları yüklenemedi");
    }

    setLatestQuality((prev) => prev || null);
    setLifecycleEvidence((prev) => prev || null);
  }, [selectedVenue.environment, selectedVenue.exchange, selectedVenue.market_type]);

  const refreshConnectionProfiles = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/user/exchange-connections");
      setConnectionProfiles(Array.isArray(data) ? data : []);
    } catch {
      // Sessiz degrade: tam ekran yüklemesini bozma
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      refreshConnectionProfiles();
    }, 2000);

    return () => clearInterval(timer);
  }, [refreshConnectionProfiles]);

  useEffect(() => {
    const loadDefaultSymbolForVenue = async () => {
      try {
        const { data } = await apiClient.get("/symbol-selector/universe", {
          params: {
            source: "crypto",
            exchange: selectedVenue.exchange,
            market_type: selectedVenue.market_type,
            mode: "all_market_symbols",
            selected_symbols: "",
            query: "",
            quote_asset_filter: "USDT",
          },
        });

        const symbols = (data?.selected_symbols || []).map((item) => String(item || "").trim().toUpperCase()).filter(Boolean);
        const storedSymbol = typeof window !== "undefined" ? String(window.localStorage.getItem(USER_EXCHANGE_SYMBOL_STORAGE_KEY) || "").trim().toUpperCase() : "";
        const nextSymbol = storedSymbol && symbols.includes(storedSymbol) ? storedSymbol : (symbols[0] || "");

        setSymbolSelectorSelection((prev) => {
          const next = nextSymbol ? [nextSymbol] : [];
          return isSameSymbolSelection(prev, next) ? prev : next;
        });
        setSelectedSymbol(nextSymbol);
      } catch {
        setSymbolSelectorSelection((prev) => (prev.length === 0 ? prev : []));
        setSelectedSymbol("");
      }
    };

    loadDefaultSymbolForVenue();
  }, [selectedVenue.exchange, selectedVenue.market_type]);

  useEffect(() => {
    const nextSymbol = String(symbolSelectorSelection?.[0] || "").trim().toUpperCase();
    setSelectedSymbol(nextSymbol);
  }, [symbolSelectorSelection]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      if (selectedSymbol) {
        window.localStorage.setItem(USER_EXCHANGE_SYMBOL_STORAGE_KEY, selectedSymbol);
      } else {
        window.localStorage.removeItem(USER_EXCHANGE_SYMBOL_STORAGE_KEY);
      }
    }

    const loadTicker = async () => {
      if (!selectedSymbol) {
        setTicker(null);
        return;
      }
      try {
        const { data } = await apiClient.get("/market/ticker", { params: { symbol: selectedSymbol } });
        setTicker(data);
      } catch {
        setTicker(null);
      }
    };

    loadTicker();
  }, [selectedSymbol]);

  useEffect(() => {
    setForm((prev) => ({
      ...prev,
      exchange: selectedVenue.exchange,
      mode: selectedVenue.environment,
    }));
  }, [selectedVenue.environment, selectedVenue.exchange]);

  useEffect(() => {
    const runAccessCheck = async () => {
      try {
        const { data } = await apiClient.get("/venues/access-check", {
          params: {
            exchange: selectedVenue.exchange,
            market_type: selectedVenue.market_type,
            environment: selectedVenue.environment,
          },
        });
        setVenueAccess(data);
      } catch {
        setVenueAccess(null);
      }
    };
    runAccessCheck();
  }, [selectedVenue.environment, selectedVenue.exchange, selectedVenue.market_type]);

  useEffect(() => {
    const fetchPreview = async () => {
      try {
        const { data } = await apiClient.get("/user-risk/preview", {
          params: {
            market_type: selectedVenue.market_type,
            leverage: futuresContext.leverage,
            margin_mode: futuresContext.margin_mode,
            position_side: futuresContext.position_side,
            risk_per_trade_pct: futuresContext.risk_per_trade_pct,
            max_daily_trades: futuresContext.max_daily_trades,
            atr_stop_multiplier: futuresContext.atr_stop_multiplier,
          },
        });
        setRiskPreview(data);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Risk preview alınamadı");
      }
    };
    fetchPreview();
  }, [
    futuresContext.atr_stop_multiplier,
    futuresContext.leverage,
    futuresContext.margin_mode,
    futuresContext.max_daily_trades,
    futuresContext.position_side,
    futuresContext.risk_per_trade_pct,
    selectedVenue.market_type,
  ]);

  const onExchangeChange = (nextExchange) => {
    const markets = [
      ...new Set(
        venueOptions.filter((item) => item.exchange === nextExchange).map((item) => item.market_type),
      ),
    ];
    const nextMarket = markets[0] || fallbackVenue.market_type;
    const environments = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === nextExchange && item.market_type === nextMarket)
          .map((item) => item.environment),
      ),
    ];
    const nextEnvironment = environments[0] || fallbackVenue.environment;
    setSelectedVenue({ exchange: nextExchange, market_type: nextMarket, environment: nextEnvironment });
  };

  const onMarketTypeChange = (nextMarketType) => {
    const environments = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === selectedVenue.exchange && item.market_type === nextMarketType)
          .map((item) => item.environment),
      ),
    ];
    const nextEnvironment = environments[0] || fallbackVenue.environment;
    setSelectedVenue((prev) => ({ ...prev, market_type: nextMarketType, environment: nextEnvironment }));
  };

  const onEnvironmentChange = (nextEnvironment) => {
    setSelectedVenue((prev) => ({ ...prev, environment: nextEnvironment }));
  };

  const resetConnectionEditor = () => {
    setEditingConnectionId("");
    setConnectionErrors({});
    setConnectionForm((prev) => ({
      ...initialConnectionForm,
      exchange: selectedVenue.exchange || "binance",
      market_type: selectedVenue.market_type || "spot",
      environment: selectedVenue.environment || "live",
    }));
  };

  const startEditConnection = (connection) => {
    setEditingConnectionId(connection.id);
    setConnectionErrors({});
    setConnectionForm({
      account_label: connection.account_label,
      exchange: connection.exchange,
      market_type: connection.market_type,
      environment: connection.environment,
      api_key: "",
      api_secret: "",
      is_default: connection.is_default,
    });
  };

  const saveConnectionProfile = async () => {
    const nextErrors = {};
    if (!connectionForm.account_label.trim()) {
      nextErrors.account_label = "Account label zorunlu";
    }
    if (connectionForm.api_key && !connectionForm.api_secret) {
      nextErrors.api_secret = "API Key girildiğinde API Secret da girilmeli";
    }
    if (connectionForm.api_secret && !connectionForm.api_key) {
      nextErrors.api_key = "API Secret girildiğinde API Key de girilmeli";
    }

    setConnectionErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      toast.error("Connection form alanlarını kontrol edin");
      return;
    }

    setIsConnectionSaving(true);
    try {
      let savedConnection = null;
      const payload = {
        account_label: connectionForm.account_label.trim(),
        exchange: connectionForm.exchange,
        market_type: connectionForm.market_type,
        environment: connectionForm.environment,
        is_default: Boolean(connectionForm.is_default),
        api_key: connectionForm.api_key || undefined,
        api_secret: connectionForm.api_secret || undefined,
      };

      if (editingConnectionId) {
        const { data } = await apiClient.put(`/user/exchange-connections/${editingConnectionId}`, payload);
        savedConnection = data || null;
        toast.success("Connection profili güncellendi");
      } else {
        const { data } = await apiClient.post("/user/exchange-connections", payload);
        savedConnection = data || null;
        toast.success("Connection profili oluşturuldu");
      }

      resetConnectionEditor();
      setConnectionErrors({});
      await loadAll();

      const hasFreshCredentials = Boolean(connectionForm.api_key) && Boolean(connectionForm.api_secret);
      if (savedConnection?.id && hasFreshCredentials) {
        await apiClient.post(`/user/exchange-connections/${savedConnection.id}/revalidate`);
        await loadAll();
        toast.success("Profil doğrulandı, cüzdan snapshot güncellendi");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Connection profili kaydedilemedi");
    } finally {
      setIsConnectionSaving(false);
    }
  };

  const setProfileAsDefault = async (connectionId) => {
    try {
      await apiClient.post(`/user/exchange-connections/${connectionId}/set-default`);
      toast.success("Varsayılan connection güncellendi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Varsayılan connection güncellenemedi");
    }
  };

  const deleteConnectionProfile = async (connectionId) => {
    try {
      await apiClient.delete(`/user/exchange-connections/${connectionId}`);
      toast.success("Connection profili silindi");
      if (editingConnectionId === connectionId) {
        resetConnectionEditor();
      }
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Connection profili silinemedi");
    }
  };

  const revalidateConnectionProfile = useCallback(async (connection, { silent = false } = {}) => {
    setValidatingConnectionId(connection.id);
    try {
      await apiClient.post(`/user/exchange-connections/${connection.id}/revalidate`);
      if (!silent) {
        toast.success(`${connection.account_label} doğrulandı`);
      }
      await loadAll();
    } catch (error) {
      if (!silent) {
        toast.error(error?.response?.data?.detail || "Profil doğrulaması başarısız");
      }
    } finally {
      setValidatingConnectionId("");
    }
  }, [loadAll]);

  useEffect(() => {
    if (!selectedConnectionProfile) {
      return;
    }
    if (selectedConnectionProfile.connection_health !== "degraded" || !selectedConnectionProfile.is_reconnecting) {
      return;
    }

    const retryIn = Number(selectedConnectionProfile.next_retry_in_seconds ?? 0);
    if (retryIn > 0) {
      const timer = setTimeout(() => {
        revalidateConnectionProfile(selectedConnectionProfile, { silent: true });
      }, Math.max(1, retryIn) * 1000);
      return () => clearTimeout(timer);
    }

    revalidateConnectionProfile(selectedConnectionProfile, { silent: true });
  }, [
    revalidateConnectionProfile,
    selectedConnectionProfile,
    selectedConnectionProfile?.id,
    selectedConnectionProfile?.connection_health,
    selectedConnectionProfile?.is_reconnecting,
    selectedConnectionProfile?.next_retry_in_seconds,
  ]);

  const saveSettings = async (event) => {
    event.preventDefault();
    setIsSaving(true);
    try {
      const { data } = await apiClient.put("/phase4/exchange-settings", {
        ...form,
        exchange: selectedVenue.exchange,
        mode: selectedVenue.environment,
        market_type: selectedVenue.market_type,
      });
      setSettings(data);
      setForm(() => ({
        ...initialForm,
        exchange: selectedVenue.exchange,
        mode: selectedVenue.environment,
      }));
      toast.success("API key bilgileri kaydedildi ve Diagnostics bağlantısına senkronlandı");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ayarlar kaydedilemedi");
    } finally {
      setIsSaving(false);
    }
  };

  const saveRiskSettings = async () => {
    if (!riskSettings) {
      return;
    }

    const nextErrors = {};
    if (!Number(riskSettings.allocation_pct) || Number(riskSettings.allocation_pct) <= 0) {
      nextErrors.allocation_pct = "Allocation % 0'dan büyük olmalı";
    }
    if (!Number(riskSettings.trade_risk_pct) || Number(riskSettings.trade_risk_pct) <= 0) {
      nextErrors.trade_risk_pct = "Risk % Per Trade 0'dan büyük olmalı";
    }
    if (!Number(riskSettings.daily_loss_limit_pct) || Number(riskSettings.daily_loss_limit_pct) <= 0) {
      nextErrors.daily_loss_limit_pct = "Max Daily Loss % 0'dan büyük olmalı";
    }
    setRiskFormErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      toast.error("Risk form alanlarını kontrol edin");
      return;
    }

    try {
      const { data } = await apiClient.put("/user-risk/settings", {
        allocation_pct: Number(riskSettings.allocation_pct),
        trade_risk_pct: Number(riskSettings.trade_risk_pct),
        daily_loss_limit_pct: Number(riskSettings.daily_loss_limit_pct),
        compounding_enabled: Boolean(riskSettings.compounding_enabled),
      });
      setRiskSettings(data);
      setRiskFormErrors({});
      toast.success("Risk ayarları kaydedildi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk ayarları kaydedilemedi");
    }
  };

  const runPermission = async () => {
    setIsValidating(true);
    try {
      const { data } = await apiClient.get("/exchange/validate", {
        params: {
          exchange: selectedVenue.exchange,
          market_type: selectedVenue.market_type,
          environment: selectedVenue.environment,
        },
      });
      setValidateResult(data);
      setTestOrderBanner("");
      if (data?.assignment_autofixed) {
        toast.success("Venue assignment otomatik onarıldı");
      }
      toast.success("Exchange doğrulaması tamamlandı");
      await loadAll();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setValidateResult(typeof detail === "object" ? detail : null);
      if (typeof detail === "object") {
        const context = [detail.exchange, detail.market_type, detail.environment].filter(Boolean).join("/");
        const reason = Array.isArray(detail.reason_codes) ? detail.reason_codes.join(",") : detail.failure_code || detail.status || "validation_failed";
        const hint = detail?.hint ? ` | hint: ${detail.hint}` : "";
        setTestOrderBanner(context ? `${context}: ${reason}${hint}` : `${reason}${hint}`);
        if (detail?.hint) {
          toast.error(detail.hint);
        }
      }
      toast.error("Exchange doğrulaması başarısız");
    } finally {
      setIsValidating(false);
    }
  };

  const runFirstTestOrder = async () => {
    const venueEligible = selectedVenue.exchange === "binance" && selectedVenue.environment === "live";
    if (!venueEligible) {
      setTestOrderBanner("unsupported_venue_for_test_order: İlk kontrollü test emri yalnızca binance/live için açık.");
      toast.error("İlk kontrollü test emri yalnızca binance/live için desteklenir");
      return;
    }

    if (!selectedSymbol) {
      setTestOrderBanner("symbol_unavailable_for_selected_venue: Seçili venue için USDT sembolü bulunamadı.");
      toast.error("Seçili venue için uygun sembol bulunamadı");
      return;
    }

    setIsTesting(true);
    setTestOrderBanner("");
    try {
      const { data } = await apiClient.post("/exchange/test-order", null, {
        params: {
          exchange: selectedVenue.exchange,
          market_type: selectedVenue.market_type,
          environment: selectedVenue.environment,
          symbol: selectedSymbol,
          leverage: futuresContext.leverage,
          margin_mode: futuresContext.margin_mode,
          position_side: futuresContext.position_side,
        },
      });
      setTestOrderResult(data);
      setLatestQuality({
        execution_id: data.order_id,
        symbol: data.symbol || selectedSymbol,
        status: data.status,
        strategy_type: data.strategy_type,
        volatility_regime: data.volatility_regime,
        volatility_pct: data.volatility_pct,
        expected_price: ticker?.mid_price,
        fill_price: data.price_avg,
        slippage: data.slippage_pct,
        execution_latency: data.execution_time_ms,
        execution_quality_score: data.execution_quality_score,
        timestamp: new Date().toISOString(),
      });
      try {
        const evidenceRes = await apiClient.get("/exchange/lifecycle-evidence/latest");
        setLifecycleEvidence(evidenceRes.data);
      } catch (_) {
        setLifecycleEvidence(null);
      }
      toast.success("İlk kontrollü test emri gönderildi");
      await loadAll();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      if (typeof detail === "object") {
        const context = [detail.exchange, detail.market_type, detail.environment].filter(Boolean).join("/");
        const reason = `${detail.failure_code || "unknown_exchange_error"}: ${detail.message || "awaiting valid key"}`;
        setTestOrderBanner(context ? `${context}: ${reason}` : reason);
      }
      toast.error(typeof detail === "object" ? detail.message : (detail || "Test emri başarısız"));
    } finally {
      setIsTesting(false);
    }
  };

  const readinessTone = readiness?.readiness_status === "ready_for_test_order"
    ? "orange"
    : readiness?.readiness_status === "awaiting_valid_key"
      ? "blue"
      : "red";

  const validationState = isValidating
    ? "validating"
    : validateResult
      ? (validateResult.is_valid ? (validateResult.can_trade ? "valid_trade_enabled" : "valid_but_trade_blocked") : "invalid")
      : "not_run";

  const effectiveTradeState = useMemo(() => {
    if (isTesting) {
      return { state: "executing", tone: "orange", reason: "Test order gönderimi devam ediyor." };
    }
    if (isValidating) {
      return { state: "validating", tone: "blue", reason: "Exchange doğrulaması sürüyor." };
    }
    if (testOrderResult?.final_status) {
      return { state: `completed:${String(testOrderResult.final_status).toLowerCase()}`, tone: "orange", reason: "Son test-order akışı tamamlandı." };
    }

    const health = String(selectedConnectionProfile?.connection_health || "unknown").toLowerCase();
    if (health === "offline") {
      return {
        state: "blocked_connection_offline",
        tone: "red",
        reason: selectedConnectionProfile?.connection_health_reason || "connection_offline",
      };
    }
    if (health === "degraded") {
      const retrySec = selectedConnectionProfile?.next_retry_in_seconds;
      const retryText = typeof retrySec === "number" ? ` · next_retry_in=${retrySec}s` : "";
      return {
        state: "degraded_reconnecting",
        tone: "red",
        reason: `${selectedConnectionProfile?.connection_health_reason || "reconnect_in_progress"}${retryText}`,
      };
    }

    if (readiness?.is_validation_stale) {
      return { state: "blocked_stale_validation", tone: "red", reason: "Validation snapshot stale." };
    }
    if (readiness?.readiness_status && readiness.readiness_status !== "ready_for_test_order") {
      return {
        state: `blocked_gate_${String(readiness.readiness_status).toLowerCase()}`,
        tone: "red",
        reason: readiness?.last_error_reason || readiness.readiness_status,
      };
    }

    if (validateResult && (!validateResult.is_valid || !validateResult.can_trade)) {
      return {
        state: "blocked_validation_result",
        tone: "red",
        reason: Array.isArray(validateResult?.reason_codes)
          ? (validateResult.reason_codes.join(",") || "validation_blocked")
          : "validation_blocked",
      };
    }

    if (readiness?.readiness_status === "ready_for_test_order") {
      return { state: "ready_for_execution", tone: "orange", reason: "Gate + validation koşulları karşılanıyor." };
    }

    return { state: "pending", tone: "blue", reason: "Profil ve validation durumu bekleniyor." };
  }, [isTesting, isValidating, testOrderResult?.final_status, selectedConnectionProfile, readiness, validateResult]);

  const testOrderEligible = selectedVenue.exchange === "binance" && selectedVenue.environment === "live";

  return (
    <section className="space-y-4" data-testid="user-exchange-settings-page">
      {!embedded && <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-settings-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-exchange-settings-title">Exchange Settings</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-exchange-settings-description">
          Spot/Futures venue seçimine göre API doğrulama ve test-order akışı. Bilgiler plaintext değil, şifreli saklanır.
        </p>
      </header>}

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-active-profile-panel">
        <div className="grid gap-3 lg:grid-cols-[1.4fr,1fr]" data-testid="user-exchange-active-profile-grid">
          <div className="form-group" data-testid="user-exchange-active-profile-selector-group">
            <label className="form-label" htmlFor="user-exchange-active-profile-select" data-testid="user-exchange-active-profile-selector-label">Active Profile</label>
            <select
              id="user-exchange-active-profile-select"
              className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              value={activeProfileId}
              onChange={(event) => setActiveProfileId(event.target.value)}
              data-testid="user-exchange-active-profile-selector"
            >
              {(visibleConnectionProfiles || []).map((item) => (
                <option key={item.id} value={item.id}>{item.account_label} · {item.exchange}/{item.market_type}/{item.environment}</option>
              ))}
            </select>
            <p className="form-helper-text" data-testid="user-exchange-active-profile-selector-helper">Yanlış environment riskini azaltmak için aktif profil üstte açıkça seçilir.</p>
          </div>
          <div className="rounded border border-slate-700 bg-slate-950 p-3" data-testid="user-exchange-active-profile-summary-card">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-exchange-active-profile-summary-title">Active Profile Summary</p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2" data-testid="user-exchange-active-profile-status-grid">
              <div className="rounded border border-slate-700 bg-slate-900 p-2" data-testid="user-exchange-active-profile-spot-status-card">
                <div className="flex items-center gap-2">
                  <span className={`inline-block h-2.5 w-2.5 rounded-full ${spotProfileStatus.active ? "bg-emerald-400" : "bg-rose-500"}`} data-testid="user-exchange-active-profile-spot-status-light" />
                  <p className="text-xs font-semibold text-slate-100" data-testid="user-exchange-active-profile-spot-status-label">Spot</p>
                </div>
                <p className="mt-1 text-[11px] text-slate-400" data-testid="user-exchange-active-profile-spot-status-profile">{spotProfileStatus.profile?.account_label || "profil yok"}</p>
              </div>
              <div className="rounded border border-slate-700 bg-slate-900 p-2" data-testid="user-exchange-active-profile-futures-status-card">
                <div className="flex items-center gap-2">
                  <span className={`inline-block h-2.5 w-2.5 rounded-full ${futuresProfileStatus.active ? "bg-emerald-400" : "bg-rose-500"}`} data-testid="user-exchange-active-profile-futures-status-light" />
                  <p className="text-xs font-semibold text-slate-100" data-testid="user-exchange-active-profile-futures-status-label">Futures</p>
                </div>
                <p className="mt-1 text-[11px] text-slate-400" data-testid="user-exchange-active-profile-futures-status-profile">{futuresProfileStatus.profile?.account_label || "profil yok"}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2" data-testid="user-tabs-nav">
        {mode !== "diagnostics" && <Button className={activeTab === "overview" ? "bg-orange-500 text-black" : "bg-slate-800 text-slate-200"} onClick={() => setActiveTab("overview")} data-testid="user-tab-overview-button">Overview</Button>}
        {mode === "diagnostics" && <Button className={activeTab === "test" ? "bg-orange-500 text-black" : "bg-slate-800 text-slate-200"} onClick={() => setActiveTab("test")} data-testid="user-tab-test-validation-button">Diagnostics</Button>}
      </div>

      {activeTab === "overview" && (
        <div className="space-y-4" data-testid="user-overview-tab-content">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="user-overview-metrics-grid">
            <MetricCard label="Spot Cüzdan" value={portfolioOverview?.spot_wallet_balance ?? 0} tone="blue" testId="user-overview-spot-wallet-balance" />
            <MetricCard label="Futures Cüzdan" value={portfolioOverview?.futures_wallet_balance ?? 0} tone="orange" testId="user-overview-futures-wallet-balance" />
            <MetricCard label="Toplam Cüzdan" value={portfolioOverview?.total_wallet_balance ?? 0} tone="orange" testId="user-overview-total-wallet-balance" />
          </div>

          <section className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="user-overview-system-health-dashboard">
            <div className="flex flex-wrap items-center justify-between gap-2" data-testid="user-overview-system-health-header">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-overview-system-health-title">System Health Dashboard</p>
                <p className="text-xs text-slate-400" data-testid="user-overview-system-health-description">Bağlantı ritmi, son başarı/başarısızlık ve jitter takibi (1m / 5m / 15m kova).</p>
              </div>
              <p className="text-xs text-slate-400" data-testid="user-overview-system-health-profile-ref">
                Profile: {selectedConnectionProfile?.account_label || "-"}
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="user-overview-system-health-metrics-grid">
              <MetricCard label="Health" value={selectedConnectionProfile?.connection_health || "unknown"} tone={selectedConnectionProfile?.connection_health === "online" ? "orange" : "red"} testId="user-overview-system-health-current" />
              <MetricCard label="Last Success" value={formatConnectionTime(selectedConnectionProfile?.last_success_at)} tone="blue" testId="user-overview-system-health-last-success" />
              <MetricCard label="Last Fail" value={formatConnectionTime(selectedConnectionProfile?.last_failure_at)} tone="red" testId="user-overview-system-health-last-fail" />
              <MetricCard label="Anlık Jitter (p95-p50)" value={formatMs(selectedConnectionProfile?.current_jitter_p95_p50_ms)} tone="orange" testId="user-overview-system-health-current-jitter" />
              <MetricCard label="Anlık Jitter (stddev)" value={formatMs(selectedConnectionProfile?.current_jitter_stddev_ms)} tone="blue" testId="user-overview-system-health-current-jitter-stddev" />
            </div>

            <div
              className={`rounded border p-3 ${selectedHealthDiagnostics.toneClass}`}
              data-testid="user-overview-system-health-diagnostics-panel"
            >
              <p className="text-xs uppercase tracking-widest" data-testid="user-overview-system-health-diagnostics-title">Health Reason</p>
              <p className="mt-1 text-sm font-semibold" data-testid="user-overview-system-health-diagnostics-reason">
                reason: {selectedHealthDiagnostics.reasonLabel}
              </p>
              <p className="mt-1 text-xs" data-testid="user-overview-system-health-diagnostics-action-message">
                action: {selectedHealthDiagnostics.recommendation}
              </p>
              <p className="mt-1 text-xs" data-testid="user-overview-system-health-diagnostics-next-retry">
                next_retry_in: {selectedHealthDiagnostics.retryLabel}
              </p>
            </div>

            <div className="overflow-x-auto" data-testid="user-overview-system-health-bucket-table-wrap">
              <table className="min-w-full border border-slate-800 text-left text-xs" data-testid="user-overview-system-health-bucket-table">
                <thead className="bg-slate-950/70 text-slate-300" data-testid="user-overview-system-health-bucket-head">
                  <tr>
                    <th className="px-3 py-2" data-testid="user-overview-system-health-col-window">Bucket</th>
                    <th className="px-3 py-2" data-testid="user-overview-system-health-col-success">Success</th>
                    <th className="px-3 py-2" data-testid="user-overview-system-health-col-fail">Fail</th>
                    <th className="px-3 py-2" data-testid="user-overview-system-health-col-rate">Success Rate</th>
                    <th className="px-3 py-2" data-testid="user-overview-system-health-col-jitter-spread">Jitter p95-p50</th>
                    <th className="px-3 py-2" data-testid="user-overview-system-health-col-jitter-stddev">Jitter StdDev</th>
                    <th className="px-3 py-2" data-testid="user-overview-system-health-col-samples">Latency Samples</th>
                  </tr>
                </thead>
                <tbody data-testid="user-overview-system-health-bucket-body">
                  {systemHealthBuckets.map((bucket) => (
                    <tr key={bucket.key} className="border-t border-slate-800 text-slate-200" data-testid={`user-overview-system-health-bucket-row-${bucket.key}`}>
                      <td className="px-3 py-2" data-testid={`user-overview-system-health-bucket-window-${bucket.key}`}>{bucket.key}</td>
                      <td className="px-3 py-2" data-testid={`user-overview-system-health-bucket-success-${bucket.key}`}>{bucket.success ?? 0}</td>
                      <td className="px-3 py-2" data-testid={`user-overview-system-health-bucket-fail-${bucket.key}`}>{bucket.fail ?? 0}</td>
                      <td className="px-3 py-2" data-testid={`user-overview-system-health-bucket-rate-${bucket.key}`}>{formatRate(bucket.success_rate)}</td>
                      <td className="px-3 py-2" data-testid={`user-overview-system-health-bucket-jitter-spread-${bucket.key}`}>{formatMs(bucket.jitter_p95_p50_ms)}</td>
                      <td className="px-3 py-2" data-testid={`user-overview-system-health-bucket-jitter-stddev-${bucket.key}`}>{formatMs(bucket.jitter_stddev_ms)}</td>
                      <td className="px-3 py-2" data-testid={`user-overview-system-health-bucket-samples-${bucket.key}`}>{bucket.latency_samples ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="user-connection-profiles-panel">
            <div className="flex flex-wrap items-center justify-between gap-2" data-testid="user-connection-profiles-header">
              <div>
                <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-connection-profiles-title">Connection Profiles</p>
                <p className="text-xs text-slate-400" data-testid="user-connection-profiles-description">account_label + exchange + market_type + environment + default yönetimi.</p>
              </div>
              <Button variant="outline" onClick={resetConnectionEditor} data-testid="user-connection-profiles-reset-button">Yeni Profil</Button>
            </div>

            <div className="grid gap-2 md:grid-cols-3" data-testid="user-connection-profiles-form-grid">
              <div className="form-group" data-testid="user-connection-profile-account-label-group">
                <label className="form-label" htmlFor="user-connection-profile-account-label-input" data-testid="user-connection-profile-account-label-label">Account Label</label>
                <Input
                  id="user-connection-profile-account-label-input"
                  value={connectionForm.account_label}
                  onChange={(event) => setConnectionForm((prev) => ({ ...prev, account_label: event.target.value }))}
                  data-testid="user-connection-profile-account-label-input"
                  aria-label="Account Label"
                  aria-describedby="user-connection-profile-account-label-helper user-connection-profile-account-label-error"
                />
                <p className="form-helper-text" id="user-connection-profile-account-label-helper" data-testid="user-connection-profile-account-label-helper">Bağlantıyı ayırt eden kısa ad. Örn: main-futures-live</p>
                {connectionErrors.account_label && <p className="form-error-text" id="user-connection-profile-account-label-error" data-testid="user-connection-profile-account-label-error">{connectionErrors.account_label}</p>}
              </div>
              <div className="form-group" data-testid="user-connection-profile-exchange-group">
                <label className="form-label" htmlFor="user-connection-profile-exchange-select" data-testid="user-connection-profile-exchange-label">Exchange</label>
                <select
                  id="user-connection-profile-exchange-select"
                  className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                  value={connectionForm.exchange}
                  onChange={(event) => setConnectionForm((prev) => ({ ...prev, exchange: event.target.value }))}
                  data-testid="user-connection-profile-exchange-select"
                  aria-label="Exchange"
                  aria-describedby="user-connection-profile-exchange-helper"
                >
                  {exchangeOptions.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
                <p className="form-helper-text" id="user-connection-profile-exchange-helper" data-testid="user-connection-profile-exchange-helper">Bağlantının kullanılacağı borsa.</p>
              </div>
              <div className="form-group" data-testid="user-connection-profile-market-type-group">
                <label className="form-label" htmlFor="user-connection-profile-market-type-select" data-testid="user-connection-profile-market-type-label">Market Type</label>
                <select
                  id="user-connection-profile-market-type-select"
                  className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                  value={connectionForm.market_type}
                  onChange={(event) => setConnectionForm((prev) => ({ ...prev, market_type: event.target.value }))}
                  data-testid="user-connection-profile-market-type-select"
                  aria-label="Market Type"
                  aria-describedby="user-connection-profile-market-type-helper"
                >
                  <option value="spot">spot</option>
                  <option value="futures">futures</option>
                </select>
                <p className="form-helper-text" id="user-connection-profile-market-type-helper" data-testid="user-connection-profile-market-type-helper">Spot veya futures kanalını seçin.</p>
              </div>
              <div className="form-group" data-testid="user-connection-profile-environment-group">
                <label className="form-label" htmlFor="user-connection-profile-environment-select" data-testid="user-connection-profile-environment-label">Environment</label>
                <select
                  id="user-connection-profile-environment-select"
                  className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                  value={connectionForm.environment}
                  onChange={(event) => setConnectionForm((prev) => ({ ...prev, environment: event.target.value }))}
                  data-testid="user-connection-profile-environment-select"
                  aria-label="Environment"
                  aria-describedby="user-connection-profile-environment-helper"
                >
                  <option value="live">live</option>
                </select>
                <p className="form-helper-text" id="user-connection-profile-environment-helper" data-testid="user-connection-profile-environment-helper">Canlı ortam.</p>
              </div>
              <div className="form-group" data-testid="user-connection-profile-api-key-group">
                <label className="form-label" htmlFor="user-connection-profile-api-key-input" data-testid="user-connection-profile-api-key-label">API Key</label>
                <Input
                  id="user-connection-profile-api-key-input"
                  value={connectionForm.api_key}
                  onChange={(event) => setConnectionForm((prev) => ({ ...prev, api_key: event.target.value }))}
                  data-testid="user-connection-profile-api-key-input"
                  aria-label="API Key"
                  aria-describedby="user-connection-profile-api-key-helper user-connection-profile-api-key-error"
                />
                <p className="form-helper-text" id="user-connection-profile-api-key-helper" data-testid="user-connection-profile-api-key-helper">Opsiyonel güncelleme: mevcut key'i değiştirmek için doldurun.</p>
                {connectionErrors.api_key && <p className="form-error-text" id="user-connection-profile-api-key-error" data-testid="user-connection-profile-api-key-error">{connectionErrors.api_key}</p>}
              </div>
              <div className="form-group" data-testid="user-connection-profile-api-secret-group">
                <label className="form-label" htmlFor="user-connection-profile-api-secret-input" data-testid="user-connection-profile-api-secret-label">API Secret</label>
                <Input
                  id="user-connection-profile-api-secret-input"
                  value={connectionForm.api_secret}
                  onChange={(event) => setConnectionForm((prev) => ({ ...prev, api_secret: event.target.value }))}
                  data-testid="user-connection-profile-api-secret-input"
                  aria-label="API Secret"
                  aria-describedby="user-connection-profile-api-secret-helper user-connection-profile-api-secret-error"
                />
                <p className="form-helper-text" id="user-connection-profile-api-secret-helper" data-testid="user-connection-profile-api-secret-helper">Opsiyonel güncelleme: key ile birlikte girin.</p>
                {connectionErrors.api_secret && <p className="form-error-text" id="user-connection-profile-api-secret-error" data-testid="user-connection-profile-api-secret-error">{connectionErrors.api_secret}</p>}
              </div>
              <label className="md:col-span-3 flex items-center gap-2 text-sm text-slate-300" data-testid="user-connection-profile-default-toggle-wrapper">
                <input
                  type="checkbox"
                  checked={Boolean(connectionForm.is_default)}
                  onChange={(event) => setConnectionForm((prev) => ({ ...prev, is_default: event.target.checked }))}
                  data-testid="user-connection-profile-default-toggle"
                />
                default connection
              </label>
              <Button
                className="md:col-span-3 bg-orange-500 text-black hover:bg-orange-600"
                onClick={saveConnectionProfile}
                disabled={isConnectionSaving}
                data-testid="user-connection-profile-save-button"
              >
                {isConnectionSaving ? "Kaydediliyor..." : editingConnectionId ? "Connection Güncelle" : "Connection Ekle"}
              </Button>
            </div>

            <div className="space-y-2" data-testid="user-connection-profiles-list">
              {visibleConnectionProfiles.map((connection) => (
                <article key={connection.id} className="flex flex-wrap items-center justify-between gap-2 border border-slate-700 bg-slate-950 p-3" data-testid={`user-connection-profile-row-${connection.id}`}>
                  <div data-testid={`user-connection-profile-info-${connection.id}`}>
                    <p className="text-sm font-semibold text-slate-100" data-testid={`user-connection-profile-label-${connection.id}`}>{connection.account_label}{connection.is_default ? " (default)" : ""}</p>
                    <p className="text-xs text-slate-400" data-testid={`user-connection-profile-meta-${connection.id}`}>{connection.exchange} / {connection.market_type} / {connection.environment}</p>
                    <p className="mt-1" data-testid={`user-connection-profile-health-badge-wrap-${connection.id}`}>
                      <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs uppercase tracking-wide ${profileHealthClass(connection.connection_health)}`} data-testid={`user-connection-profile-health-badge-${connection.id}`}>
                        {connection.connection_health || "unknown"}
                      </span>
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2" data-testid={`user-connection-profile-permissions-${connection.id}`}>
                      {permissionBadges(connection).map((badge) => (
                        <span key={`${connection.id}-${badge.key}`} className={`inline-flex rounded border px-2 py-0.5 text-[11px] uppercase tracking-wide ${badge.active ? badge.danger ? "border-rose-600 text-rose-300 bg-rose-950/30" : "border-emerald-600 text-emerald-300 bg-emerald-950/20" : "border-slate-700 text-slate-400 bg-slate-900/40"}`} data-testid={`user-connection-profile-permission-badge-${connection.id}-${badge.key}`}>
                          {badge.key}
                        </span>
                      ))}
                    </div>
                    <p className="text-xs text-slate-500" data-testid={`user-connection-profile-readiness-${connection.id}`}>readiness: {connection.readiness_snapshot?.venue_state || "-"}</p>
                    <p className="text-xs text-slate-500" data-testid={`user-connection-profile-can-trade-${connection.id}`}>can_trade_effective: {String(Boolean(connection.can_trade_effective))}</p>
                    <p className="text-xs text-slate-500" data-testid={`user-connection-profile-last-validated-${connection.id}`}>last_validated_at: {formatConnectionTime(connection.last_validated_at)}</p>
                    <p className="text-xs text-slate-500" data-testid={`user-connection-profile-last-reason-${connection.id}`}>last_reason: {connection.connection_health_reason || "-"}</p>
                    <p className="text-xs text-slate-500" data-testid={`user-connection-profile-reconnect-${connection.id}`}>reconnecting: {String(Boolean(connection.is_reconnecting))}</p>
                    <p className="text-xs text-slate-500" data-testid={`user-connection-profile-next-retry-${connection.id}`}>next_retry_in: {typeof connection.next_retry_in_seconds === "number" ? `${connection.next_retry_in_seconds}s` : "-"}</p>
                    <p className="text-xs text-slate-500" data-testid={`user-connection-profile-action-required-${connection.id}`}>action_required: {String(Boolean(connection.action_required))}</p>
                  </div>
                  <div className="flex flex-wrap gap-2" data-testid={`user-connection-profile-actions-${connection.id}`}>
                    <Button size="sm" variant="outline" onClick={() => startEditConnection(connection)} data-testid={`user-connection-profile-edit-button-${connection.id}`}>Düzenle</Button>
                    <Button size="sm" variant="outline" onClick={() => revalidateConnectionProfile(connection)} disabled={validatingConnectionId === connection.id} data-testid={`user-connection-profile-revalidate-button-${connection.id}`}>
                      {validatingConnectionId === connection.id ? "Doğrulanıyor..." : "Revalidate"}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setProfileAsDefault(connection.id)} data-testid={`user-connection-profile-set-default-button-${connection.id}`}>Default Yap</Button>
                    <Button size="sm" variant="outline" onClick={() => window.location.assign('/user/exchange-diagnostics')} data-testid={`user-connection-profile-open-diagnostics-button-${connection.id}`}>Open Diagnostics</Button>
                    <Button size="sm" className="bg-rose-600 text-white hover:bg-rose-500" onClick={() => deleteConnectionProfile(connection.id)} data-testid={`user-connection-profile-delete-button-${connection.id}`}>Sil</Button>
                  </div>
                </article>
              ))}
              {visibleConnectionProfiles.length === 0 && (
                <p className="text-sm text-slate-400" data-testid="user-connection-profiles-empty">Henüz connection profili yok.</p>
              )}
            </div>
          </section>

          <section className="grid gap-3 lg:grid-cols-2" data-testid="user-exchange-account-snapshot-grid">
            <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-account-snapshot-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500">Account Snapshot</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <MetricCard label="Available" value={selectedAccountSnapshot.available_balance ?? "-"} tone="blue" testId="user-exchange-account-available" />
                <MetricCard label="Wallet / Equity" value={selectedAccountSnapshot.wallet_equity ?? "-"} tone="orange" testId="user-exchange-account-equity" />
                <MetricCard label="Open Order Margin" value={selectedAccountSnapshot.open_order_margin ?? "-"} tone="blue" testId="user-exchange-account-order-margin" />
                <MetricCard label="Unrealized PnL" value={selectedAccountSnapshot.unrealized_pnl ?? "-"} tone="orange" testId="user-exchange-account-unrealized-pnl" />
              </div>
              <p className="mt-3 text-xs text-slate-400" data-testid="user-exchange-account-last-sync">last_sync: {formatConnectionTime(selectedAccountSnapshot.last_sync_time)}</p>
              <p className="text-xs text-slate-400" data-testid="user-exchange-account-stale-state">state: {selectedAccountSnapshot.stale_state ? "stale" : "synced"}</p>
              {selectedAccountSnapshot.wallet_equity === null && (
                <p className="mt-2 text-xs text-amber-300" data-testid="user-exchange-account-missing-wallet-hint">
                  Cüzdan verisi yok. Profile Revalidate çalıştırın veya key/permission kontrol edin.
                </p>
              )}
            </div>
            <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-security-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500">Credential Security</p>
              <p className="mt-2 text-sm text-slate-200" data-testid="user-exchange-security-masked-key">masked_api_key: {selectedConnectionProfile?.masked_api_key || "-"}</p>
              <p className="mt-1 text-sm text-slate-200" data-testid="user-exchange-security-key-masked">key masked: {String(Boolean(selectedConnectionProfile?.has_api_key))}</p>
              <p className="mt-1 text-sm text-slate-200" data-testid="user-exchange-security-secret-masked">secret masked: {String(Boolean(selectedConnectionProfile?.has_api_secret))}</p>
              <p className="mt-1 text-sm text-slate-200" data-testid="user-exchange-security-fingerprint">fingerprint: {selectedConnectionProfile?.credential_fingerprint || "-"}</p>
              <p className="mt-1 text-sm text-slate-200" data-testid="user-exchange-security-updated-at">updated_at: {formatConnectionTime(selectedConnectionProfile?.updated_at)}</p>
            </div>
          </section>

          <section className="grid gap-3 lg:grid-cols-2" data-testid="user-exchange-validation-operations-grid">
            <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-validation-breakdown-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500">Validation Breakdown</p>
              <div className="mt-3 space-y-2 text-sm text-slate-200">
                <p data-testid="user-exchange-validation-credential-status">credential_status: {selectedConnectionProfile?.has_api_key && selectedConnectionProfile?.has_api_secret ? "present" : "missing"}</p>
                <p data-testid="user-exchange-validation-permission-status">permission_status: {selectedConnectionProfile?.can_trade_effective ? "trade-ready" : "restricted"}</p>
                <p data-testid="user-exchange-validation-environment-status">environment_match: {selectedConnectionProfile?.environment_valid ? "match" : "mismatch"}</p>
                <p data-testid="user-exchange-validation-reachability-status">venue_reachability: {selectedConnectionProfile?.connection_health || "unknown"}</p>
                <p data-testid="user-exchange-validation-verdict">trade_ready_verdict: {selectedConnectionProfile?.can_trade_effective ? "ready" : "blocked"}</p>
                <p data-testid="user-exchange-validation-required-action">required_action: {selectedConnectionProfile?.action_required_message || "none"}</p>
              </div>
            </div>
            <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-validation-history-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500">Connection Test History</p>
              <div className="mt-3 space-y-2" data-testid="user-exchange-validation-history-list">
                {(selectedHealthTimeline || []).map((item, index) => (
                  <div key={`${item.at || 'na'}-${index}`} className="border border-slate-700 p-2 text-xs" data-testid={`user-exchange-validation-history-item-${index}`}>
                    <p>{formatConnectionTime(item.at)} · {item.health || "unknown"}</p>
                    <p>reason: {item.reason || "-"}</p>
                    <p>source: {item.source || "-"} · latency: {formatMs(item.latency_ms)}</p>
                  </div>
                ))}
                {selectedHealthTimeline.length === 0 && <p className="text-sm text-slate-400" data-testid="user-exchange-validation-history-empty">Henüz validation geçmişi yok.</p>}
              </div>
            </div>
          </section>
        </div>
      )}

      {false && activeTab === "risk" && (
        <div className="space-y-4" data-testid="user-risk-settings-tab-content">
          <div className="grid gap-2 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="user-risk-venue-selection-grid">
            <div className="form-group" data-testid="user-risk-venue-exchange-group">
              <label className="form-label" htmlFor="user-risk-venue-exchange-select" data-testid="user-risk-venue-exchange-label">Exchange</label>
              <select id="user-risk-venue-exchange-select" value={selectedVenue.exchange} onChange={(event) => onExchangeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-risk-venue-exchange-select" aria-label="Exchange" aria-describedby="user-risk-venue-exchange-helper">
                {exchangeOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <p className="form-helper-text" id="user-risk-venue-exchange-helper" data-testid="user-risk-venue-exchange-helper">Risk hesaplamasının yapılacağı borsa.</p>
            </div>
            <div className="form-group" data-testid="user-risk-venue-market-type-group">
              <label className="form-label" htmlFor="user-risk-venue-market-type-select" data-testid="user-risk-venue-market-type-label">Market Type</label>
              <select id="user-risk-venue-market-type-select" value={selectedVenue.market_type} onChange={(event) => onMarketTypeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-risk-venue-market-type-select" aria-label="Market Type" aria-describedby="user-risk-venue-market-type-helper">
                {marketTypeOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <p className="form-helper-text" id="user-risk-venue-market-type-helper" data-testid="user-risk-venue-market-type-helper">Spot veya futures risk modunu seçin.</p>
            </div>
            <div className="form-group" data-testid="user-risk-venue-environment-group">
              <label className="form-label" htmlFor="user-risk-venue-environment-select" data-testid="user-risk-venue-environment-label">Environment</label>
              <select id="user-risk-venue-environment-select" value={selectedVenue.environment} onChange={(event) => onEnvironmentChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-risk-venue-environment-select" aria-label="Environment" aria-describedby="user-risk-venue-environment-helper">
                {environmentOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <p className="form-helper-text" id="user-risk-venue-environment-helper" data-testid="user-risk-venue-environment-helper">Sadece live ortamı.</p>
            </div>
            <p className="md:col-span-3 text-xs text-slate-400" data-testid="user-risk-selected-venue-summary">Seçili venue: {selectedVenue.exchange} / {selectedVenue.market_type} / {selectedVenue.environment}</p>
            {venueOptions.length === 0 && (
              <p className="md:col-span-3 text-xs text-yellow-300" data-testid="user-risk-no-assignment-warning">Henüz venue assignment yok. Admin panelden kullanıcıya venue atanmalı.</p>
            )}
          </div>

          <div className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-4" data-testid="user-risk-dual-mode-panel">
            <p className="md:col-span-4 text-xs uppercase tracking-widest text-slate-500" data-testid="user-risk-dual-mode-title">
              Mod: {selectedVenue.market_type === "futures" ? "Futures" : "Spot"}
            </p>

            {selectedVenue.market_type === "futures" && (
              <>
                <div className="form-group" data-testid="user-futures-leverage-group">
                  <label className="form-label" htmlFor="user-futures-leverage-input" data-testid="user-futures-leverage-label">Leverage</label>
                  <Input
                    id="user-futures-leverage-input"
                    type="number"
                    min={1}
                    max={20}
                    value={futuresContext.leverage}
                    onChange={(event) => setFuturesContext((prev) => ({ ...prev, leverage: Number(event.target.value) || 1 }))}
                    data-testid="user-futures-leverage-input"
                    aria-label="Leverage"
                    aria-describedby="user-futures-leverage-helper"
                  />
                  <p className="form-helper-text" id="user-futures-leverage-helper" data-testid="user-futures-leverage-helper">Futures işlem çarpanı.</p>
                </div>
                <div className="form-group" data-testid="user-futures-margin-mode-group">
                  <label className="form-label" htmlFor="user-futures-margin-mode-select" data-testid="user-futures-margin-mode-label">Margin Mode</label>
                  <select
                    id="user-futures-margin-mode-select"
                    value={futuresContext.margin_mode}
                    onChange={(event) => setFuturesContext((prev) => ({ ...prev, margin_mode: event.target.value }))}
                    className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    data-testid="user-futures-margin-mode-select"
                    aria-label="Margin Mode"
                    aria-describedby="user-futures-margin-mode-helper"
                  >
                    <option value="cross">cross</option>
                    <option value="isolated">isolated</option>
                  </select>
                  <p className="form-helper-text" id="user-futures-margin-mode-helper" data-testid="user-futures-margin-mode-helper">Cross veya isolated marjin tipi.</p>
                </div>
                <div className="form-group" data-testid="user-futures-position-side-group">
                  <label className="form-label" htmlFor="user-futures-position-side-select" data-testid="user-futures-position-side-label">Position Mode</label>
                  <select
                    id="user-futures-position-side-select"
                    value={futuresContext.position_side}
                    onChange={(event) => setFuturesContext((prev) => ({ ...prev, position_side: event.target.value }))}
                    className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                    data-testid="user-futures-position-side-select"
                    aria-label="Position Mode"
                    aria-describedby="user-futures-position-side-helper"
                  >
                    <option value="BOTH">BOTH</option>
                    <option value="LONG">LONG</option>
                    <option value="SHORT">SHORT</option>
                  </select>
                  <p className="form-helper-text" id="user-futures-position-side-helper" data-testid="user-futures-position-side-helper">Hedge modu için yön seçimi.</p>
                </div>
                <div className="form-group" data-testid="user-futures-risk-per-trade-group">
                  <label className="form-label" htmlFor="user-futures-risk-per-trade-input" data-testid="user-futures-risk-per-trade-label">Risk % Per Trade</label>
                  <Input
                    id="user-futures-risk-per-trade-input"
                    type="number"
                    min={1}
                    max={100}
                    value={futuresContext.risk_per_trade_pct}
                    onChange={(event) => setFuturesContext((prev) => ({ ...prev, risk_per_trade_pct: Number(event.target.value) || 1 }))}
                    data-testid="user-futures-risk-per-trade-input"
                    aria-label="Risk % Per Trade"
                    aria-describedby="user-futures-risk-per-trade-helper"
                  />
                  <p className="form-helper-text" id="user-futures-risk-per-trade-helper" data-testid="user-futures-risk-per-trade-helper">Her işlem için risk yüzdesi.</p>
                </div>
                <div className="form-group" data-testid="user-futures-max-daily-trades-group">
                  <label className="form-label" htmlFor="user-futures-max-daily-trades-input" data-testid="user-futures-max-daily-trades-label">Max Daily Trades</label>
                  <Input
                    id="user-futures-max-daily-trades-input"
                    type="number"
                    min={1}
                    max={200}
                    value={futuresContext.max_daily_trades}
                    onChange={(event) => setFuturesContext((prev) => ({ ...prev, max_daily_trades: Number(event.target.value) || 1 }))}
                    data-testid="user-futures-max-daily-trades-input"
                    aria-label="Max Daily Trades"
                    aria-describedby="user-futures-max-daily-trades-helper"
                  />
                  <p className="form-helper-text" id="user-futures-max-daily-trades-helper" data-testid="user-futures-max-daily-trades-helper">Günlük işlem üst limiti.</p>
                </div>
                <div className="form-group" data-testid="user-futures-atr-stop-multiplier-group">
                  <label className="form-label" htmlFor="user-futures-atr-stop-multiplier-input" data-testid="user-futures-atr-stop-multiplier-label">ATR Stop Multiplier</label>
                  <Input
                    id="user-futures-atr-stop-multiplier-input"
                    type="number"
                    min={0.5}
                    step="0.1"
                    value={futuresContext.atr_stop_multiplier}
                    onChange={(event) => setFuturesContext((prev) => ({ ...prev, atr_stop_multiplier: Number(event.target.value) || 1 }))}
                    data-testid="user-futures-atr-stop-multiplier-input"
                    aria-label="ATR Stop Multiplier"
                    aria-describedby="user-futures-atr-stop-multiplier-helper"
                  />
                  <p className="form-helper-text" id="user-futures-atr-stop-multiplier-helper" data-testid="user-futures-atr-stop-multiplier-helper">ATR tabanlı stop mesafesi katsayısı.</p>
                </div>
                <p className="text-sm text-yellow-300 md:col-span-4" data-testid="user-futures-liquidation-risk-text">
                  liquidation risk: leverage arttıkça likidasyon buffer düşer.
                </p>
              </>
            )}

            {selectedVenue.market_type === "spot" && (
              <p className="md:col-span-4 text-sm text-emerald-300" data-testid="user-spot-fields-hidden-text">
                Spot modda leverage / margin_mode / position_side / liquidation risk alanları gizlenir. Test order quoteQty ile çalışır.
              </p>
            )}
          </div>

          <div className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="user-risk-settings-form-grid">
            <div className="form-group" data-testid="user-risk-allocation-group">
              <label className="form-label" htmlFor="user-risk-allocation-input" data-testid="user-risk-allocation-label">Position Size (%)</label>
              <Input id="user-risk-allocation-input" type="number" min={1} max={50} value={riskSettings?.allocation_pct ?? 20} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), allocation_pct: event.target.value }))} data-testid="user-risk-allocation-input" aria-label="Position Size (%)" aria-describedby="user-risk-allocation-helper user-risk-allocation-error" />
              <p className="form-helper-text" id="user-risk-allocation-helper" data-testid="user-risk-allocation-helper">Toplam sermayeden işleme ayrılacak oran.</p>
              {riskFormErrors.allocation_pct && <p className="form-error-text" id="user-risk-allocation-error" data-testid="user-risk-allocation-error">{riskFormErrors.allocation_pct}</p>}
            </div>
            <div className="form-group" data-testid="user-risk-trade-risk-group">
              <label className="form-label" htmlFor="user-risk-trade-risk-input" data-testid="user-risk-trade-risk-label">Risk % Per Trade</label>
              <Input id="user-risk-trade-risk-input" type="number" min={1} max={25} value={riskSettings?.trade_risk_pct ?? 10} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), trade_risk_pct: event.target.value }))} data-testid="user-risk-trade-risk-input" aria-label="Risk % Per Trade" aria-describedby="user-risk-trade-risk-helper user-risk-trade-risk-error" />
              <p className="form-helper-text" id="user-risk-trade-risk-helper" data-testid="user-risk-trade-risk-helper">Her işlemde göze alınacak risk yüzdesi.</p>
              {riskFormErrors.trade_risk_pct && <p className="form-error-text" id="user-risk-trade-risk-error" data-testid="user-risk-trade-risk-error">{riskFormErrors.trade_risk_pct}</p>}
            </div>
            <div className="form-group" data-testid="user-risk-daily-loss-group">
              <label className="form-label" htmlFor="user-risk-daily-loss-input" data-testid="user-risk-daily-loss-label">Max Daily Loss (%)</label>
              <Input id="user-risk-daily-loss-input" type="number" min={1} max={10} value={riskSettings?.daily_loss_limit_pct ?? 3} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), daily_loss_limit_pct: event.target.value }))} data-testid="user-risk-daily-loss-input" aria-label="Max Daily Loss (%)" aria-describedby="user-risk-daily-loss-helper user-risk-daily-loss-error" />
              <p className="form-helper-text" id="user-risk-daily-loss-helper" data-testid="user-risk-daily-loss-helper">Günlük maksimum kayıp limiti.</p>
              {riskFormErrors.daily_loss_limit_pct && <p className="form-error-text" id="user-risk-daily-loss-error" data-testid="user-risk-daily-loss-error">{riskFormErrors.daily_loss_limit_pct}</p>}
            </div>
            <label className="flex items-center gap-2 text-sm" data-testid="user-risk-compounding-toggle-row">
              <input type="checkbox" checked={Boolean(riskSettings?.compounding_enabled)} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), compounding_enabled: event.target.checked }))} data-testid="user-risk-compounding-toggle" />
              Kâr/Zararı Ana Paraya Ekle
            </label>
            <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" onClick={saveRiskSettings} data-testid="user-risk-save-button">Risk Ayarlarını Kaydet</Button>
          </div>

          <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-risk-live-preview-card">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-risk-live-preview-title">Canlı İşlem Önizlemesi</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-risk-live-preview-grid">
              <p data-testid="user-risk-preview-market-type">Market Type: {riskPreview?.market_type ?? "-"}</p>
              <p data-testid="user-risk-preview-current-capital">Güncel ana para: {riskPreview?.current_capital ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-position-size">Position size: {riskPreview?.position_size ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-risk-amount">Risk amount: {riskPreview?.risk_amount ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-allocation-pct">İşleme ayrılan oran: %{riskPreview?.allocation_pct ?? "-"}</p>
              <p data-testid="user-risk-preview-allocation-amount">İşleme girecek tutar: {riskPreview?.trade_allocation_amount ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-trade-risk-pct">İşlemde risk oranı: %{riskPreview?.trade_risk_pct ?? "-"}</p>
              <p data-testid="user-risk-preview-max-loss">Maksimum bu işlem kaybı: {riskPreview?.max_trade_loss_amount ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-capital-impact">Toplam ana paraya etkisi: %{riskPreview?.total_capital_impact_pct ?? "-"}</p>
              <p data-testid="user-risk-preview-next-base">Sonraki işlem baz hesabı: {riskPreview?.next_trade_base_capital ?? "-"}</p>
              <p data-testid="user-risk-preview-compounding">Compounding: {String(riskPreview?.compounding_enabled ?? false)}</p>

              {selectedVenue.market_type === "futures" && (
                <>
                  <p data-testid="user-risk-preview-futures-leverage">Leverage: x{riskPreview?.leverage ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-margin-mode">Margin mode: {riskPreview?.margin_mode ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-position-side">Position side: {riskPreview?.position_side ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-risk-per-trade">Risk % Per Trade: %{futuresContext.risk_per_trade_pct}</p>
                  <p data-testid="user-risk-preview-futures-max-daily-trades">Max Daily Trades: {futuresContext.max_daily_trades}</p>
                  <p data-testid="user-risk-preview-futures-atr-stop-multiplier">ATR Stop Multiplier: {futuresContext.atr_stop_multiplier}</p>
                  <p data-testid="user-risk-preview-futures-margin-usage">Margin usage: %{riskPreview?.margin_usage_pct ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-liquidation-buffer">Estimated liquidation buffer: %{riskPreview?.estimated_liquidation_buffer_pct ?? "-"}</p>
                </>
              )}
            </div>
            <div className="mt-2 space-y-1" data-testid="user-risk-preview-warnings-list">
              {(riskPreview?.warnings || []).map((warning) => (
                <p key={warning} className="text-xs text-yellow-300" data-testid={`user-risk-preview-warning-${warning}`}>High risk configuration: {warning}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "test" && (
        <div className="space-y-4" data-testid="user-test-validation-tab-content">

      <div className="grid gap-2 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="user-test-venue-selection-grid">
        <div className="form-group" data-testid="user-test-venue-exchange-group">
          <label className="form-label" htmlFor="user-test-venue-exchange-select" data-testid="user-test-venue-exchange-label">Exchange</label>
          <select id="user-test-venue-exchange-select" value={selectedVenue.exchange} onChange={(event) => onExchangeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-venue-exchange-select" aria-label="Exchange">
            {exchangeOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="form-group" data-testid="user-test-venue-market-type-group">
          <label className="form-label" htmlFor="user-test-venue-market-type-select" data-testid="user-test-venue-market-type-label">Market Type</label>
          <select id="user-test-venue-market-type-select" value={selectedVenue.market_type} onChange={(event) => onMarketTypeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-venue-market-type-select" aria-label="Market Type">
            {marketTypeOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="form-group" data-testid="user-test-venue-environment-group">
          <label className="form-label" htmlFor="user-test-venue-environment-select" data-testid="user-test-venue-environment-label">Environment</label>
          <select id="user-test-venue-environment-select" value={selectedVenue.environment} onChange={(event) => onEnvironmentChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-venue-environment-select" aria-label="Environment">
            {environmentOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <p className="md:col-span-3 text-xs text-slate-400" data-testid="user-test-selected-venue-summary">Seçili venue: {selectedVenue.exchange} / {selectedVenue.market_type} / {selectedVenue.environment}</p>
        {venueOptions.length === 0 && (
          <p className="md:col-span-3 text-xs text-yellow-300" data-testid="user-test-no-assignment-warning">Henüz venue assignment yok. Admin panelden kullanıcıya venue atanmalı.</p>
        )}
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-test-symbol-selector-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-test-symbol-selector-title">Trade Symbol Selection</p>
        <p className="mt-1 text-xs text-slate-400" data-testid="user-test-symbol-selector-description">
          Venue bazlı USDT pair listesi otomatik yüklenir. Seçim localStorage ile korunur.
        </p>
        <div className="mt-3" data-testid="user-test-symbol-selector-wrapper">
          <SymbolSelectorPanel
            testIdPrefix="user-exchange-symbol-selector"
            source={symbolSelectorSource}
            onSourceChange={(next) => setSymbolSelectorSource(next === "stock" ? "crypto" : next)}
            mode={symbolSelectorMode}
            onModeChange={setSymbolSelectorMode}
            exchange={selectedVenue.exchange}
            marketType={selectedVenue.market_type}
            quoteAssetFilter="USDT"
            selectedSymbols={symbolSelectorSelection}
            onSelectedSymbolsChange={setSymbolSelectorSelection}
            multi
          />
        </div>
        <p className="mt-2 text-sm text-emerald-300" data-testid="user-test-selected-symbol-summary">
          Selected Symbols: {symbolSelectorSelection.length} · Active Symbol: {selectedSymbol || "-"}
        </p>
      </div>

      {selectedVenue.market_type === "futures" && (
        <div className="grid gap-2 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="user-test-futures-context-grid">
          <div className="form-group" data-testid="user-test-futures-leverage-group">
            <label className="form-label" htmlFor="user-test-futures-leverage-input" data-testid="user-test-futures-leverage-label">Leverage</label>
            <Input id="user-test-futures-leverage-input" type="number" min={1} max={20} value={futuresContext.leverage} onChange={(event) => setFuturesContext((prev) => ({ ...prev, leverage: Number(event.target.value) || 1 }))} data-testid="user-test-futures-leverage-input" aria-label="Leverage" />
          </div>
          <div className="form-group" data-testid="user-test-futures-margin-mode-group">
            <label className="form-label" htmlFor="user-test-futures-margin-mode-select" data-testid="user-test-futures-margin-mode-label">Margin Mode</label>
            <select id="user-test-futures-margin-mode-select" value={futuresContext.margin_mode} onChange={(event) => setFuturesContext((prev) => ({ ...prev, margin_mode: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-futures-margin-mode-select" aria-label="Margin Mode">
              <option value="cross">cross</option>
              <option value="isolated">isolated</option>
            </select>
          </div>
          <div className="form-group" data-testid="user-test-futures-position-side-group">
            <label className="form-label" htmlFor="user-test-futures-position-side-select" data-testid="user-test-futures-position-side-label">Position Mode</label>
            <select id="user-test-futures-position-side-select" value={futuresContext.position_side} onChange={(event) => setFuturesContext((prev) => ({ ...prev, position_side: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-futures-position-side-select" aria-label="Position Mode">
              <option value="BOTH">BOTH</option>
              <option value="LONG">LONG</option>
              <option value="SHORT">SHORT</option>
            </select>
          </div>
        </div>
      )}

      {selectedVenue.market_type === "spot" && (
        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-test-spot-context-card">
          <p className="text-sm text-emerald-300" data-testid="user-test-spot-quote-qty-text">Spot test order quoteQty=10 USDT semantiği ile gönderilir.</p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-10" data-testid="user-exchange-settings-metrics-grid">
        <MetricCard label="Exchange" value={settings?.exchange || "-"} tone="orange" testId="user-exchange-metric-exchange" />
        <MetricCard label="Mode" value={settings?.mode || "-"} tone="orange" testId="user-exchange-metric-mode" />
        <MetricCard label="Permission" value={permission?.overall_status || "-"} tone={permission?.overall_status === "pass" ? "orange" : "red"} testId="user-exchange-metric-permission" />
        <MetricCard label="Live Activation" value={permission?.live_activation || "blocked"} tone={permission?.live_activation === "ready" ? "orange" : "red"} testId="user-exchange-metric-live-activation" />
        <MetricCard label="Execution Quality" value={latestQuality?.execution_quality_score ?? "-"} tone="orange" testId="user-exchange-metric-quality" />
        <MetricCard label="Profiles Online" value={String(connectionHealthOverview.online)} tone="orange" testId="user-exchange-metric-profiles-online" />
        <MetricCard label="Profiles Degraded" value={String(connectionHealthOverview.degraded)} tone={connectionHealthOverview.degraded > 0 ? "red" : "blue"} testId="user-exchange-metric-profiles-degraded" />
        <MetricCard label="Profiles Offline" value={String(connectionHealthOverview.offline)} tone={connectionHealthOverview.offline > 0 ? "red" : "blue"} testId="user-exchange-metric-profiles-offline" />
        <MetricCard label="Action Required" value={String(actionRequiredProfiles.length)} tone={actionRequiredProfiles.length > 0 ? "red" : "orange"} testId="user-exchange-metric-action-required" />
        <MetricCard label="24h Validation Success" value={formatRate(selectedConnectionProfile?.validation_success_rate_24h)} tone="blue" testId="user-exchange-metric-validation-success-rate" />
      </div>

      <div className="grid gap-3 sm:grid-cols-6" data-testid="user-exchange-action-state-grid">
        <MetricCard label="Readiness" value={readiness?.readiness_status || "-"} tone={readinessTone} testId="user-exchange-readiness-status" />
        <MetricCard label="Validation Result" value={validationState} tone={validationState === "valid_trade_enabled" ? "orange" : validationState === "not_run" ? "blue" : "red"} testId="user-exchange-validation-state" />
        <MetricCard label="Effective Trade State" value={effectiveTradeState.state} tone={effectiveTradeState.tone} testId="user-exchange-effective-trade-state" />
        <MetricCard label="Connection Health" value={selectedConnectionProfile?.connection_health || "unknown"} tone={selectedConnectionProfile?.connection_health === "online" ? "orange" : selectedConnectionProfile?.connection_health === "unknown" ? "blue" : "red"} testId="user-exchange-selected-connection-health" />
        <MetricCard label="Last Validation" value={readiness?.validation_timestamp || "-"} tone="blue" testId="user-exchange-last-validation-at" />
        <MetricCard label="Last Error" value={readiness?.last_error_reason || "-"} tone="red" testId="user-exchange-last-error-reason" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-effective-state-reason-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-exchange-effective-state-reason-title">Execution State Resolver</p>
        <p className="mt-2 text-sm text-slate-200" data-testid="user-exchange-effective-state-reason-text">{effectiveTradeState.reason}</p>
      </div>

      <div className="grid gap-3 lg:grid-cols-2" data-testid="user-exchange-action-required-grid">
        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-action-required-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-exchange-action-required-title">Action Required</p>
          {actionRequiredProfiles.length === 0 ? (
            <p className="mt-2 text-sm text-emerald-300" data-testid="user-exchange-action-required-empty">Tüm connection profilleri trade-ready.</p>
          ) : (
            <div className="mt-2 space-y-2" data-testid="user-exchange-action-required-list">
              {actionRequiredProfiles.map((profile) => (
                <div key={profile.id} className="rounded border border-slate-700 bg-slate-950 p-2" data-testid={`user-exchange-action-required-item-${profile.id}`}>
                  <p className="text-sm font-semibold text-slate-100" data-testid={`user-exchange-action-required-item-label-${profile.id}`}>{profile.account_label} · {profile.connection_health}</p>
                  <p className="text-xs text-slate-400" data-testid={`user-exchange-action-required-item-reason-${profile.id}`}>{profile.action_required_message || profile.connection_health_reason || "-"}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-health-timeline-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-exchange-health-timeline-title">Selected Profile Health Timeline</p>
          <p className="mt-1 text-xs text-slate-400" data-testid="user-exchange-health-timeline-summary">
            success_24h={selectedConnectionProfile?.validation_success_24h ?? 0} · fail_24h={selectedConnectionProfile?.validation_fail_24h ?? 0} · last_transition={formatConnectionTime(selectedConnectionProfile?.health_last_transition_at)}
          </p>
          {selectedHealthTimeline.length === 0 ? (
            <p className="mt-2 text-sm text-slate-400" data-testid="user-exchange-health-timeline-empty">Henüz health transition geçmişi yok.</p>
          ) : (
            <div className="mt-2 space-y-1" data-testid="user-exchange-health-timeline-list">
              {selectedHealthTimeline.map((item, index) => (
                <p key={`${item.at || "no-at"}-${index}`} className="text-xs text-slate-300" data-testid={`user-exchange-health-timeline-item-${index}`}>
                  {formatConnectionTime(item.at)} · {item.health || "-"} · {item.reason || "none"} · source={item.source || "-"}
                </p>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-venue-access-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-venue-access-title">Venue Access Check</p>
        <p className="mt-2 text-sm text-slate-300" data-testid="user-venue-access-allowed">allowed={String(venueAccess?.allowed ?? false)}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-venue-access-state">venue_state={venueAccess?.venue_state || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-venue-access-capability">capability_match={String(venueAccess?.capability_match ?? false)}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-venue-access-reasons">reason_codes={(venueAccess?.reason_codes || []).join(",") || "-"}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3" data-testid="user-exchange-validate-grid">
        <MetricCard label="Validate is_valid" value={String(validateResult?.is_valid ?? false)} tone={validateResult?.is_valid ? "orange" : "red"} testId="user-exchange-validate-is-valid" />
        <MetricCard label="can_trade" value={String(validateResult?.can_trade ?? false)} tone={validateResult?.can_trade ? "orange" : "red"} testId="user-exchange-validate-can-trade" />
        <MetricCard label="mid_price" value={ticker?.mid_price ?? "-"} tone="blue" testId="user-exchange-mid-price" />
      </div>
      <p className="text-xs text-slate-400" data-testid="user-exchange-mid-price-symbol-label">ticker_symbol={selectedSymbol || "-"}</p>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-readiness-checklist-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-readiness-checklist-title">Readiness Checklist</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-readiness-checklist-grid">
          <p data-testid="user-readiness-has-api-key">API key mevcut: {String(readiness?.has_api_key ?? false)}</p>
          <p data-testid="user-readiness-has-api-secret">Secret mevcut: {String(readiness?.has_api_secret ?? false)}</p>
          <p data-testid="user-readiness-validation-success">Validation başarılı: {String(readiness?.validation_success ?? false)}</p>
          <p data-testid="user-readiness-can-trade">can_trade=true: {String(readiness?.can_trade ?? false)}</p>
          <p data-testid="user-readiness-live-env">live environment: {String(!(readiness?.is_live_environment ?? false))}</p>
          <p data-testid="user-readiness-validation-stale">snapshot stale: {String(readiness?.is_validation_stale ?? true)}</p>
        </div>
      </div>

      {readiness?.readiness_status === "awaiting_valid_key" && (
        <div className="border border-blue-700 bg-blue-950/20 p-4 text-sm text-blue-200" data-testid="user-readiness-awaiting-valid-key-banner">
          awaiting valid key — Binance live API key ve secret doğrulanmadan gerçek test-order çalıştırılamaz.
        </div>
      )}

      {(testOrderBanner || readiness?.is_validation_stale) && (
        <div className="border border-red-700 bg-red-950/20 p-4 text-sm text-red-200" data-testid="user-readiness-failure-banner">
          {testOrderBanner || "Validation snapshot stale. Lütfen Revalidate yapın."}
        </div>
      )}

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-quality-regime-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-exchange-quality-regime-title">Quality Normalization</p>
        <p className="mt-2 text-sm text-slate-300" data-testid="user-exchange-quality-symbol">symbol={latestQuality?.symbol || selectedSymbol || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-exchange-quality-strategy">strategy={latestQuality?.strategy_type || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-exchange-quality-volatility-regime">volatility_regime={latestQuality?.volatility_regime || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-exchange-quality-volatility-pct">volatility_pct={latestQuality?.volatility_pct ?? "-"}</p>
      </div>

      <form className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" onSubmit={saveSettings} data-testid="user-exchange-settings-form">
        <div className="form-group" data-testid="user-exchange-settings-exchange-group">
          <label className="form-label" htmlFor="user-exchange-settings-exchange-select" data-testid="user-exchange-settings-exchange-label">Exchange</label>
          <select id="user-exchange-settings-exchange-select" value={selectedVenue.exchange} onChange={(event) => onExchangeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-exchange-settings-exchange-select" aria-label="Exchange">
            {exchangeOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <p className="form-helper-text" data-testid="user-exchange-settings-exchange-helper">Ana bağlantı için kullanılacak borsa.</p>
        </div>
        <div className="form-group" data-testid="user-exchange-settings-market-type-group">
          <label className="form-label" htmlFor="user-exchange-settings-market-type-select" data-testid="user-exchange-settings-market-type-label">Market Type</label>
          <select id="user-exchange-settings-market-type-select" value={selectedVenue.market_type} onChange={(event) => onMarketTypeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-exchange-settings-market-type-select" aria-label="Market Type">
            {marketTypeOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <p className="form-helper-text" data-testid="user-exchange-settings-market-type-helper">Kaydettiğiniz key bu market paneline (Diagnostics) otomatik akar.</p>
        </div>
        <div className="form-group" data-testid="user-exchange-settings-environment-group">
          <label className="form-label" htmlFor="user-exchange-settings-environment-select" data-testid="user-exchange-settings-environment-label">Environment</label>
          <select id="user-exchange-settings-environment-select" value={selectedVenue.environment} onChange={(event) => onEnvironmentChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-exchange-settings-environment-select" aria-label="Environment">
            {environmentOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <p className="form-helper-text" data-testid="user-exchange-settings-environment-helper">Canlı hedef ortamı.</p>
        </div>
        <div className="form-group" data-testid="user-exchange-settings-api-key-group">
          <label className="form-label" htmlFor="user-exchange-settings-api-key-input" data-testid="user-exchange-settings-api-key-label">API Key</label>
          <Input id="user-exchange-settings-api-key-input" value={form.api_key} onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))} data-testid="user-exchange-settings-api-key-input" aria-label="API Key" aria-describedby="user-exchange-settings-api-key-helper" required />
          <p className="form-helper-text" id="user-exchange-settings-api-key-helper" data-testid="user-exchange-settings-api-key-helper">Borsa panelinden alınan API key.</p>
        </div>
        <div className="form-group" data-testid="user-exchange-settings-api-secret-group">
          <label className="form-label" htmlFor="user-exchange-settings-api-secret-input" data-testid="user-exchange-settings-api-secret-label">API Secret</label>
          <Input id="user-exchange-settings-api-secret-input" value={form.api_secret} onChange={(event) => setForm((prev) => ({ ...prev, api_secret: event.target.value }))} data-testid="user-exchange-settings-api-secret-input" aria-label="API Secret" aria-describedby="user-exchange-settings-api-secret-helper" required />
          <p className="form-helper-text" id="user-exchange-settings-api-secret-helper" data-testid="user-exchange-settings-api-secret-helper">API key ile eşleşen secret değeri.</p>
        </div>
        <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" data-testid="user-exchange-settings-save-button" disabled={isSaving}>
          {isSaving ? "Kaydediliyor..." : "API Bilgilerini Kaydet"}
        </Button>
      </form>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-actions-panel">
        <div className="flex flex-wrap gap-3" data-testid="user-exchange-actions-buttons">
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={runPermission} data-testid="user-exchange-check-permission-button" disabled={isValidating}>
            {isValidating ? "Validating..." : "Revalidate"}
          </Button>
          <Button
            className="bg-black text-orange-400 hover:bg-zinc-900"
            onClick={runFirstTestOrder}
            data-testid="user-exchange-first-test-order-button"
            disabled={isTesting || readiness?.readiness_status !== "ready_for_test_order" || !testOrderEligible}
          >
            {isTesting ? "Gönderiliyor..." : "İlk Kontrollü Test Emri"}
          </Button>
        </div>

        {!testOrderEligible && (
          <p className="mt-2 text-xs text-yellow-300" data-testid="user-test-order-venue-constraint-text">
            Test order şu an yalnızca binance/live kombinasyonu için destekleniyor.
          </p>
        )}

        <div className="mt-4 space-y-1" data-testid="user-exchange-permission-controls-list">
          {(permission?.controls || []).map((item) => (
            <p key={item.key} className="text-xs font-mono text-slate-300" data-testid={`user-exchange-permission-control-${item.key}`}>
              {item.key}: {item.status} ({item.reason})
            </p>
          ))}
          <p className="pt-2 text-xs font-mono text-slate-300" data-testid="user-exchange-validate-permissions-line">
            permissions: {(validateResult?.permissions || []).join(",") || "-"}
          </p>
          <p className="text-xs font-mono text-slate-300" data-testid="user-exchange-validate-reason-codes-line">
            reason_codes: {(validateResult?.reason_codes || []).join(",") || "-"}
          </p>
          <p className="text-xs font-mono text-slate-300" data-testid="user-exchange-validate-hint-line">
            hint: {validateResult?.hint || "-"}
          </p>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-test-order-result-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-test-order-result-title">Test Order Result</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-test-order-result-grid">
          <p data-testid="user-test-order-exchange">exchange: {testOrderResult?.exchange || selectedVenue.exchange}</p>
          <p data-testid="user-test-order-market-type">market_type: {testOrderResult?.market_type || selectedVenue.market_type}</p>
          <p data-testid="user-test-order-environment">environment: {testOrderResult?.environment || selectedVenue.environment}</p>
          <p data-testid="user-test-order-symbol">symbol: {testOrderResult?.symbol || selectedSymbol || "-"}</p>
          <p data-testid="user-test-order-status">order status: {testOrderResult?.status || "awaiting_valid_key"}</p>
          <p data-testid="user-test-order-final-status">final status: {testOrderResult?.final_status || "-"}</p>
          <p data-testid="user-test-order-exchange-order-id">exchange order id: {testOrderResult?.exchange_order_id || "-"}</p>
          <p data-testid="user-test-order-client-order-id">client order id: {testOrderResult?.client_order_id || "-"}</p>
          <p data-testid="user-test-order-average-fill-price">average fill price: {testOrderResult?.price_avg ?? "-"}</p>
          <p data-testid="user-test-order-executed-qty">executed quantity: {testOrderResult?.executed_qty ?? "-"}</p>
          <p data-testid="user-test-order-slippage-pct">slippage pct: {testOrderResult?.slippage_pct ?? "-"}</p>
          <p data-testid="user-test-order-execution-time-ms">execution time ms: {testOrderResult?.execution_time_ms ?? "-"}</p>
          <p data-testid="user-test-order-volatility-regime">volatility regime: {testOrderResult?.volatility_regime || "-"}</p>
          <p data-testid="user-test-order-strategy-type">strategy type: {testOrderResult?.strategy_type || "-"}</p>
          <p data-testid="user-test-order-requested-leverage">requested leverage: {testOrderResult?.requested_leverage ?? "-"}</p>
          <p data-testid="user-test-order-recommended-leverage">recommended leverage: {testOrderResult?.recommended_leverage ?? "-"}</p>
          <p data-testid="user-test-order-applied-leverage">applied leverage: {testOrderResult?.applied_leverage ?? "-"}</p>
          <p className="sm:col-span-2" data-testid="user-test-order-leverage-clamp-reasons">leverage clamp reasons: {(testOrderResult?.leverage_clamp_reasons || []).join(",") || "none"}</p>
          <p data-testid="user-test-order-failure-code">failure code: {testOrderResult?.failure_code || "-"}</p>
          <p data-testid="user-test-order-submitted-at">submitted_at: {testOrderResult?.submitted_at || "-"}</p>
          <p data-testid="user-test-order-ack-at">ack_at: {testOrderResult?.ack_at || "-"}</p>
          <p data-testid="user-test-order-final-at">final_at: {testOrderResult?.final_at || "-"}</p>
          <p className="sm:col-span-2" data-testid="user-test-order-validation-timestamp">validation timestamp: {readiness?.validation_timestamp || "-"}</p>
          <p className="sm:col-span-2" data-testid="user-test-order-validation-snapshot-id">validation snapshot id: {readiness?.validation_snapshot_id || "-"}</p>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-lifecycle-evidence-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-lifecycle-evidence-title">Lifecycle Evidence Timeline</p>
        <div className="mt-3 space-y-2" data-testid="user-lifecycle-evidence-list">
          {(lifecycleEvidence?.timeline || []).map((item, index) => (
            <div key={`${item.event_name}-${index}`} className="border border-slate-700 p-2 text-xs" data-testid={`user-lifecycle-evidence-item-${index}`}>
              {item.event_name} — {item.event_timestamp}
            </div>
          ))}
          {(!lifecycleEvidence || (lifecycleEvidence.timeline || []).length === 0) && (
            <p className="text-xs text-slate-400" data-testid="user-lifecycle-evidence-empty">Henüz lifecycle evidence yok.</p>
          )}
        </div>
      </div>
        </div>
      )}
    </section>
  );
};