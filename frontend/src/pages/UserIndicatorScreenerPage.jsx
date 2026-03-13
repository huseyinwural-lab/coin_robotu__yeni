import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";

const createSignalRuleFeatureEnabled = false;

const defaultFilters = {
  exchange: "binance",
  market_type: "spot",
  timeframe: "15m",
  query_expression: "rsi14 < 30",
  limit: 50,
  symbol_universe_mode: "all",
  symbol_whitelist: "",
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
    "symbol",
    "timeframe",
    "close",
    "rsi14",
    "rsi7",
    "ema20",
    "ema50",
    "fibo_161_8",
    "fibo_127_2",
    "fibo_100",
    "fibo_78_6",
    "matched_rules",
    "updated_at",
  ];

  const body = rows.map((row) => [
    row.index,
    row.exchange,
    row.symbol,
    row.timeframe,
    row.close,
    row.rsi14,
    row.rsi7,
    row.ema20,
    row.ema50,
    row.fibo_161_8,
    row.fibo_127_2,
    row.fibo_100,
    row.fibo_78_6,
    (row.matched_rules || []).join(" | "),
    row.updated_at || "",
  ]);

  return [headers.join(","), ...body.map((line) => line.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))].join("\n");
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
  const [sortConfig, setSortConfig] = useState({ key: "symbol", direction: "asc" });

  const watchlistSymbolSet = useMemo(() => new Set((watchlistRows || []).map((item) => item.symbol)), [watchlistRows]);

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

  const sortedRows = useMemo(() => {
    const list = [...rows];
    const { key, direction } = sortConfig;
    list.sort((a, b) => {
      const left = a[key];
      const right = b[key];
      if (typeof left === "number" && typeof right === "number") {
        return direction === "asc" ? left - right : right - left;
      }
      return direction === "asc" ? String(left ?? "").localeCompare(String(right ?? "")) : String(right ?? "").localeCompare(String(left ?? ""));
    });
    return list;
  }, [rows, sortConfig]);

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const applyPreset = (preset) => {
    updateFilter("query_expression", preset.query_expression);
    toast.success(`Preset yüklendi: ${preset.title}`);
  };

  const runQuery = async () => {
    setIsRunning(true);
    setRunError("");
    try {
      const payload = {
        exchange: filters.exchange,
        market_type: filters.market_type,
        timeframe: filters.timeframe,
        query_expression: filters.query_expression,
        limit: Number(filters.limit),
        symbol_universe:
          filters.symbol_universe_mode === "all"
            ? "all"
            : (filters.symbol_whitelist || "")
                .split(",")
                .map((item) => item.trim().toUpperCase())
                .filter(Boolean),
      };
      const { data } = await apiClient.post("/user/indicator-screener/run", payload);
      setMeta(data || null);
      setRows(data?.rows || []);
      if (!data?.query_valid) {
        setRunError(data?.query_error || "Geçersiz query");
        toast.error(data?.query_error || "Geçersiz query");
      } else {
        toast.success(`Tarama tamamlandı. Eşleşme: ${data?.match_count || 0}`);
      }
    } catch (error) {
      const message = error?.response?.data?.detail || "Indicator query çalıştırılamadı";
      setRunError(message);
      toast.error(message);
    } finally {
      setIsRunning(false);
    }
  };

  const clearQuery = () => {
    setFilters(defaultFilters);
    setRows([]);
    setMeta(null);
    setRunError("");
    setSaveQueryName("");
  };

  const saveCurrentQuery = async () => {
    try {
      const payload = {
        name: saveQueryName,
        exchange: filters.exchange,
        market_type: filters.market_type,
        timeframe: filters.timeframe,
        query_expression: filters.query_expression,
        symbol_universe:
          filters.symbol_universe_mode === "all"
            ? []
            : (filters.symbol_whitelist || "")
                .split(",")
                .map((item) => item.trim().toUpperCase())
                .filter(Boolean),
        result_limit: Number(filters.limit),
      };
      await apiClient.post("/user/indicator-screener/saved-queries", payload);
      toast.success("Sorgu kaydedildi");
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

  const addToWatchlist = async (row) => {
    try {
      await apiClient.post("/user/indicator-screener/watchlist", {
        exchange: row.exchange,
        market_type: row.market_type,
        symbol: row.symbol,
        note: `indicator-screener:${filters.query_expression}`,
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
    if (!sortedRows.length) {
      toast.error("Export için sonuç bulunmuyor");
      return;
    }
    const csv = toCsv(sortedRows);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `indicator_screener_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const applySavedQuery = (item) => {
    setFilters({
      exchange: item.exchange,
      market_type: item.market_type,
      timeframe: item.timeframe,
      query_expression: item.query_expression,
      limit: item.result_limit,
      symbol_universe_mode: item.symbol_universe?.length ? "whitelist" : "all",
      symbol_whitelist: (item.symbol_universe || []).join(","),
    });
    toast.success(`Sorgu yüklendi: ${item.name}`);
  };

  const toggleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === "asc" ? "desc" : "asc" };
      }
      return { key, direction: "asc" };
    });
  };

  const openInExecute = (row) => {
    navigate(`/user/execute?symbol=${row.symbol}&side=BUY&quantity=0.001&timeInForce=GTC&source=indicator-screener`);
  };

  const createSignalRule = () => {
    toast.info("Create Signal Rule bu sürümde feature flag altında hazırlık modunda.");
  };

  const isMatchedField = (row, field) => (row.matched_fields || []).includes(field);

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
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-indicator-screener-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="user-indicator-screener-header-row">
          <div data-testid="user-indicator-screener-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-indicator-screener-title">Indicator Screener</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="user-indicator-screener-description">Borsa → timeframe → query ile koşulu sağlayan coinleri yoğun tablo görünümünde tarar.</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="user-indicator-screener-last-calculated">Son hesaplama: {meta?.calculation_timestamp ? new Date(meta.calculation_timestamp).toLocaleString() : "-"}</p>
          </div>
          <div className="flex items-center gap-2" data-testid="user-indicator-screener-header-actions">
            <Button variant="outline" onClick={() => setDensityMode((prev) => (prev === "compact" ? "wide" : "compact"))} data-testid="user-indicator-screener-density-toggle-button">
              Mode: {densityMode === "compact" ? "Compact" : "Wide"}
            </Button>
            <Button variant="outline" onClick={exportCsv} data-testid="user-indicator-screener-export-csv-button">Export CSV</Button>
          </div>
        </div>
      </header>

      {loadError && (
        <div className="border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="user-indicator-screener-warning-alert">Açılış yüklemesinde uyarı: {loadError}</div>
      )}

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="user-indicator-screener-filter-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-indicator-screener-filter-title">Filtre Paneli</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="user-indicator-screener-filter-grid">
          <label className="space-y-1" data-testid="user-indicator-screener-exchange-field">
            <span className="text-xs text-slate-500">Exchange</span>
            <select value={filters.exchange} onChange={(event) => updateFilter("exchange", event.target.value)} className="h-9 w-full rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="user-indicator-screener-exchange-select">
              <option value="binance" data-testid="user-indicator-screener-exchange-option-binance">Binance</option>
            </select>
          </label>

          <label className="space-y-1" data-testid="user-indicator-screener-market-type-field">
            <span className="text-xs text-slate-500">Market Type</span>
            <select value={filters.market_type} onChange={(event) => updateFilter("market_type", event.target.value)} className="h-9 w-full rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="user-indicator-screener-market-type-select">
              <option value="spot" data-testid="user-indicator-screener-market-type-option-spot">Spot</option>
              <option value="futures" data-testid="user-indicator-screener-market-type-option-futures">Futures</option>
            </select>
          </label>

          <label className="space-y-1" data-testid="user-indicator-screener-timeframe-field">
            <span className="text-xs text-slate-500">Timeframe</span>
            <select value={filters.timeframe} onChange={(event) => updateFilter("timeframe", event.target.value)} className="h-9 w-full rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="user-indicator-screener-timeframe-select">
              <option value="5m" data-testid="user-indicator-screener-timeframe-option-5m">5m</option>
              <option value="15m" data-testid="user-indicator-screener-timeframe-option-15m">15m</option>
              <option value="1h" data-testid="user-indicator-screener-timeframe-option-1h">1h</option>
              <option value="4h" data-testid="user-indicator-screener-timeframe-option-4h">4h</option>
              <option value="1d" data-testid="user-indicator-screener-timeframe-option-1d">1d</option>
            </select>
          </label>

          <label className="space-y-1" data-testid="user-indicator-screener-limit-field">
            <span className="text-xs text-slate-500">Result Limit</span>
            <Input type="number" min={1} max={300} value={filters.limit} onChange={(event) => updateFilter("limit", Number(event.target.value || 1))} data-testid="user-indicator-screener-limit-input" />
          </label>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2" data-testid="user-indicator-screener-query-grid">
          <label className="space-y-1" data-testid="user-indicator-screener-query-field">
            <span className="text-xs text-slate-500">Query Expression</span>
            <Textarea value={filters.query_expression} onChange={(event) => updateFilter("query_expression", event.target.value)} className="min-h-20" data-testid="user-indicator-screener-query-textarea" />
          </label>

          <div className="space-y-3" data-testid="user-indicator-screener-universe-panel">
            <label className="space-y-1" data-testid="user-indicator-screener-universe-mode-field">
              <span className="text-xs text-slate-500">Symbol Universe</span>
              <select value={filters.symbol_universe_mode} onChange={(event) => updateFilter("symbol_universe_mode", event.target.value)} className="h-9 w-full rounded border border-slate-700 bg-slate-950 px-2 text-sm" data-testid="user-indicator-screener-universe-mode-select">
                <option value="all" data-testid="user-indicator-screener-universe-mode-option-all">all tradable</option>
                <option value="whitelist" data-testid="user-indicator-screener-universe-mode-option-whitelist">whitelist</option>
              </select>
            </label>

            {filters.symbol_universe_mode === "whitelist" && (
              <label className="space-y-1" data-testid="user-indicator-screener-whitelist-field">
                <span className="text-xs text-slate-500">Whitelist (virgül ile)</span>
                <Input value={filters.symbol_whitelist} onChange={(event) => updateFilter("symbol_whitelist", event.target.value)} placeholder="BTCUSDT,ETHUSDT,SOLUSDT" data-testid="user-indicator-screener-whitelist-input" />
              </label>
            )}

            <div className="flex flex-wrap gap-2" data-testid="user-indicator-screener-filter-actions">
              <Button onClick={runQuery} disabled={isRunning} data-testid="user-indicator-screener-run-button">{isRunning ? "Çalışıyor..." : "Run"}</Button>
              <Button variant="outline" onClick={clearQuery} data-testid="user-indicator-screener-clear-button">Clear</Button>
              <Button variant="outline" onClick={saveCurrentQuery} data-testid="user-indicator-screener-save-query-button">Save Query</Button>
            </div>
            <Input value={saveQueryName} onChange={(event) => setSaveQueryName(event.target.value)} placeholder="Sorgu adı (opsiyonel)" data-testid="user-indicator-screener-save-query-name-input" />
          </div>
        </div>

        <div className="mt-3" data-testid="user-indicator-screener-presets-panel">
          <p className="text-xs text-slate-500" data-testid="user-indicator-screener-presets-title">Quick Presets</p>
          <div className="mt-2 flex flex-wrap gap-2" data-testid="user-indicator-screener-presets-list">
            {presets.map((preset) => (
              <Button key={preset.preset_key} variant="outline" onClick={() => applyPreset(preset)} data-testid={`user-indicator-screener-preset-button-${preset.preset_key}`}>
                {preset.title}
              </Button>
            ))}
            {presets.length === 0 && <p className="text-sm text-slate-400" data-testid="user-indicator-screener-presets-empty">Preset bulunmuyor.</p>}
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="user-indicator-screener-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-indicator-screener-summary-evaluated-card">
          <p className="text-xs text-slate-500">Evaluated</p>
          <p className="text-xl font-semibold" data-testid="user-indicator-screener-summary-evaluated-value">{meta?.evaluated_count ?? 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-indicator-screener-summary-match-card">
          <p className="text-xs text-slate-500">Match Count</p>
          <p className="text-xl font-semibold" data-testid="user-indicator-screener-summary-match-value">{meta?.match_count ?? 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-indicator-screener-summary-query-valid-card">
          <p className="text-xs text-slate-500">Query Valid</p>
          <p className="text-xl font-semibold" data-testid="user-indicator-screener-summary-query-valid-value">{meta?.query_valid === undefined ? "-" : String(meta.query_valid)}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-indicator-screener-summary-universe-card">
          <p className="text-xs text-slate-500">Universe</p>
          <p className="text-xl font-semibold" data-testid="user-indicator-screener-summary-universe-value">{meta?.universe_count ?? 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="user-indicator-screener-summary-skipped-card">
          <p className="text-xs text-slate-500">Skipped</p>
          <p className="text-xl font-semibold" data-testid="user-indicator-screener-summary-skipped-value">{meta?.skipped_symbols?.length ?? 0}</p>
        </article>
      </div>

      {runError && (
        <div className="border border-rose-500/40 bg-rose-900/20 p-3 text-sm text-rose-200" data-testid="user-indicator-screener-run-error-banner">{runError}</div>
      )}

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="user-indicator-screener-results-section">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-indicator-screener-results-title">Sonuçlar</p>

        {meta?.query_valid && sortedRows.length === 0 && (
          <div className="mt-3 border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400" data-testid="user-indicator-screener-empty-state">Bu query için eşleşme bulunamadı. (empty state)</div>
        )}

        <div className="mt-3 md:hidden space-y-2" data-testid="user-indicator-screener-mobile-card-list">
          {sortedRows.map((row) => (
            <article key={`mobile-${row.symbol}`} className="border border-slate-800 bg-slate-950 p-3" data-testid={`user-indicator-screener-mobile-card-${row.symbol}`}>
              <div className="flex items-center justify-between" data-testid={`user-indicator-screener-mobile-card-header-${row.symbol}`}>
                <p className="font-semibold" data-testid={`user-indicator-screener-mobile-symbol-${row.symbol}`}>{row.symbol}</p>
                <p className="text-xs text-slate-400" data-testid={`user-indicator-screener-mobile-timeframe-${row.symbol}`}>{row.timeframe}</p>
              </div>
              <p className="mt-1 text-sm text-slate-300" data-testid={`user-indicator-screener-mobile-rsi-${row.symbol}`}>RSI14: {numberCell(row.rsi14, 2)} | RSI7: {numberCell(row.rsi7, 2)}</p>
              <p className="text-sm text-slate-300" data-testid={`user-indicator-screener-mobile-close-${row.symbol}`}>Close: {numberCell(row.close, 6)}</p>
              <div className="mt-2 flex gap-2" data-testid={`user-indicator-screener-mobile-actions-${row.symbol}`}>
                <Button size="sm" onClick={() => openInExecute(row)} data-testid={`user-indicator-screener-mobile-open-execute-button-${row.symbol}`}>Execute</Button>
                <Button size="sm" variant="outline" onClick={() => addToWatchlist(row)} disabled={watchlistSymbolSet.has(row.symbol)} data-testid={`user-indicator-screener-mobile-watchlist-button-${row.symbol}`}>
                  {watchlistSymbolSet.has(row.symbol) ? "Watchlist" : "Add WL"}
                </Button>
              </div>
            </article>
          ))}
        </div>

        <div className="mt-3 hidden md:block overflow-x-auto" data-testid="user-indicator-screener-table-wrapper">
          <table className={`min-w-[1500px] text-sm ${densityMode === "compact" ? "[&_td]:py-1 [&_th]:py-1" : "[&_td]:py-2 [&_th]:py-2"}`} data-testid="user-indicator-screener-table">
            <thead className="bg-slate-800 text-left" data-testid="user-indicator-screener-table-head">
              <tr>
                {["index", "exchange", "symbol", "timeframe", "close", "rsi14", "rsi7", "ema20", "ema50", "fibo_161_8", "fibo_127_2", "fibo_100", "fibo_78_6", "matched_rules", "updated_at"].map((field) => (
                  <th key={field} className="px-2" data-testid={`user-indicator-screener-table-head-${field}`}>
                    <button type="button" onClick={() => toggleSort(field)} className="text-left text-xs uppercase tracking-wide text-slate-300 hover:text-white" data-testid={`user-indicator-screener-sort-button-${field}`}>
                      {field}
                    </button>
                  </th>
                ))}
                <th className="px-2" data-testid="user-indicator-screener-table-head-actions">actions</th>
              </tr>
            </thead>
            <tbody data-testid="user-indicator-screener-table-body">
              {sortedRows.map((row) => (
                <tr key={row.symbol} className="border-t border-slate-800" data-testid={`user-indicator-screener-row-${row.symbol}`}>
                  <td className="px-2" data-testid={`user-indicator-screener-cell-index-${row.symbol}`}>{row.index}</td>
                  <td className="px-2" data-testid={`user-indicator-screener-cell-exchange-${row.symbol}`}>{row.exchange}</td>
                  <td className="px-2 font-semibold" data-testid={`user-indicator-screener-cell-symbol-${row.symbol}`}>{row.symbol}</td>
                  <td className="px-2" data-testid={`user-indicator-screener-cell-timeframe-${row.symbol}`}>{row.timeframe}</td>
                  <td className={`px-2 ${isMatchedField(row, "close") ? "bg-emerald-950/40 text-emerald-300" : ""}`} data-testid={`user-indicator-screener-cell-close-${row.symbol}`}>{numberCell(row.close, 6)}</td>
                  <td className={`px-2 ${row.rsi14 < 30 ? "text-rose-300 font-semibold" : ""} ${isMatchedField(row, "rsi14") ? "bg-emerald-950/40" : ""}`} data-testid={`user-indicator-screener-cell-rsi14-${row.symbol}`}>{numberCell(row.rsi14, 2)}</td>
                  <td className={`px-2 ${row.rsi7 < 30 ? "text-amber-300 font-semibold" : ""} ${isMatchedField(row, "rsi7") ? "bg-emerald-950/40" : ""}`} data-testid={`user-indicator-screener-cell-rsi7-${row.symbol}`}>{numberCell(row.rsi7, 2)}</td>
                  <td className={`px-2 ${isMatchedField(row, "ema20") ? "bg-emerald-950/40 text-emerald-300" : ""}`} data-testid={`user-indicator-screener-cell-ema20-${row.symbol}`}>{numberCell(row.ema20, 6)}</td>
                  <td className={`px-2 ${isMatchedField(row, "ema50") ? "bg-emerald-950/40 text-emerald-300" : ""}`} data-testid={`user-indicator-screener-cell-ema50-${row.symbol}`}>{numberCell(row.ema50, 6)}</td>
                  <td className={`px-2 ${isMatchedField(row, "fibo_161_8") ? "bg-emerald-950/40 text-emerald-300" : ""}`} data-testid={`user-indicator-screener-cell-fibo-1618-${row.symbol}`}>{numberCell(row.fibo_161_8, 6)}</td>
                  <td className={`px-2 ${isMatchedField(row, "fibo_127_2") ? "bg-emerald-950/40 text-emerald-300" : ""}`} data-testid={`user-indicator-screener-cell-fibo-1272-${row.symbol}`}>{numberCell(row.fibo_127_2, 6)}</td>
                  <td className={`px-2 ${isMatchedField(row, "fibo_100") ? "bg-emerald-950/40 text-emerald-300" : ""}`} data-testid={`user-indicator-screener-cell-fibo-100-${row.symbol}`}>{numberCell(row.fibo_100, 6)}</td>
                  <td className={`px-2 ${isMatchedField(row, "fibo_78_6") ? "bg-emerald-950/40 text-emerald-300" : ""}`} data-testid={`user-indicator-screener-cell-fibo-786-${row.symbol}`}>{numberCell(row.fibo_78_6, 6)}</td>
                  <td className="px-2 text-xs text-slate-300" data-testid={`user-indicator-screener-cell-matched-rules-${row.symbol}`}>{(row.matched_rules || []).join(" | ") || "-"}</td>
                  <td className="px-2 text-xs text-slate-400" data-testid={`user-indicator-screener-cell-updated-at-${row.symbol}`}>{row.updated_at ? new Date(row.updated_at).toLocaleString() : "-"}</td>
                  <td className="px-2">
                    <div className="flex flex-wrap gap-1" data-testid={`user-indicator-screener-row-actions-${row.symbol}`}>
                      <Button size="sm" onClick={() => openInExecute(row)} data-testid={`user-indicator-screener-open-execute-button-${row.symbol}`}>Open in Execute</Button>
                      <Button size="sm" variant="outline" onClick={() => addToWatchlist(row)} disabled={watchlistSymbolSet.has(row.symbol)} data-testid={`user-indicator-screener-add-watchlist-button-${row.symbol}`}>
                        {watchlistSymbolSet.has(row.symbol) ? "Watchlist" : "Add to Watchlist"}
                      </Button>
                      <Button size="sm" variant="outline" onClick={createSignalRule} disabled={!createSignalRuleFeatureEnabled} data-testid={`user-indicator-screener-create-signal-rule-button-${row.symbol}`}>
                        Create Signal Rule
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {sortedRows.length === 0 && (
                <tr className="border-t border-slate-800" data-testid="user-indicator-screener-table-empty-row">
                  <td colSpan={16} className="px-2 py-4 text-center text-sm text-slate-400" data-testid="user-indicator-screener-table-empty-text">Sonuç bulunmuyor.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="user-indicator-screener-bridge-grid">
        <section className="border border-slate-800 bg-slate-900 p-4" data-testid="user-indicator-screener-saved-queries-section">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-indicator-screener-saved-queries-title">Saved Queries</p>
          <div className="mt-3 space-y-2" data-testid="user-indicator-screener-saved-queries-list">
            {savedQueries.map((item) => (
              <article key={item.id} className="border border-slate-800 bg-slate-950 p-3" data-testid={`user-indicator-screener-saved-query-row-${item.id}`}>
                <p className="text-sm font-semibold" data-testid={`user-indicator-screener-saved-query-name-${item.id}`}>{item.name}</p>
                <p className="mt-1 text-xs text-slate-400" data-testid={`user-indicator-screener-saved-query-expression-${item.id}`}>{item.query_expression}</p>
                <div className="mt-2 flex gap-2" data-testid={`user-indicator-screener-saved-query-actions-${item.id}`}>
                  <Button size="sm" onClick={() => applySavedQuery(item)} data-testid={`user-indicator-screener-apply-saved-query-button-${item.id}`}>Uygula</Button>
                  <Button size="sm" variant="outline" onClick={() => deleteSavedQuery(item.id)} data-testid={`user-indicator-screener-delete-saved-query-button-${item.id}`}>Sil</Button>
                </div>
              </article>
            ))}
            {savedQueries.length === 0 && <p className="text-sm text-slate-400" data-testid="user-indicator-screener-saved-queries-empty">Kayıtlı sorgu yok.</p>}
          </div>
        </section>

        <section className="border border-slate-800 bg-slate-900 p-4" data-testid="user-indicator-screener-watchlist-section">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-indicator-screener-watchlist-title">Watchlist</p>
          <div className="mt-3 space-y-2" data-testid="user-indicator-screener-watchlist-list">
            {watchlistRows.map((item) => (
              <article key={item.id} className="flex items-center justify-between border border-slate-800 bg-slate-950 p-3" data-testid={`user-indicator-screener-watchlist-row-${item.id}`}>
                <div data-testid={`user-indicator-screener-watchlist-content-${item.id}`}>
                  <p className="text-sm font-semibold" data-testid={`user-indicator-screener-watchlist-symbol-${item.id}`}>{item.symbol}</p>
                  <p className="text-xs text-slate-400" data-testid={`user-indicator-screener-watchlist-note-${item.id}`}>{item.note || "-"}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => deleteWatchlist(item.id)} data-testid={`user-indicator-screener-delete-watchlist-button-${item.id}`}>Sil</Button>
              </article>
            ))}
            {watchlistRows.length === 0 && <p className="text-sm text-slate-400" data-testid="user-indicator-screener-watchlist-empty">Watchlist boş.</p>}
          </div>
        </section>
      </div>
    </section>
  );
};
