import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LineChart, Play, Settings2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const EXCHANGE_OPTIONS = [
  { value: "binance", label: "Binance" },
  { value: "bybit", label: "Bybit" },
];

const MARKET_TYPE_OPTIONS = [
  { value: "spot", label: "Spot" },
  { value: "futures", label: "Futures" },
];

const toFriendlyError = (error, fallback = "Tarama çalıştırılamadı") => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parsed = detail
      .map((item) => (typeof item === "object" ? (item?.msg || item?.type || "") : String(item || "")))
      .filter(Boolean)
      .join(" | ");
    if (parsed) return parsed;
  }
  return error?.message || fallback;
};

const normalizeConditionExpression = (rawCondition) => {
  const source = String(rawCondition || "").trim();
  if (!source) {
    throw new Error("Koşul boş olamaz");
  }

  const normalized = source
    .replace(/G[ÜU]NCEL\s*F[İI]YAT/gi, "last_price")
    .replace(/ANLIK\s*F[İI]YAT/gi, "last_price")
    .replace(/LAST\s*PRICE/gi, "last_price")
    .replace(/KAPANI[ŞS]/gi, "close")
    .replace(/CLOSE/gi, "close")
    .replace(/\s*(<=|>=|!=|=|<|>)\s*/g, " $1 ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

  return normalized;
};

export const UserSimpleScannerPage = () => {
  const navigate = useNavigate();

  const [exchange, setExchange] = useState("binance");
  const [marketType, setMarketType] = useState("spot");
  const [manualCondition, setManualCondition] = useState("rsi14 > 70");
  const [autoRefreshMinutes, setAutoRefreshMinutes] = useState("1");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [rows, setRows] = useState([]);
  const [lastRunQueryExpression, setLastRunQueryExpression] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);

  const liveQueryPreview = useMemo(() => {
    try {
      return normalizeConditionExpression(manualCondition);
    } catch {
      return "-";
    }
  }, [manualCondition]);

  const runSimpleScan = useCallback(async ({ silent = false } = {}) => {
    setIsRunning(true);
    try {
      const expression = normalizeConditionExpression(manualCondition);
      setLastRunQueryExpression(expression);

      const payload = {
        exchange,
        market_type: marketType,
        timeframe: "15m",
        query_expression: expression,
        symbol_universe: "all",
        limit: 60,
        filter_payload: {
          symbol_universe_mode: "top_by_volume",
          universe_top_n: 220,
          sort_by: "signal_score",
          sort_direction: "desc",
          market_participation: marketType === "futures" ? "futures_only" : "spot_only",
          pair_mode: "usdt_only",
          min_24h_volume: 100000,
        },
      };

      const { data } = await apiClient.post("/user/indicator-screener/run", payload);
      setRows(data?.rows || []);
      setLastUpdatedAt(new Date().toISOString());
      if (!silent) {
        toast.success(`Tarama tamamlandı: ${data?.match_count || 0} sonuç`);
      }
    } catch (error) {
      if (!silent) {
        toast.error(toFriendlyError(error));
      }
    } finally {
      setIsRunning(false);
    }
  }, [exchange, marketType, manualCondition]);

  useEffect(() => {
    if (!autoRefreshEnabled) return undefined;
    const minutes = Math.max(1, Number.parseInt(String(autoRefreshMinutes || ""), 10) || 1);
    const timer = window.setInterval(() => {
      runSimpleScan({ silent: true });
    }, minutes * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [autoRefreshEnabled, autoRefreshMinutes, runSimpleScan]);

  return (
    <section className="mx-auto w-full max-w-6xl space-y-4 p-4 sm:p-6" data-testid="simple-scanner-page">
      <header className="rounded-xl border border-slate-200 bg-white p-5" data-testid="simple-scanner-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="simple-scanner-header-row">
          <div data-testid="simple-scanner-header-copy">
            <h1 className="text-4xl font-black tracking-tight text-slate-900" data-testid="simple-scanner-title">Basit Scanner</h1>
            <p className="mt-1 text-sm text-slate-600" data-testid="simple-scanner-subtitle">
              1) Borsa 2) Spot/Futures 3) Manuel Koşul 4) Run 5) Sonuç + Grafik
            </p>
          </div>
          <Button type="button" variant="outline" onClick={() => navigate("/user/pro-scanner")} data-testid="simple-scanner-pro-view-button">
            <Settings2 className="mr-2 h-4 w-4" />
            Profesyonel Görünüm
          </Button>
        </div>
      </header>

      <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="simple-scanner-controls-card">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="simple-scanner-controls-grid">
          <label className="space-y-1" data-testid="simple-scanner-exchange-field">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">1. Borsa</span>
            <select className="h-10 w-full rounded border border-slate-300 px-3" value={exchange} onChange={(event) => setExchange(event.target.value)} data-testid="simple-scanner-exchange-select">
              {EXCHANGE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>

          <label className="space-y-1" data-testid="simple-scanner-market-type-field">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">2. Market</span>
            <select className="h-10 w-full rounded border border-slate-300 px-3" value={marketType} onChange={(event) => setMarketType(event.target.value)} data-testid="simple-scanner-market-type-select">
              {MARKET_TYPE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>

          <label className="space-y-1" data-testid="simple-scanner-auto-refresh-field">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Otomatik Güncelleme (dk)</span>
            <Input value={autoRefreshMinutes} onChange={(event) => setAutoRefreshMinutes(event.target.value)} placeholder="1/3/5/10" data-testid="simple-scanner-auto-refresh-minutes-input" />
          </label>

          <label className="space-y-1 sm:col-span-2 lg:col-span-3" data-testid="simple-scanner-condition-field">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">3. Koşul (manuel)</span>
            <Input value={manualCondition} onChange={(event) => setManualCondition(event.target.value)} placeholder="örn: rsi14 > 70 veya ema21 > güncel fiyat" data-testid="simple-scanner-condition-input" />
            <p className="text-xs text-slate-500" data-testid="simple-scanner-condition-helper">
              Örnekler: <strong>RSI14&gt;70</strong>, <strong>EMA21&gt;GÜNCEL FİYAT</strong>, <strong>SMA20&gt;SMA50</strong>
            </p>
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2" data-testid="simple-scanner-run-row">
          <Button type="button" onClick={runSimpleScan} disabled={isRunning} data-testid="simple-scanner-run-button">
            <Play className="mr-2 h-4 w-4" />
            {isRunning ? "Çalışıyor..." : "4. Run"}
          </Button>
          <Button
            type="button"
            variant={autoRefreshEnabled ? "default" : "outline"}
            onClick={() => setAutoRefreshEnabled((prev) => !prev)}
            data-testid="simple-scanner-auto-refresh-toggle-button"
          >
            {autoRefreshEnabled ? "Auto: Açık" : "Auto: Kapalı"}
          </Button>
          <p className="text-xs text-slate-500" data-testid="simple-scanner-query-preview">Query: {liveQueryPreview}</p>
          <p className="text-xs text-slate-500" data-testid="simple-scanner-last-run-query">Son Run: {lastRunQueryExpression || "-"}</p>
          <p className="text-xs text-slate-500" data-testid="simple-scanner-last-updated-at">Son güncelleme: {lastUpdatedAt || "-"}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="simple-scanner-results-card">
        <div className="mb-3 flex items-center justify-between" data-testid="simple-scanner-results-header-row">
          <h2 className="text-lg font-bold text-slate-900" data-testid="simple-scanner-results-title">5. Sonuç Listesi</h2>
          <p className="text-xs text-slate-500" data-testid="simple-scanner-results-count">Toplam: {rows.length}</p>
        </div>

        <div className="overflow-x-auto" data-testid="simple-scanner-results-table-wrap">
          <table className="min-w-full border-collapse text-sm" data-testid="simple-scanner-results-table">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-2 py-2" data-testid="simple-scanner-col-symbol">Symbol</th>
                <th className="px-2 py-2" data-testid="simple-scanner-col-close">Close</th>
                <th className="px-2 py-2" data-testid="simple-scanner-col-last-price">Anlık</th>
                <th className="px-2 py-2" data-testid="simple-scanner-col-rsi">RSI</th>
                <th className="px-2 py-2" data-testid="simple-scanner-col-ema">EMA</th>
                <th className="px-2 py-2" data-testid="simple-scanner-col-score">Skor</th>
                <th className="px-2 py-2" data-testid="simple-scanner-col-chart">Grafik</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const symbol = String(row?.symbol || "").toUpperCase();
                return (
                  <tr key={`${symbol}-${index}`} className="border-b border-slate-100" data-testid={`simple-scanner-row-${index}`}>
                    <td className="px-2 py-2 font-semibold text-slate-900" data-testid={`simple-scanner-row-symbol-${index}`}>{symbol}</td>
                    <td className="px-2 py-2 text-slate-700" data-testid={`simple-scanner-row-close-${index}`}>{row?.close}</td>
                    <td className="px-2 py-2 text-slate-700" data-testid={`simple-scanner-row-last-price-${index}`}>{row?.last_price}</td>
                    <td className="px-2 py-2 text-slate-700" data-testid={`simple-scanner-row-rsi-${index}`}>rsi7:{row?.rsi7} · rsi14:{row?.rsi14}</td>
                    <td className="px-2 py-2 text-slate-700" data-testid={`simple-scanner-row-ema-${index}`}>ema20:{row?.ema20} · ema50:{row?.ema50}</td>
                    <td className="px-2 py-2 text-slate-700" data-testid={`simple-scanner-row-score-${index}`}>{row?.signal_score}</td>
                    <td className="px-2 py-2" data-testid={`simple-scanner-row-chart-cell-${index}`}>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/user/chart?symbol=${encodeURIComponent(symbol)}&tf=15m`)}
                        data-testid={`simple-scanner-open-chart-button-${index}`}
                      >
                        <LineChart className="mr-1 h-4 w-4" />
                        Grafik
                      </Button>
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr data-testid="simple-scanner-empty-row">
                  <td colSpan={7} className="px-2 py-6 text-center text-sm text-slate-500" data-testid="simple-scanner-empty-message">
                    Henüz sonuç yok. Üstten manuel koşulu girip Run yap.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};
