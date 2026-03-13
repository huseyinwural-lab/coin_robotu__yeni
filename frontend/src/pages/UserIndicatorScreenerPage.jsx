import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";

const createSignalRuleFeatureEnabled = false;
const FILTER_SCHEMA_VERSION = 2;

const defaultFilters = {
  exchange: "binance",
  market_type: "spot",
  timeframe: "15m",
  query_expression: "rsi14 < 30",
  limit: 50,

  symbol_universe_mode: "all_tradable",
  symbol_whitelist: "",
  symbol_search: "",
  saved_query_id: "",
  universe_top_n: 200,

  sort_by: "symbol",
  sort_direction: "asc",

  min_24h_volume: 100000,
  max_24h_volume: "",
  quote_asset_filter: "ALL",
  only_tradable_pairs: true,
  only_margin_eligible: false,
  only_futures_eligible: false,
  spread_threshold_pct: "",

  market_participation: "spot_only",
  pair_mode: "all",
  exclude_leveraged_tokens: true,
  exclude_stablecoin_stablecoin_pairs: true,

  min_signal_score: "",
  min_confidence: "",
  min_rr_estimate: "",
  only_executable: false,
  only_fresh_data: false,
  last_candle_freshness_minutes: 180,
};

const filterKeyLabels = {
  market_participation: "Market",
  symbol_universe_mode: "Universe",
  symbol_search: "Search",
  min_24h_volume: "Min Vol",
  max_24h_volume: "Max Vol",
  quote_asset_filter: "Quote",
  pair_mode: "Pair",
  fresh: "Fresh",
  exec: "Executable",
  min_signal_score: "Min Score",
};

const resultStateMessages = {
  loading: "Tarama çalışıyor. Piyasa verileri toplanıyor...",
  success: "Tarama tamamlandı.",
  no_match: "Koşulları sağlayan kayıt bulunamadı (no match).",
  empty_universe: "Seçilen evrende değerlendirilecek sembol kalmadı (empty universe).",
  backend_unavailable: "Backend şu anda ulaşılamıyor.",
  rate_limit_throttled: "Rate-limit nedeniyle tarama kısıtlandı. Kısa süre sonra tekrar deneyin.",
  permission_blocked: "Bu tarama için yetkiniz yok veya oturum süreniz doldu.",
  invalid_filter_combination: "Filtre kombinasyonu geçersiz.",
  invalid_query: "Query ifadesi geçersiz.",
};

const buttonClass = {
  primary: "bg-emerald-300 text-slate-950 hover:bg-emerald-200 border border-emerald-300 disabled:bg-slate-300 disabled:text-slate-500",
  secondary: "bg-slate-100 text-slate-900 hover:bg-slate-50 border border-slate-300 disabled:bg-slate-200 disabled:text-slate-500",
  danger: "bg-rose-500 text-white hover:bg-rose-400 border border-rose-500 disabled:bg-slate-300 disabled:text-slate-500",
  warning: "bg-amber-400 text-slate-950 hover:bg-amber-300 border border-amber-400 disabled:bg-slate-300 disabled:text-slate-500",
};

const numberCell = (value, digits = 4) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
};

const toCsv = (rows) => {
  const headers = [
    "#",
    "exchange",
    "market_type",
    "symbol",
    "timeframe",
    "close",
    "rsi14",
    "rsi7",
    "ema20",
    "ema50",
    "volume_24h",
    "signal_score",
    "confidence",
    "rr_estimate",
    "executable",
    "stale_data",
    "matched_rules",
    "updated_at",
  ];

  const body = rows.map((row) => [
    row.index,
    row.exchange,
    row.market_type,
    row.symbol,
    row.timeframe,
    row.close,
    row.rsi14,
    row.rsi7,
    row.ema20,
    row.ema50,
    row.volume_24h,
    row.signal_score,
    row.confidence,
    row.rr_estimate,
    row.executable,
    row.stale_data,
    (row.matched_rules || []).join(" | "),
    row.updated_at || "",
  ]);

  return [headers.join(","), ...body.map((line) => line.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))].join("\n");
};

const parseOptionalNumber = (value) => {
  if (value === "" || value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export const UserIndicatorScreenerPage = () => {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(defaultFilters);
  const [saveQueryName, setSaveQueryName] = useState("");
  const [presets, setPresets] = useState([]);
  const [savedQueries, setSavedQueries] = useState([]);
  const [watchlistRows, setWatchlistRows] = useState([]);
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState(null);
  const [isBootLoading, setIsBootLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [runError, setRunError] = useState("");
  const [densityMode, setDensityMode] = useState("compact");
  const [showFiltersExpanded, setShowFiltersExpanded] = useState(true);
  const [selectedRowKey, setSelectedRowKey] = useState("");

  const watchlistSymbolSet = useMemo(() => new Set((watchlistRows || []).map((item) => `${item.symbol}:${item.market_type}`)), [watchlistRows]);

  const loadBootstrap = useCallback(async () => {
    setIsBootLoading(true);
    setLoadError("");
    try {
      const [presetRes, savedRes, watchlistRes] = await Promise.all([
        apiClient.get("/user/indicator-screener/presets"),
        apiClient.get("/user/indicator-screener/saved-queries"),
        apiClient.get("/user/indicator-screener/watchlist"),
      ]);
      setPresets(presetRes.data || []);
      setSavedQueries(savedRes.data || []);
      setWatchlistRows(watchlistRes.data || []);
    } catch (error) {
      const message = error?.response?.data?.detail || "Indicator screener kaynakları yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsBootLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const clearSingleFilter = (key) => {
    if (!(key in defaultFilters)) {
      if (key === "fresh") {
        setFilters((prev) => ({ ...prev, only_fresh_data: false }));
        return;
      }
      if (key === "exec") {
        setFilters((prev) => ({ ...prev, only_executable: false }));
        return;
      }
      return;
    }
    setFilters((prev) => ({ ...prev, [key]: defaultFilters[key] }));
  };

  const buildFilterPayload = () => ({
    symbol_universe_mode: filters.symbol_universe_mode,
    symbol_whitelist: (filters.symbol_whitelist || "")
      .split(",")
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean),
    symbol_search: (filters.symbol_search || "").trim().toUpperCase(),
    saved_query_id: filters.saved_query_id || null,
    universe_top_n: Number(filters.universe_top_n || 200),

    sort_by: filters.sort_by,
    sort_direction: filters.sort_direction,

    min_24h_volume: parseOptionalNumber(filters.min_24h_volume),
    max_24h_volume: parseOptionalNumber(filters.max_24h_volume),
    quote_asset_filter: filters.quote_asset_filter,
    only_tradable_pairs: Boolean(filters.only_tradable_pairs),
    only_margin_eligible: Boolean(filters.only_margin_eligible),
    only_futures_eligible: Boolean(filters.only_futures_eligible),
    spread_threshold_pct: parseOptionalNumber(filters.spread_threshold_pct),

    market_participation: filters.market_participation,
    pair_mode: filters.pair_mode,
    exclude_leveraged_tokens: Boolean(filters.exclude_leveraged_tokens),
    exclude_stablecoin_stablecoin_pairs: Boolean(filters.exclude_stablecoin_stablecoin_pairs),

    min_signal_score: parseOptionalNumber(filters.min_signal_score),
    min_confidence: parseOptionalNumber(filters.min_confidence),
    min_rr_estimate: parseOptionalNumber(filters.min_rr_estimate),
    only_executable: Boolean(filters.only_executable),
    only_fresh_data: Boolean(filters.only_fresh_data),
    last_candle_freshness_minutes: Number(filters.last_candle_freshness_minutes || 180),
  });

  const validateFiltersBeforeSubmit = () => {
    const minVol = parseOptionalNumber(filters.min_24h_volume);
    const maxVol = parseOptionalNumber(filters.max_24h_volume);
    if (minVol !== null && maxVol !== null && minVol > maxVol) {
      return "min 24h volume, max 24h volume değerinden büyük olamaz.";
    }

    if (filters.symbol_universe_mode === "top_by_volume" && (filters.symbol_whitelist || "").trim()) {
      return "top by volume seçiliyken whitelist aynı anda kullanılamaz.";
    }

    if (filters.symbol_universe_mode === "whitelist_only" && !(filters.symbol_whitelist || "").trim()) {
      return "whitelist only modunda en az bir sembol girilmeli.";
    }

    if (filters.only_fresh_data && Number(filters.last_candle_freshness_minutes || 0) <= 0) {
      return "only fresh data açıkken freshness tolerance 0'dan büyük olmalı.";
    }

    if (filters.market_participation === "futures_only" && filters.symbol_universe_mode === "saved_universe") {
      const selected = savedQueries.find((item) => item.id === filters.saved_query_id);
      if (selected?.market_type === "spot") {
        return "Futures only ile spot tabanlı saved universe aynı anda kullanılamaz.";
      }
    }

    return "";
  };

  const runQuery = async () => {
    const validationError = validateFiltersBeforeSubmit();
    if (validationError) {
      setRunError(validationError);
      toast.error(validationError);
      return;
    }

    setIsRunning(true);
    setRunError("");
    try {
      const payload = {
        exchange: filters.exchange,
        market_type: filters.market_type,
        timeframe: filters.timeframe,
        query_expression: filters.query_expression,
        limit: Number(filters.limit),
        symbol_universe: filters.symbol_universe_mode === "whitelist_only" ? (filters.symbol_whitelist || "") : "all",
        filter_payload: buildFilterPayload(),
      };
      const { data } = await apiClient.post("/user/indicator-screener/run", payload);
      setMeta(data || null);
      setRows(data?.rows || []);
      setSelectedRowKey("");

      if (!data?.query_valid) {
        setRunError(data?.query_error || "Geçersiz query");
        toast.error(data?.query_error || "Geçersiz query");
      } else if (data?.filter_error) {
        setRunError(data.filter_error);
        toast.error(data.filter_error);
      } else {
        toast.success(resultStateMessages[data?.result_state] || `Tarama tamamlandı. Eşleşme: ${data?.match_count || 0}`);
      }
    } catch (error) {
      const message = error?.response?.data?.detail || "Indicator query çalıştırılamadı";
      const statusCode = Number(error?.response?.status || 0);
      let mappedState = "backend_unavailable";
      if (statusCode === 401 || statusCode === 403) {
        mappedState = "permission_blocked";
      } else if (statusCode === 429 || String(message).toLowerCase().includes("rate")) {
        mappedState = "rate_limit_throttled";
      }
      setRows([]);
      setMeta((prev) => ({
        ...(prev || {}),
        result_state: mappedState,
        applied_filters: buildFilterPayload(),
        active_filter_chips: prev?.active_filter_chips || [],
      }));
      setRunError(message);
      toast.error(message);
    } finally {
      setIsRunning(false);
    }
  };

  const clearAllFilters = () => {
    setFilters(defaultFilters);
    setRows([]);
    setMeta(null);
    setRunError("");
    setSaveQueryName("");
  };

  const applyPreset = (preset) => {
    updateFilter("query_expression", preset.query_expression);
    toast.success(`Preset yüklendi: ${preset.title}`);
  };

  const saveCurrentQuery = async () => {
    try {
      const payload = {
        name: saveQueryName,
        exchange: filters.exchange,
        market_type: filters.market_type,
        timeframe: filters.timeframe,
        query_expression: filters.query_expression,
        symbol_universe: (filters.symbol_whitelist || "")
          .split(",")
          .map((item) => item.trim().toUpperCase())
          .filter(Boolean),
        filter_snapshot: buildFilterPayload(),
        schema_version: FILTER_SCHEMA_VERSION,
        result_limit: Number(filters.limit),
      };
      await apiClient.post("/user/indicator-screener/saved-queries", payload);
      toast.success("Sorgu + filtre durumu kaydedildi");
      setSaveQueryName("");
      await loadBootstrap();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Sorgu kaydedilemedi");
    }
  };

  const deleteSavedQuery = async (queryId) => {
    try {
      await apiClient.delete(`/user/indicator-screener/saved-queries/${queryId}`);
      toast.success("Kayıtlı sorgu silindi");
      await loadBootstrap();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Kayıtlı sorgu silinemedi");
    }
  };

  const applySavedQuery = (item) => {
    const snapshot = item.filter_snapshot || {};
    setFilters((prev) => ({
      ...prev,
      exchange: item.exchange,
      market_type: item.market_type,
      timeframe: item.timeframe,
      query_expression: item.query_expression,
      limit: item.result_limit,

      symbol_universe_mode: snapshot.symbol_universe_mode || ((item.symbol_universe || []).length ? "whitelist_only" : "all_tradable"),
      symbol_whitelist: (snapshot.symbol_whitelist || item.symbol_universe || []).join(","),
      symbol_search: snapshot.symbol_search || "",
      saved_query_id: item.id,
      universe_top_n: snapshot.universe_top_n ?? prev.universe_top_n,

      sort_by: snapshot.sort_by || prev.sort_by,
      sort_direction: snapshot.sort_direction || prev.sort_direction,

      min_24h_volume: snapshot.min_24h_volume ?? prev.min_24h_volume,
      max_24h_volume: snapshot.max_24h_volume ?? "",
      quote_asset_filter: snapshot.quote_asset_filter || prev.quote_asset_filter,
      only_tradable_pairs: snapshot.only_tradable_pairs ?? prev.only_tradable_pairs,
      only_margin_eligible: snapshot.only_margin_eligible ?? prev.only_margin_eligible,
      only_futures_eligible: snapshot.only_futures_eligible ?? prev.only_futures_eligible,
      spread_threshold_pct: snapshot.spread_threshold_pct ?? "",

      market_participation: snapshot.market_participation || prev.market_participation,
      pair_mode: snapshot.pair_mode || prev.pair_mode,
      exclude_leveraged_tokens: snapshot.exclude_leveraged_tokens ?? prev.exclude_leveraged_tokens,
      exclude_stablecoin_stablecoin_pairs:
        snapshot.exclude_stablecoin_stablecoin_pairs ?? prev.exclude_stablecoin_stablecoin_pairs,

      min_signal_score: snapshot.min_signal_score ?? "",
      min_confidence: snapshot.min_confidence ?? "",
      min_rr_estimate: snapshot.min_rr_estimate ?? "",
      only_executable: snapshot.only_executable ?? prev.only_executable,
      only_fresh_data: snapshot.only_fresh_data ?? prev.only_fresh_data,
      last_candle_freshness_minutes: snapshot.last_candle_freshness_minutes ?? prev.last_candle_freshness_minutes,
    }));
    toast.success(`Sorgu + filtre yüklendi: ${item.name}`);
  };

  const addToWatchlist = async (row) => {
    try {
      await apiClient.post("/user/indicator-screener/watchlist", {
        exchange: row.exchange,
        market_type: row.market_type,
        symbol: row.symbol,
        note: `indicator-screener:${filters.query_expression}`,
        context_snapshot: {
          query_expression: filters.query_expression,
          filter_payload: buildFilterPayload(),
          source_result: {
            symbol: row.symbol,
            market_type: row.market_type,
            timeframe: row.timeframe,
          },
        },
      });
      toast.success(`${row.symbol} watchlist'e eklendi`);
      await loadBootstrap();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Watchlist ekleme başarısız");
    }
  };

  const deleteWatchlist = async (watchId) => {
    try {
      await apiClient.delete(`/user/indicator-screener/watchlist/${watchId}`);
      toast.success("Watchlist kaydı silindi");
      await loadBootstrap();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Watchlist kaydı silinemedi");
    }
  };

  const exportCsv = () => {
    if (!rows.length) {
      toast.error("Export için sonuç bulunmuyor");
      return;
    }
    const csv = toCsv(rows);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `indicator_screener_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const openInExecute = (row) => {
    toast.success(`${row.symbol} (${row.market_type}) Execute ekranına aktarılıyor`);
    navigate(`/user/execute?symbol=${row.symbol}&marketType=${row.market_type}&side=BUY&quantity=0.001&timeInForce=GTC&source=indicator-screener`);
  };

  const createSignalRule = () => {
    toast.info("Create Signal Rule bu sürümde feature flag altında hazırlık modunda.");
  };

  const applySortFromTableHeader = (field) => {
    setFilters((prev) => {
      if (prev.sort_by === field) {
        return { ...prev, sort_direction: prev.sort_direction === "asc" ? "desc" : "asc" };
      }
      return { ...prev, sort_by: field, sort_direction: "asc" };
    });
  };

  const isMatchedField = (row, field) => (row.matched_fields || []).includes(field);

  const activeChips = useMemo(() => {
    if (meta?.active_filter_chips?.length) {
      return meta.active_filter_chips.map((item) => ({
        key: item.key,
        label: filterKeyLabels[item.key] || item.label || item.key,
        value: item.value,
      }));
    }
    return [];
  }, [meta]);

  const effectiveState = isRunning ? "loading" : (meta?.result_state || "success");
  const appliedFilterSummary = meta?.applied_filters || buildFilterPayload();
  const querySummaryText = (filters.query_expression || "").trim() || "(query yok - filter-only mode)";

  const stateCardMap = {
    loading: {
      title: "Tarama Çalışıyor",
      description: resultStateMessages.loading,
      tone: "border-sky-300 bg-sky-50 text-sky-900",
      ctaLabel: "",
      ctaAction: () => {},
    },
    no_match: {
      title: "Eşleşme Yok",
      description: "Query veya filtreleri koruyarak farklı timeframe/likidite ayarı deneyebilirsiniz.",
      tone: "border-emerald-300 bg-emerald-50 text-emerald-900",
      ctaLabel: "Filtreleri Gözden Geçir",
      ctaAction: () => setShowFiltersExpanded(true),
    },
    empty_universe: {
      title: "Universe Boş",
      description: "Seçtiğiniz universe + market + likidite kombinasyonunda değerlendirilecek sembol bulunamadı.",
      tone: "border-amber-300 bg-amber-50 text-amber-900",
      ctaLabel: "Universe'i Sıfırla",
      ctaAction: () => {
        setFilters((prev) => ({ ...prev, symbol_universe_mode: "all_tradable", symbol_whitelist: "", saved_query_id: "" }));
        setShowFiltersExpanded(true);
      },
    },
    invalid_filter_combination: {
      title: "Geçersiz Filtre Kombinasyonu",
      description: meta?.filter_error || "Filtreler arası çakışma tespit edildi.",
      tone: "border-amber-400 bg-amber-50 text-amber-900",
      ctaLabel: "Clear All Filters",
      ctaAction: clearAllFilters,
    },
    invalid_query: {
      title: "Query Geçersiz",
      description: runError || resultStateMessages.invalid_query,
      tone: "border-rose-300 bg-rose-50 text-rose-900",
      ctaLabel: "Query Temizle",
      ctaAction: () => setFilters((prev) => ({ ...prev, query_expression: "" })),
    },
    backend_unavailable: {
      title: "Backend Ulaşılamıyor",
      description: runError || resultStateMessages.backend_unavailable,
      tone: "border-rose-300 bg-rose-50 text-rose-900",
      ctaLabel: "Retry Scan",
      ctaAction: runQuery,
    },
    rate_limit_throttled: {
      title: "Rate-Limit Throttled",
      description: runError || resultStateMessages.rate_limit_throttled,
      tone: "border-orange-300 bg-orange-50 text-orange-900",
      ctaLabel: "Biraz Sonra Tekrar Dene",
      ctaAction: runQuery,
    },
    permission_blocked: {
      title: "Permission Blocked",
      description: runError || resultStateMessages.permission_blocked,
      tone: "border-rose-300 bg-rose-50 text-rose-900",
      ctaLabel: "Girişe Dön",
      ctaAction: () => navigate("/user/login"),
    },
    success: {
      title: "",
      description: "",
      tone: "",
      ctaLabel: "",
      ctaAction: () => {},
    },
  };

  const stateCard = stateCardMap[effectiveState] || stateCardMap.success;

  if (isBootLoading) {
    return <LoadingSkeleton rows={10} testId="user-indicator-screener-loading-skeleton" />;
  }

  if (loadError && !presets.length) {
    return (
      <section className="space-y-4" data-testid="user-indicator-screener-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="user-indicator-screener-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="user-indicator-screener-broken-title">Indicator Screener açılış verisi yüklenemedi</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="user-indicator-screener-broken-message">{loadError}</p>
          <Button className="mt-3" onClick={loadBootstrap} data-testid="user-indicator-screener-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="user-indicator-screener-page">
      <header className="rounded-lg border border-emerald-300 bg-gradient-to-r from-emerald-100 via-emerald-50 to-lime-100 p-4" data-testid="user-indicator-screener-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="user-indicator-screener-header-row">
          <div data-testid="user-indicator-screener-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight text-slate-900" data-testid="user-indicator-screener-title">Indicator Screener</h2>
            <p className="mt-2 text-sm text-slate-700" data-testid="user-indicator-screener-description">Filter-first tarama yüzeyi: likidite, universe, market participation ve execution uyumlu sonuçlar.</p>
            <p className="mt-1 text-xs text-slate-600" data-testid="user-indicator-screener-last-calculated">Son hesaplama: {meta?.calculation_timestamp ? new Date(meta.calculation_timestamp).toLocaleString() : "-"}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="user-indicator-screener-header-actions">
            <Button className={buttonClass.secondary} onClick={() => setShowFiltersExpanded((prev) => !prev)} data-testid="user-indicator-screener-filter-collapse-toggle-button">
              {showFiltersExpanded ? "Filters: Expanded" : "Filters: Collapsed"}
            </Button>
            <Button className={buttonClass.secondary} onClick={() => setDensityMode((prev) => (prev === "compact" ? "wide" : "compact"))} data-testid="user-indicator-screener-density-toggle-button">
              Density: {densityMode === "compact" ? "Compact" : "Wide"}
            </Button>
            <Button className={buttonClass.secondary} onClick={exportCsv} data-testid="user-indicator-screener-export-csv-button">Export CSV</Button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_auto]" data-testid="user-indicator-screener-top-toolbar-grid">
          <label className="space-y-1" data-testid="user-indicator-screener-top-toolbar-query-field">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-700">Query Expression</span>
            <Textarea value={filters.query_expression} onChange={(event) => updateFilter("query_expression", event.target.value)} className="min-h-12 border-emerald-300 bg-white text-slate-900" data-testid="user-indicator-screener-query-textarea" />
            <p className="text-xs text-slate-600" data-testid="user-indicator-screener-top-toolbar-query-helper">Query opsiyoneldir. Boş bırakırsanız sadece filtre katmanıyla tarama çalışır.</p>
          </label>
          <div className="flex flex-wrap items-end gap-2" data-testid="user-indicator-screener-top-toolbar-actions">
            <Button className={buttonClass.primary} onClick={runQuery} disabled={isRunning} data-testid="user-indicator-screener-run-button">{isRunning ? "Running..." : "Run Scan"}</Button>
            <Button className={buttonClass.warning} onClick={clearAllFilters} data-testid="user-indicator-screener-clear-button">Reset</Button>
            <Button className={buttonClass.secondary} onClick={saveCurrentQuery} data-testid="user-indicator-screener-save-query-button">Save Query</Button>
          </div>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="user-indicator-screener-top-toolbar-secondary-strip">
          <div className="rounded-md border border-emerald-200 bg-white/70 p-2" data-testid="user-indicator-screener-query-summary-box">
            <p className="text-xs font-semibold text-slate-700" data-testid="user-indicator-screener-query-summary-title">Query Summary</p>
            <p className="text-xs text-slate-700" data-testid="user-indicator-screener-query-summary-value">{querySummaryText}</p>
          </div>
          <div className="rounded-md border border-emerald-200 bg-white/70 p-2" data-testid="user-indicator-screener-applied-filter-summary-box">
            <p className="text-xs font-semibold text-slate-700" data-testid="user-indicator-screener-applied-filter-summary-title">Applied Filter Snapshot</p>
            <p className="text-xs text-slate-700" data-testid="user-indicator-screener-applied-filter-summary-value">market={appliedFilterSummary.market_participation} · universe={appliedFilterSummary.symbol_universe_mode} · sort={appliedFilterSummary.sort_by}/{appliedFilterSummary.sort_direction}</p>
          </div>
        </div>
      </header>

      {loadError && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" data-testid="user-indicator-screener-warning-alert">Açılış yüklemesinde uyarı: {loadError}</div>
      )}

      <section className="rounded-lg border border-slate-300 bg-white p-4" data-testid="user-indicator-screener-filter-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="user-indicator-screener-filter-header-row">
          <div data-testid="user-indicator-screener-filter-header-left">
            <p className="text-xs uppercase tracking-widest text-slate-600" data-testid="user-indicator-screener-filter-title">Filter Panel</p>
            <p className="text-xs text-slate-500" data-testid="user-indicator-screener-filter-subtitle">Market, liquidity, universe, quality ve sorting katmanları ayrı ayrı kontrol edilir.</p>
          </div>
          <div className="flex flex-wrap gap-2" data-testid="user-indicator-screener-filter-header-actions">
            <Input value={saveQueryName} onChange={(event) => setSaveQueryName(event.target.value)} placeholder="Saved Query adı" className="h-9 w-52 border-slate-300 bg-white" data-testid="user-indicator-screener-save-query-name-input" />
            <Button className={buttonClass.secondary} onClick={saveCurrentQuery} data-testid="user-indicator-screener-save-query-header-button">Save Query + Filters</Button>
          </div>
        </div>

        {showFiltersExpanded && (
          <div className="mt-3 grid gap-3 xl:grid-cols-2" data-testid="user-indicator-screener-filter-groups-grid">
            <article className="rounded-md border border-slate-200 bg-slate-50 p-3" data-testid="user-indicator-screener-group-market-sorting">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-600" data-testid="user-indicator-screener-group-market-sorting-title">Market + Sorting</p>
              <p className="mt-1 text-xs text-slate-500" data-testid="user-indicator-screener-group-market-sorting-helper">Taramanın temel market bağlamını ve sonuç sıralamasını belirler.</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="user-indicator-screener-core-filter-grid">
                <label className="space-y-1" data-testid="user-indicator-screener-exchange-field">
                  <span className="text-xs text-slate-600">Exchange</span>
                  <select value={filters.exchange} onChange={(event) => updateFilter("exchange", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-exchange-select">
                    <option value="binance" data-testid="user-indicator-screener-exchange-option-binance">Binance</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-market-type-field">
                  <span className="text-xs text-slate-600">Market Type (default)</span>
                  <select value={filters.market_type} onChange={(event) => updateFilter("market_type", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-market-type-select">
                    <option value="spot" data-testid="user-indicator-screener-market-type-option-spot">Spot</option>
                    <option value="futures" data-testid="user-indicator-screener-market-type-option-futures">Futures</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-timeframe-field">
                  <span className="text-xs text-slate-600">Timeframe</span>
                  <select value={filters.timeframe} onChange={(event) => updateFilter("timeframe", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-timeframe-select">
                    <option value="5m" data-testid="user-indicator-screener-timeframe-option-5m">5m</option>
                    <option value="15m" data-testid="user-indicator-screener-timeframe-option-15m">15m</option>
                    <option value="1h" data-testid="user-indicator-screener-timeframe-option-1h">1h</option>
                    <option value="4h" data-testid="user-indicator-screener-timeframe-option-4h">4h</option>
                    <option value="1d" data-testid="user-indicator-screener-timeframe-option-1d">1d</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-limit-field">
                  <span className="text-xs text-slate-600">Limit</span>
                  <Input type="number" min={1} max={300} value={filters.limit} onChange={(event) => updateFilter("limit", Number(event.target.value || 1))} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-limit-input" />
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-sort-by-field">
                  <span className="text-xs text-slate-600">Sort By</span>
                  <select value={filters.sort_by} onChange={(event) => updateFilter("sort_by", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-sort-by-select">
                    <option value="symbol" data-testid="user-indicator-screener-sort-by-option-symbol">symbol</option>
                    <option value="volume_24h" data-testid="user-indicator-screener-sort-by-option-volume24h">volume_24h</option>
                    <option value="close" data-testid="user-indicator-screener-sort-by-option-close">close</option>
                    <option value="rsi14" data-testid="user-indicator-screener-sort-by-option-rsi14">rsi14</option>
                    <option value="rsi7" data-testid="user-indicator-screener-sort-by-option-rsi7">rsi7</option>
                    <option value="signal_score" data-testid="user-indicator-screener-sort-by-option-signal-score">signal_score</option>
                    <option value="confidence" data-testid="user-indicator-screener-sort-by-option-confidence">confidence</option>
                    <option value="rr_estimate" data-testid="user-indicator-screener-sort-by-option-rr-estimate">rr_estimate</option>
                    <option value="updated_at" data-testid="user-indicator-screener-sort-by-option-updated-at">updated_at</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-sort-direction-field">
                  <span className="text-xs text-slate-600">Sort Direction</span>
                  <select value={filters.sort_direction} onChange={(event) => updateFilter("sort_direction", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-sort-direction-select">
                    <option value="asc" data-testid="user-indicator-screener-sort-direction-option-asc">ASC</option>
                    <option value="desc" data-testid="user-indicator-screener-sort-direction-option-desc">DESC</option>
                  </select>
                </label>
              </div>
            </article>

            <article className="rounded-md border border-slate-200 bg-slate-50 p-3" data-testid="user-indicator-screener-group-universe-liquidity">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-600" data-testid="user-indicator-screener-group-universe-liquidity-title">Universe + Liquidity</p>
              <p className="mt-1 text-xs text-slate-500" data-testid="user-indicator-screener-group-universe-liquidity-helper">Tüm market yerine hedeflenmiş evren ve işlem kalitesi odaklı ön-eleme uygular.</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="user-indicator-screener-universe-liquidity-grid">
                <label className="space-y-1" data-testid="user-indicator-screener-symbol-search-field">
                  <span className="text-xs text-slate-600">Symbol Search</span>
                  <Input value={filters.symbol_search} onChange={(event) => updateFilter("symbol_search", event.target.value.toUpperCase())} placeholder="BTC, ETH, SOL" className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-symbol-search-input" />
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-universe-mode-field">
                  <span className="text-xs text-slate-600">Symbol Universe Mode</span>
                  <select value={filters.symbol_universe_mode} onChange={(event) => updateFilter("symbol_universe_mode", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-universe-mode-select">
                    <option value="all_tradable" data-testid="user-indicator-screener-universe-mode-option-all-tradable">all tradable</option>
                    <option value="top_by_volume" data-testid="user-indicator-screener-universe-mode-option-top-by-volume">top by volume</option>
                    <option value="whitelist_only" data-testid="user-indicator-screener-universe-mode-option-whitelist-only">whitelist only</option>
                    <option value="watchlist_only" data-testid="user-indicator-screener-universe-mode-option-watchlist-only">watchlist only</option>
                    <option value="saved_universe" data-testid="user-indicator-screener-universe-mode-option-saved-universe">saved universe</option>
                    <option value="futures_only_eligible_universe" data-testid="user-indicator-screener-universe-mode-option-futures-eligible">futures-only eligible universe</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-universe-top-n-field">
                  <span className="text-xs text-slate-600">Universe Top N</span>
                  <Input type="number" min={1} max={500} value={filters.universe_top_n} onChange={(event) => updateFilter("universe_top_n", Number(event.target.value || 1))} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-universe-top-n-input" />
                </label>
                {filters.symbol_universe_mode === "whitelist_only" && (
                  <label className="space-y-1 sm:col-span-2" data-testid="user-indicator-screener-whitelist-field">
                    <span className="text-xs text-slate-600">Whitelist (virgül ile)</span>
                    <Input value={filters.symbol_whitelist} onChange={(event) => updateFilter("symbol_whitelist", event.target.value)} placeholder="BTCUSDT,ETHUSDT,SOLUSDT" className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-whitelist-input" />
                  </label>
                )}
                {filters.symbol_universe_mode === "saved_universe" && (
                  <label className="space-y-1 sm:col-span-2" data-testid="user-indicator-screener-saved-universe-field">
                    <span className="text-xs text-slate-600">Saved Universe Query</span>
                    <select value={filters.saved_query_id} onChange={(event) => updateFilter("saved_query_id", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-saved-universe-select">
                      <option value="" data-testid="user-indicator-screener-saved-universe-option-latest">latest saved query</option>
                      {savedQueries.map((item) => (
                        <option key={item.id} value={item.id} data-testid={`user-indicator-screener-saved-universe-option-${item.id}`}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="space-y-1" data-testid="user-indicator-screener-min-volume-field">
                  <span className="text-xs text-slate-600">Min 24h Volume</span>
                  <Input type="number" min={0} value={filters.min_24h_volume} onChange={(event) => updateFilter("min_24h_volume", event.target.value)} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-min-volume-input" />
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-max-volume-field">
                  <span className="text-xs text-slate-600">Max 24h Volume</span>
                  <Input type="number" min={0} value={filters.max_24h_volume} onChange={(event) => updateFilter("max_24h_volume", event.target.value)} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-max-volume-input" />
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-quote-asset-field">
                  <span className="text-xs text-slate-600">Quote Asset</span>
                  <select value={filters.quote_asset_filter} onChange={(event) => updateFilter("quote_asset_filter", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-quote-asset-select">
                    <option value="ALL" data-testid="user-indicator-screener-quote-asset-option-all">ALL</option>
                    <option value="USDT" data-testid="user-indicator-screener-quote-asset-option-usdt">USDT</option>
                    <option value="BTC" data-testid="user-indicator-screener-quote-asset-option-btc">BTC</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-spread-threshold-field">
                  <span className="text-xs text-slate-600">Spread Threshold %</span>
                  <Input type="number" min={0} step="0.01" value={filters.spread_threshold_pct} onChange={(event) => updateFilter("spread_threshold_pct", event.target.value)} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-spread-threshold-input" />
                </label>
              </div>
            </article>

            <article className="rounded-md border border-slate-200 bg-slate-50 p-3" data-testid="user-indicator-screener-group-participation-quality">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-600" data-testid="user-indicator-screener-group-participation-quality-title">Participation + Result Quality</p>
              <p className="mt-1 text-xs text-slate-500" data-testid="user-indicator-screener-group-participation-quality-helper">İşlem yapılabilir, taze ve skor odaklı sonuç kümesi oluşturur.</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="user-indicator-screener-participation-filter-grid">
                <label className="space-y-1" data-testid="user-indicator-screener-market-participation-field">
                  <span className="text-xs text-slate-600">Market Participation</span>
                  <select value={filters.market_participation} onChange={(event) => updateFilter("market_participation", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-market-participation-select">
                    <option value="spot_only" data-testid="user-indicator-screener-market-participation-option-spot-only">spot only</option>
                    <option value="futures_only" data-testid="user-indicator-screener-market-participation-option-futures-only">futures only</option>
                    <option value="both" data-testid="user-indicator-screener-market-participation-option-both">both</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-pair-mode-field">
                  <span className="text-xs text-slate-600">Pair Filter</span>
                  <select value={filters.pair_mode} onChange={(event) => updateFilter("pair_mode", event.target.value)} className="h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm" data-testid="user-indicator-screener-pair-mode-select">
                    <option value="all" data-testid="user-indicator-screener-pair-mode-option-all">all</option>
                    <option value="usdt_only" data-testid="user-indicator-screener-pair-mode-option-usdt-only">USDT pairs only</option>
                    <option value="btc_only" data-testid="user-indicator-screener-pair-mode-option-btc-only">BTC pairs only</option>
                  </select>
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-freshness-tolerance-field">
                  <span className="text-xs text-slate-600">Freshness Tolerance (dk)</span>
                  <Input type="number" min={1} value={filters.last_candle_freshness_minutes} onChange={(event) => updateFilter("last_candle_freshness_minutes", Number(event.target.value || 1))} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-freshness-tolerance-input" />
                </label>

                <label className="space-y-1" data-testid="user-indicator-screener-min-signal-score-field">
                  <span className="text-xs text-slate-600">Min Signal Score</span>
                  <Input type="number" min={0} max={100} value={filters.min_signal_score} onChange={(event) => updateFilter("min_signal_score", event.target.value)} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-min-signal-score-input" />
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-min-confidence-field">
                  <span className="text-xs text-slate-600">Min Confidence</span>
                  <Input type="number" min={0} max={100} value={filters.min_confidence} onChange={(event) => updateFilter("min_confidence", event.target.value)} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-min-confidence-input" />
                </label>
                <label className="space-y-1" data-testid="user-indicator-screener-min-rr-field">
                  <span className="text-xs text-slate-600">Min RR Estimate</span>
                  <Input type="number" min={0} step="0.01" value={filters.min_rr_estimate} onChange={(event) => updateFilter("min_rr_estimate", event.target.value)} className="h-9 border-slate-300 bg-white" data-testid="user-indicator-screener-min-rr-input" />
                </label>

                <div className="flex flex-col justify-end gap-2" data-testid="user-indicator-screener-toggle-group-tradable">
                  <label className="flex items-center gap-2 text-sm text-slate-700" data-testid="user-indicator-screener-only-tradable-toggle-wrapper">
                    <input type="checkbox" checked={filters.only_tradable_pairs} onChange={(event) => updateFilter("only_tradable_pairs", event.target.checked)} data-testid="user-indicator-screener-only-tradable-toggle" />
                    only tradable pairs
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700" data-testid="user-indicator-screener-only-margin-toggle-wrapper">
                    <input type="checkbox" checked={filters.only_margin_eligible} onChange={(event) => updateFilter("only_margin_eligible", event.target.checked)} data-testid="user-indicator-screener-only-margin-toggle" />
                    only margin eligible
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700" data-testid="user-indicator-screener-only-futures-eligible-toggle-wrapper">
                    <input type="checkbox" checked={filters.only_futures_eligible} onChange={(event) => updateFilter("only_futures_eligible", event.target.checked)} data-testid="user-indicator-screener-only-futures-eligible-toggle" />
                    only futures eligible
                  </label>
                </div>
                <div className="flex flex-col justify-end gap-2" data-testid="user-indicator-screener-toggle-group-pair-exclusion">
                  <label className="flex items-center gap-2 text-sm text-slate-700" data-testid="user-indicator-screener-exclude-leveraged-toggle-wrapper">
                    <input type="checkbox" checked={filters.exclude_leveraged_tokens} onChange={(event) => updateFilter("exclude_leveraged_tokens", event.target.checked)} data-testid="user-indicator-screener-exclude-leveraged-toggle" />
                    leveraged token exclude
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700" data-testid="user-indicator-screener-exclude-stable-stable-toggle-wrapper">
                    <input type="checkbox" checked={filters.exclude_stablecoin_stablecoin_pairs} onChange={(event) => updateFilter("exclude_stablecoin_stablecoin_pairs", event.target.checked)} data-testid="user-indicator-screener-exclude-stable-stable-toggle" />
                    stablecoin/stablecoin pair exclude
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700" data-testid="user-indicator-screener-only-executable-toggle-wrapper">
                    <input type="checkbox" checked={filters.only_executable} onChange={(event) => updateFilter("only_executable", event.target.checked)} data-testid="user-indicator-screener-only-executable-toggle" />
                    only executable
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700" data-testid="user-indicator-screener-only-fresh-toggle-wrapper">
                    <input type="checkbox" checked={filters.only_fresh_data} onChange={(event) => updateFilter("only_fresh_data", event.target.checked)} data-testid="user-indicator-screener-only-fresh-toggle" />
                    only fresh data
                  </label>
                </div>
              </div>
            </article>

            <article className="rounded-md border border-slate-200 bg-slate-50 p-3 xl:col-span-2" data-testid="user-indicator-screener-group-presets-title">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-600" data-testid="user-indicator-screener-presets-title">Quick Presets</p>
              <p className="mt-1 text-xs text-slate-500" data-testid="user-indicator-screener-presets-helper">Preset seçimi query alanını doldurur; filtreler korunur.</p>
              <div className="mt-2 flex flex-wrap gap-2" data-testid="user-indicator-screener-presets-list">
                {presets.map((preset) => (
                  <Button key={preset.preset_key} className={buttonClass.secondary} onClick={() => applyPreset(preset)} data-testid={`user-indicator-screener-preset-button-${preset.preset_key}`}>{preset.title}</Button>
                ))}
                {presets.length === 0 && <p className="text-sm text-slate-500" data-testid="user-indicator-screener-presets-empty">Preset bulunmuyor.</p>}
              </div>
            </article>
          </div>
        )}

        <div className="mt-3" data-testid="user-indicator-screener-active-filters-panel">
          <p className="text-xs text-slate-600" data-testid="user-indicator-screener-active-filters-title">Active Filter Chips</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="user-indicator-screener-active-filters-list">
            {activeChips.map((chip, idx) => (
              <button key={`${chip.key}-${idx}`} type="button" onClick={() => clearSingleFilter(chip.key)} className="rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs text-emerald-900 hover:bg-emerald-100" data-testid={`user-indicator-screener-active-filter-chip-${chip.key}-${idx}`}>
                {chip.label}: {String(chip.value)} ✕
              </button>
            ))}
            {activeChips.length === 0 && <p className="text-sm text-slate-500" data-testid="user-indicator-screener-active-filters-empty">Aktif filtre yok.</p>}
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6" data-testid="user-indicator-screener-summary-grid">
        <article className="rounded-md border border-slate-300 bg-white p-3" data-testid="user-indicator-screener-summary-evaluated-card"><p className="text-xs text-slate-500">Evaluated</p><p className="text-xl font-semibold text-slate-900" data-testid="user-indicator-screener-summary-evaluated-value">{meta?.evaluated_count ?? 0}</p></article>
        <article className="rounded-md border border-slate-300 bg-white p-3" data-testid="user-indicator-screener-summary-match-card"><p className="text-xs text-slate-500">Match Count</p><p className="text-xl font-semibold text-slate-900" data-testid="user-indicator-screener-summary-match-value">{meta?.match_count ?? 0}</p></article>
        <article className="rounded-md border border-slate-300 bg-white p-3" data-testid="user-indicator-screener-summary-query-valid-card"><p className="text-xs text-slate-500">Query Valid</p><p className="text-xl font-semibold text-slate-900" data-testid="user-indicator-screener-summary-query-valid-value">{meta?.query_valid === undefined ? "-" : String(meta.query_valid)}</p></article>
        <article className="rounded-md border border-slate-300 bg-white p-3" data-testid="user-indicator-screener-summary-universe-card"><p className="text-xs text-slate-500">Universe</p><p className="text-xl font-semibold text-slate-900" data-testid="user-indicator-screener-summary-universe-value">{meta?.universe_count ?? 0}</p></article>
        <article className="rounded-md border border-slate-300 bg-white p-3" data-testid="user-indicator-screener-summary-skipped-card"><p className="text-xs text-slate-500">Skipped</p><p className="text-xl font-semibold text-slate-900" data-testid="user-indicator-screener-summary-skipped-value">{meta?.skipped_symbols?.length ?? 0}</p></article>
        <article className="rounded-md border border-slate-300 bg-white p-3" data-testid="user-indicator-screener-summary-result-state-card"><p className="text-xs text-slate-500">Result State</p><p className="text-xl font-semibold text-slate-900" data-testid="user-indicator-screener-summary-result-state-value">{effectiveState || "-"}</p></article>
      </div>

      {effectiveState !== "success" && (
        <div className={`rounded-md border p-3 ${stateCard.tone}`} data-testid="user-indicator-screener-state-contract-panel">
          <p className="text-sm font-semibold" data-testid="user-indicator-screener-state-contract-title">{stateCard.title}</p>
          <p className="mt-1 text-sm" data-testid="user-indicator-screener-state-contract-description">{stateCard.description}</p>
          {stateCard.ctaLabel ? (
            <Button className="mt-2 bg-white/80 text-slate-900 hover:bg-white border border-slate-300" onClick={stateCard.ctaAction} data-testid="user-indicator-screener-state-contract-cta-button">{stateCard.ctaLabel}</Button>
          ) : null}
        </div>
      )}

      {runError && effectiveState === "success" && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-900" data-testid="user-indicator-screener-run-error-banner">{runError}</div>
      )}

      {meta?.warnings?.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3" data-testid="user-indicator-screener-warning-list-panel">
          <p className="text-sm font-semibold text-amber-900" data-testid="user-indicator-screener-warning-list-title">Uyarılar</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900" data-testid="user-indicator-screener-warning-list-items">
            {meta.warnings.map((warning, idx) => (
              <li key={`${warning}-${idx}`} data-testid={`user-indicator-screener-warning-list-item-${idx}`}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <section className="rounded-lg border border-slate-300 bg-white p-4" data-testid="user-indicator-screener-results-section">
        <p className="text-xs uppercase tracking-widest text-slate-600" data-testid="user-indicator-screener-results-title">Sonuçlar</p>

        <div className="mt-3 space-y-2 md:hidden" data-testid="user-indicator-screener-mobile-card-list">
          {rows.map((row) => (
            <article key={`mobile-${row.symbol}-${row.market_type}`} className="rounded-md border border-slate-300 bg-slate-50 p-3" data-testid={`user-indicator-screener-mobile-card-${row.symbol}-${row.market_type}`}>
              <div className="flex items-center justify-between" data-testid={`user-indicator-screener-mobile-card-header-${row.symbol}-${row.market_type}`}>
                <p className="font-semibold text-slate-900" data-testid={`user-indicator-screener-mobile-symbol-${row.symbol}-${row.market_type}`}>{row.symbol}</p>
                <p className="text-xs text-slate-600" data-testid={`user-indicator-screener-mobile-market-${row.symbol}-${row.market_type}`}>{row.market_type} / {row.timeframe}</p>
              </div>
              <p className="mt-1 text-sm text-slate-700" data-testid={`user-indicator-screener-mobile-rsi-${row.symbol}-${row.market_type}`}>RSI14: {numberCell(row.rsi14, 2)} | RSI7: {numberCell(row.rsi7, 2)}</p>
              <p className="text-sm text-slate-700" data-testid={`user-indicator-screener-mobile-close-${row.symbol}-${row.market_type}`}>Close: {numberCell(row.close, 6)}</p>
              <p className="text-xs text-slate-600" data-testid={`user-indicator-screener-mobile-quality-${row.symbol}-${row.market_type}`}>Score: {numberCell(row.signal_score, 2)} | Conf: {numberCell(row.confidence, 2)} | RR: {numberCell(row.rr_estimate, 2)}</p>
              <div className="mt-2 flex gap-2" data-testid={`user-indicator-screener-mobile-actions-${row.symbol}-${row.market_type}`}>
                <Button size="sm" className={buttonClass.primary} onClick={() => openInExecute(row)} data-testid={`user-indicator-screener-mobile-open-execute-button-${row.symbol}-${row.market_type}`}>Execute</Button>
                <Button size="sm" className={buttonClass.secondary} onClick={() => addToWatchlist(row)} disabled={watchlistSymbolSet.has(`${row.symbol}:${row.market_type}`)} data-testid={`user-indicator-screener-mobile-watchlist-button-${row.symbol}-${row.market_type}`}>{watchlistSymbolSet.has(`${row.symbol}:${row.market_type}`) ? "Watchlist" : "Add WL"}</Button>
              </div>
            </article>
          ))}
        </div>

        <div className="mt-3 hidden md:block overflow-x-auto" data-testid="user-indicator-screener-table-wrapper">
          <table className={`min-w-[2200px] text-sm ${densityMode === "compact" ? "[&_td]:py-1 [&_th]:py-1" : "[&_td]:py-2 [&_th]:py-2"}`} data-testid="user-indicator-screener-table">
            <thead className="sticky top-0 z-20 bg-emerald-50 text-left" data-testid="user-indicator-screener-table-head">
              <tr>
                {[
                  ["index", "#", false],
                  ["exchange", "Exchange", false],
                  ["market_type", "Market", true],
                  ["symbol", "Symbol", true],
                  ["timeframe", "TF", false],
                  ["close", "Close", true],
                  ["rsi14", "RSI14", true],
                  ["rsi7", "RSI7", true],
                  ["ema20", "EMA20", false],
                  ["ema50", "EMA50", false],
                  ["fibo_161_8", "FIBO 161.8", false],
                  ["fibo_127_2", "FIBO 127.2", false],
                  ["fibo_100", "FIBO 100", false],
                  ["fibo_78_6", "FIBO 78.6", false],
                  ["volume_24h", "24h Vol", true],
                  ["signal_score", "Score", true],
                  ["confidence", "Confidence", true],
                  ["rr_estimate", "RR", true],
                  ["executable", "Executable", false],
                  ["stale_data", "Fresh", false],
                  ["matched_rules", "Matched Rules", false],
                  ["updated_at", "Updated At", true],
                ].map(([field, label, sortable]) => (
                  <th key={field} className={`px-2 font-semibold text-slate-700 ${["close", "rsi14", "rsi7", "volume_24h", "signal_score", "confidence", "rr_estimate"].includes(field) ? "text-right" : ""}`} data-testid={`user-indicator-screener-head-${field}`}>
                    {sortable ? (
                      <button type="button" onClick={() => applySortFromTableHeader(field)} className="inline-flex items-center gap-1 text-xs uppercase tracking-wide" data-testid={`user-indicator-screener-sort-button-${field}`}>
                        {label}
                        <span className="text-[10px]" data-testid={`user-indicator-screener-sort-icon-${field}`}>{filters.sort_by === field ? (filters.sort_direction === "asc" ? "▲" : "▼") : "↕"}</span>
                      </button>
                    ) : (
                      <span className="text-xs uppercase tracking-wide">{label}</span>
                    )}
                  </th>
                ))}
                <th className="sticky right-0 z-30 bg-emerald-50 px-2 text-xs uppercase tracking-wide text-slate-700" data-testid="user-indicator-screener-head-actions">Actions</th>
              </tr>
            </thead>
            <tbody data-testid="user-indicator-screener-table-body">
              {rows.map((row) => {
                const rowKey = `${row.symbol}-${row.market_type}`;
                const isSelected = selectedRowKey === rowKey;
                return (
                  <tr key={rowKey} onClick={() => setSelectedRowKey(rowKey)} className={`border-t border-slate-200 hover:bg-emerald-50/50 ${isSelected ? "bg-emerald-50" : "bg-white"}`} data-testid={`user-indicator-screener-row-${row.symbol}-${row.market_type}`}>
                    <td className="px-2" data-testid={`user-indicator-screener-cell-index-${row.symbol}-${row.market_type}`}>{row.index}</td>
                    <td className="px-2" data-testid={`user-indicator-screener-cell-exchange-${row.symbol}-${row.market_type}`}>{row.exchange}</td>
                    <td className="px-2" data-testid={`user-indicator-screener-cell-market-type-${row.symbol}-${row.market_type}`}>{row.market_type}</td>
                    <td className="px-2 font-semibold" data-testid={`user-indicator-screener-cell-symbol-${row.symbol}-${row.market_type}`}>{row.symbol}</td>
                    <td className="px-2" data-testid={`user-indicator-screener-cell-timeframe-${row.symbol}-${row.market_type}`}>{row.timeframe}</td>
                    <td className={`px-2 text-right tabular-nums ${isMatchedField(row, "close") ? "bg-emerald-100 text-emerald-900" : ""}`} data-testid={`user-indicator-screener-cell-close-${row.symbol}-${row.market_type}`}>{numberCell(row.close, 6)}</td>
                    <td className={`px-2 text-right tabular-nums ${row.rsi14 < 30 ? "text-rose-600 font-semibold" : ""} ${isMatchedField(row, "rsi14") ? "bg-emerald-100" : ""}`} data-testid={`user-indicator-screener-cell-rsi14-${row.symbol}-${row.market_type}`}>{numberCell(row.rsi14, 2)}</td>
                    <td className={`px-2 text-right tabular-nums ${row.rsi7 < 30 ? "text-amber-600 font-semibold" : ""} ${isMatchedField(row, "rsi7") ? "bg-emerald-100" : ""}`} data-testid={`user-indicator-screener-cell-rsi7-${row.symbol}-${row.market_type}`}>{numberCell(row.rsi7, 2)}</td>
                    <td className={`px-2 text-right tabular-nums ${isMatchedField(row, "ema20") ? "bg-emerald-100 text-emerald-900" : ""}`} data-testid={`user-indicator-screener-cell-ema20-${row.symbol}-${row.market_type}`}>{numberCell(row.ema20, 6)}</td>
                    <td className={`px-2 text-right tabular-nums ${isMatchedField(row, "ema50") ? "bg-emerald-100 text-emerald-900" : ""}`} data-testid={`user-indicator-screener-cell-ema50-${row.symbol}-${row.market_type}`}>{numberCell(row.ema50, 6)}</td>
                    <td className={`px-2 text-right tabular-nums ${isMatchedField(row, "fibo_161_8") ? "bg-emerald-100 text-emerald-900" : ""}`} data-testid={`user-indicator-screener-cell-fibo-1618-${row.symbol}-${row.market_type}`}>{numberCell(row.fibo_161_8, 6)}</td>
                    <td className={`px-2 text-right tabular-nums ${isMatchedField(row, "fibo_127_2") ? "bg-emerald-100 text-emerald-900" : ""}`} data-testid={`user-indicator-screener-cell-fibo-1272-${row.symbol}-${row.market_type}`}>{numberCell(row.fibo_127_2, 6)}</td>
                    <td className={`px-2 text-right tabular-nums ${isMatchedField(row, "fibo_100") ? "bg-emerald-100 text-emerald-900" : ""}`} data-testid={`user-indicator-screener-cell-fibo-100-${row.symbol}-${row.market_type}`}>{numberCell(row.fibo_100, 6)}</td>
                    <td className={`px-2 text-right tabular-nums ${isMatchedField(row, "fibo_78_6") ? "bg-emerald-100 text-emerald-900" : ""}`} data-testid={`user-indicator-screener-cell-fibo-786-${row.symbol}-${row.market_type}`}>{numberCell(row.fibo_78_6, 6)}</td>
                    <td className="px-2 text-right tabular-nums" data-testid={`user-indicator-screener-cell-volume24h-${row.symbol}-${row.market_type}`}>{numberCell(row.volume_24h, 2)}</td>
                    <td className="px-2 text-right tabular-nums" data-testid={`user-indicator-screener-cell-score-${row.symbol}-${row.market_type}`}>{numberCell(row.signal_score, 2)}</td>
                    <td className="px-2 text-right tabular-nums" data-testid={`user-indicator-screener-cell-confidence-${row.symbol}-${row.market_type}`}>{numberCell(row.confidence, 2)}</td>
                    <td className="px-2 text-right tabular-nums" data-testid={`user-indicator-screener-cell-rr-${row.symbol}-${row.market_type}`}>{numberCell(row.rr_estimate, 2)}</td>
                    <td className={`px-2 text-center ${row.executable ? "text-emerald-700" : "text-rose-600"}`} data-testid={`user-indicator-screener-cell-executable-${row.symbol}-${row.market_type}`}>{String(row.executable)}</td>
                    <td className={`px-2 text-center ${row.stale_data ? "text-rose-600" : "text-emerald-700"}`} data-testid={`user-indicator-screener-cell-freshness-${row.symbol}-${row.market_type}`}>{row.stale_data ? "stale" : "fresh"}</td>
                    <td className="px-2 text-xs text-slate-700" data-testid={`user-indicator-screener-cell-matched-rules-${row.symbol}-${row.market_type}`}>{(row.matched_rules || []).join(" | ") || "-"}</td>
                    <td className="px-2 text-xs text-slate-600" data-testid={`user-indicator-screener-cell-updated-at-${row.symbol}-${row.market_type}`}>{row.updated_at ? new Date(row.updated_at).toLocaleString() : "-"}</td>
                    <td className="sticky right-0 z-10 px-2 bg-white" data-testid={`user-indicator-screener-cell-actions-${row.symbol}-${row.market_type}`}>
                      <div className="flex flex-nowrap gap-1" data-testid={`user-indicator-screener-row-actions-${row.symbol}-${row.market_type}`}>
                        <Button size="sm" className={buttonClass.primary} onClick={() => openInExecute(row)} data-testid={`user-indicator-screener-open-execute-button-${row.symbol}-${row.market_type}`}>Open in Execute</Button>
                        <Button size="sm" className={buttonClass.secondary} onClick={() => addToWatchlist(row)} disabled={watchlistSymbolSet.has(`${row.symbol}:${row.market_type}`)} data-testid={`user-indicator-screener-add-watchlist-button-${row.symbol}-${row.market_type}`}>{watchlistSymbolSet.has(`${row.symbol}:${row.market_type}`) ? "Watchlist" : "Add to Watchlist"}</Button>
                        <Button size="sm" className={buttonClass.warning} onClick={createSignalRule} disabled={!createSignalRuleFeatureEnabled} data-testid={`user-indicator-screener-create-signal-rule-button-${row.symbol}-${row.market_type}`}>Create Signal Rule</Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr className="border-t border-slate-200" data-testid="user-indicator-screener-table-empty-row">
                  <td colSpan={23} className="px-2 py-4 text-center text-sm text-slate-500" data-testid="user-indicator-screener-table-empty-text">Sonuç bulunmuyor.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="user-indicator-screener-bridge-grid">
        <section className="rounded-lg border border-slate-300 bg-white p-4" data-testid="user-indicator-screener-saved-queries-section">
          <p className="text-xs uppercase tracking-widest text-slate-600" data-testid="user-indicator-screener-saved-queries-title">Saved Queries</p>
          <div className="mt-3 space-y-2" data-testid="user-indicator-screener-saved-queries-list">
            {savedQueries.map((item) => (
              <article key={item.id} className="rounded-md border border-slate-200 bg-slate-50 p-3" data-testid={`user-indicator-screener-saved-query-row-${item.id}`}>
                <p className="text-sm font-semibold text-slate-900" data-testid={`user-indicator-screener-saved-query-name-${item.id}`}>{item.name}</p>
                <p className="mt-1 text-xs text-slate-600" data-testid={`user-indicator-screener-saved-query-expression-${item.id}`}>{item.query_expression || "(query yok - filter only)"}</p>
                <p className="mt-1 text-xs text-slate-500" data-testid={`user-indicator-screener-saved-query-meta-${item.id}`}>schema: {item.schema_version} | {item.market_type} | {item.timeframe}</p>
                <div className="mt-2 flex gap-2" data-testid={`user-indicator-screener-saved-query-actions-${item.id}`}>
                  <Button size="sm" className={buttonClass.secondary} onClick={() => applySavedQuery(item)} data-testid={`user-indicator-screener-apply-saved-query-button-${item.id}`}>Uygula</Button>
                  <Button size="sm" className={buttonClass.danger} onClick={() => deleteSavedQuery(item.id)} data-testid={`user-indicator-screener-delete-saved-query-button-${item.id}`}>Sil</Button>
                </div>
              </article>
            ))}
            {savedQueries.length === 0 && <p className="text-sm text-slate-500" data-testid="user-indicator-screener-saved-queries-empty">Kayıtlı sorgu yok.</p>}
          </div>
        </section>

        <section className="rounded-lg border border-slate-300 bg-white p-4" data-testid="user-indicator-screener-watchlist-section">
          <p className="text-xs uppercase tracking-widest text-slate-600" data-testid="user-indicator-screener-watchlist-title">Watchlist</p>
          <div className="mt-3 space-y-2" data-testid="user-indicator-screener-watchlist-list">
            {watchlistRows.map((item) => (
              <article key={item.id} className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 p-3" data-testid={`user-indicator-screener-watchlist-row-${item.id}`}>
                <div data-testid={`user-indicator-screener-watchlist-content-${item.id}`}>
                  <p className="text-sm font-semibold text-slate-900" data-testid={`user-indicator-screener-watchlist-symbol-${item.id}`}>{item.symbol}</p>
                  <p className="text-xs text-slate-600" data-testid={`user-indicator-screener-watchlist-note-${item.id}`}>{item.note || "-"}</p>
                </div>
                <Button size="sm" className={buttonClass.danger} onClick={() => deleteWatchlist(item.id)} data-testid={`user-indicator-screener-delete-watchlist-button-${item.id}`}>Sil</Button>
              </article>
            ))}
            {watchlistRows.length === 0 && <p className="text-sm text-slate-500" data-testid="user-indicator-screener-watchlist-empty">Watchlist boş.</p>}
          </div>
        </section>
      </div>
    </section>
  );
};
