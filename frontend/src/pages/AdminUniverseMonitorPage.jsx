import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

export const AdminUniverseMonitorPage = () => {
  const { user } = useAuth();
  const isSuperAdmin = String(user?.role || "") === "super_admin";
  const isProductionEnv = String(process.env.REACT_APP_ENV || "").toLowerCase() === "production";
  const canShowDebug = isSuperAdmin && !isProductionEnv;
  const [mode, setMode] = useState("ALL_MARKET_SYMBOLS");
  const [windowSize, setWindowSize] = useState("24h");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [debugPayload, setDebugPayload] = useState(null);
  const [trend, setTrend] = useState({ points: [] });
  const [breakdown, setBreakdown] = useState({ user_breakdown: [], regime_breakdown: [] });
  const [heatmap, setHeatmap] = useState({ items: [] });
  const [rollout, setRollout] = useState(null);
  const [fallbackEvents, setFallbackEvents] = useState([]);
  const [runtimeSummary, setRuntimeSummary] = useState(null);
  const [statusContract, setStatusContract] = useState(null);
  const [scannerEngineConfig, setScannerEngineConfig] = useState({
    exchange: "binance",
    include_spot: true,
    include_futures: true,
    signal_mode: "manual",
    scan_limit: 80,
    top_n: 20,
    manual_symbols: [],
    indicator_timeframe: "1h",
    execution_timeframe: "15m",
  });
  const [manualSymbolsInput, setManualSymbolsInput] = useState("");
  const [scannerEngineRun, setScannerEngineRun] = useState({
    status: "empty",
    summary: {
      max_score: 161,
      candidate_count: 0,
      scored_count: 0,
      strong_long_count: 0,
      strong_short_count: 0,
    },
    top_results: [],
    results: [],
  });
  const [scannerEngineJobs, setScannerEngineJobs] = useState([]);
  const [scannerEngineBusy, setScannerEngineBusy] = useState(false);
  const [startBotModalOpen, setStartBotModalOpen] = useState(false);
  const [startBotForm, setStartBotForm] = useState({
    selection_mode: "top_n",
    top_n: 20,
    side_filter: "all",
    selected_symbols: [],
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryRes, trendRes, breakdownRes, heatmapRes, rolloutRes, fallbackEventsRes, runtimeSummaryRes] = await Promise.all([
        apiClient.get("/admin/universe-monitor", { params: { market_type: "spot", scanner_mode: mode, top_n: 200 } }),
        apiClient.get("/admin/universe-monitor/trends", { params: { window: windowSize } }),
        apiClient.get("/admin/universe-monitor/breakdown", { params: { window: windowSize } }),
        apiClient.get("/admin/universe-monitor/freshness-heatmap", { params: { window: windowSize } }),
        apiClient.get("/admin/universe-monitor/rollout/status"),
        apiClient.get("/admin/universe-monitor/fallback-events", { params: { limit: 80 } }),
        apiClient.get("/admin/universe/runtime-summary", { params: { scanner_mode: mode, top_n: 200 } }),
      ]);
      let debugRes = { data: null };
      if (canShowDebug) {
        try {
          debugRes = await apiClient.get("/debug/effective-universe", { params: { market_type: "spot", scanner_mode: mode, top_n: 200 } });
        } catch {
          debugRes = { data: null };
        }
      }
      setSummary(summaryRes.data || null);
      setDebugPayload(debugRes.data || null);
      setTrend(trendRes.data || { points: [] });
      setBreakdown(breakdownRes.data || { user_breakdown: [], regime_breakdown: [] });
      setHeatmap(heatmapRes.data || { items: [] });
      setRollout(rolloutRes.data || null);
      setFallbackEvents(fallbackEventsRes?.data?.items || []);
      setRuntimeSummary(runtimeSummaryRes?.data || null);
      try {
        const statusContractRes = await apiClient.get("/admin/strategy/status-contract", { timeout: 8000 });
        setStatusContract(statusContractRes?.data || null);
      } catch {
        setStatusContract(null);
      }

      try {
        const [scannerConfigRes, scannerRunRes, scannerJobsRes] = await Promise.all([
          apiClient.get("/admin/universe-monitor/scanner-engine/config"),
          apiClient.get("/admin/universe-monitor/scanner-engine/last-run"),
          apiClient.get("/admin/universe-monitor/scanner-engine/bot/jobs", { params: { limit: 20 } }),
        ]);
        const configData = scannerConfigRes?.data || {};
        setScannerEngineConfig((prev) => ({ ...prev, ...configData }));
        setManualSymbolsInput((prev) => (prev ? prev : (configData?.manual_symbols || []).join(",")));
        setScannerEngineRun(scannerRunRes?.data || { status: "empty", summary: {}, top_results: [], results: [] });
        setScannerEngineJobs(scannerJobsRes?.data?.items || []);
      } catch {
        // scanner engine panel'i, monitor ana akışını bozmadan sessizce fallback eder
      }
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const errorMessage = typeof detail === "string" ? detail : (Array.isArray(detail) ? detail.map(d => d?.msg || JSON.stringify(d)).join(", ") : "Universe monitor verisi alınamadı");
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [mode, windowSize, canShowDebug]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => {
      load();
    }, 10000);
    return () => clearInterval(timer);
  }, [load]);

  const latestTrendPoint = useMemo(() => trend?.latest || trend?.points?.[trend.points.length - 1] || null, [trend]);

  const requestRolloutRecommendation = async () => {
    try {
      await apiClient.post("/admin/universe-monitor/rollout/recommend");
      toast.success("Rollout recommendation üretildi");
      load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Recommendation üretilemedi");
    }
  };

  const approveRolloutRecommendation = async () => {
    try {
      await apiClient.post("/admin/universe-monitor/rollout/approve");
      toast.success("Rollout stage admin onayı ile güncellendi");
      load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rollout approve başarısız");
    }
  };

  const downloadCsv = async () => {
    try {
      const { data } = await apiClient.get("/admin/universe-monitor/export.csv", {
        params: { window: windowSize },
        responseType: "blob",
      });
      const blobUrl = window.URL.createObjectURL(new Blob([data], { type: "text/csv" }));
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `universe_monitor_${windowSize}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "CSV export başarısız");
    }
  };

  const saveScannerEngineConfig = async () => {
    setScannerEngineBusy(true);
    try {
      const manualSymbols = manualSymbolsInput
        .split(/[\s,;]+/)
        .map((item) => String(item || "").trim().toUpperCase())
        .filter(Boolean);
      const payload = {
        exchange: "binance",
        include_spot: Boolean(scannerEngineConfig.include_spot),
        include_futures: Boolean(scannerEngineConfig.include_futures),
        signal_mode: scannerEngineConfig.signal_mode || "manual",
        scan_limit: Number(scannerEngineConfig.scan_limit || 80),
        top_n: Number(scannerEngineConfig.top_n || 20),
        manual_symbols: manualSymbols,
        reason: "scanner_engine_config_save",
      };
      const { data } = await apiClient.post("/admin/universe-monitor/scanner-engine/config/save", payload);
      setScannerEngineConfig((prev) => ({ ...prev, ...(data?.config || payload) }));
      toast.success("Scanner Engine ayarları kaydedildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ayarlar kaydedilemedi");
    } finally {
      setScannerEngineBusy(false);
    }
  };

  const runScannerEngine = async () => {
    setScannerEngineBusy(true);
    try {
      const { data } = await apiClient.post("/admin/universe-monitor/scanner-engine/run", {
        force_refresh: false,
        reason: "manual_scanner_run",
      });
      setScannerEngineRun(data || { status: "empty", summary: {}, results: [] });
      toast.success(`Scanner tamamlandı: ${data?.summary?.scored_count || 0} sembol skorlandı`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Scanner run başarısız");
    } finally {
      setScannerEngineBusy(false);
    }
  };

  const openStartBotModal = () => {
    const defaultTopN = Number(scannerEngineConfig?.top_n || 20);
    const defaultSymbols = (scannerEngineRun?.top_results || []).slice(0, defaultTopN).map((item) => item.symbol);
    setStartBotForm({
      selection_mode: "top_n",
      top_n: defaultTopN,
      side_filter: "all",
      selected_symbols: defaultSymbols,
    });
    setStartBotModalOpen(true);
  };

  const toggleStartBotSymbol = (symbol) => {
    setStartBotForm((prev) => {
      const set = new Set(prev.selected_symbols || []);
      if (set.has(symbol)) {
        set.delete(symbol);
      } else {
        set.add(symbol);
      }
      return { ...prev, selected_symbols: Array.from(set) };
    });
  };

  const startScannerJob = async () => {
    setScannerEngineBusy(true);
    try {
      const payload = {
        selection_mode: startBotForm.selection_mode,
        top_n: Number(startBotForm.top_n || 20),
        side_filter: startBotForm.side_filter || "all",
        selected_symbols: startBotForm.selected_symbols || [],
        reason: "start_scanner_job",
      };
      const { data } = await apiClient.post("/admin/universe-monitor/scanner-engine/bot/start", payload);
      setStartBotModalOpen(false);
      setScannerEngineJobs((prev) => [data?.job, ...prev].filter(Boolean).slice(0, 20));
      toast.success(`Scanner-job oluşturuldu: ${data?.job?.symbol_count || 0} sembol`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Scanner-job oluşturulamadı");
    } finally {
      setScannerEngineBusy(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-universe-monitor-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="admin-universe-monitor-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="admin-universe-monitor-title">Universe Monitor</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-universe-monitor-description">
          Throughput / latency / freshness / rollout durumunu tek panelde izleyin.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2" data-testid="admin-universe-monitor-toolbar">
        <label className="space-y-1" data-testid="admin-universe-monitor-mode-field">
          <span className="text-xs text-slate-400">Scanner Mode</span>
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value)}
            className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid="admin-universe-monitor-mode-select"
          >
            <option value="ALL_MARKET_SYMBOLS" data-testid="admin-universe-monitor-mode-option-all">ALL_MARKET_SYMBOLS</option>
            <option value="TOP_VOLUME" data-testid="admin-universe-monitor-mode-option-top">TOP_VOLUME</option>
            <option value="MANUAL_SELECTION" data-testid="admin-universe-monitor-mode-option-manual">MANUAL_SELECTION</option>
          </select>
        </label>

        <label className="space-y-1" data-testid="admin-universe-monitor-window-field">
          <span className="text-xs text-slate-400">Trend Window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(event.target.value)}
            className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid="admin-universe-monitor-window-select"
          >
            <option value="24h" data-testid="admin-universe-monitor-window-24h">24s</option>
            <option value="7d" data-testid="admin-universe-monitor-window-7d">7g</option>
            <option value="30d" data-testid="admin-universe-monitor-window-30d">30g</option>
          </select>
        </label>

        <Button type="button" variant="outline" onClick={load} data-testid="admin-universe-monitor-refresh-button">
          Yenile
        </Button>
        <Button type="button" variant="outline" onClick={downloadCsv} data-testid="admin-universe-monitor-export-csv-button">
          Export CSV
        </Button>
        <Link to="/admin/freshness-heatmap" data-testid="admin-universe-monitor-open-heatmap-link">
          <Button type="button" variant="outline" data-testid="admin-universe-monitor-open-heatmap-button">Freshness Heatmap Sayfası</Button>
        </Link>
      </div>

      <article className="hidden rounded-xl border border-cyan-700/40 bg-cyan-950/20 p-4" data-testid="admin-universe-monitor-scanner-engine-panel">
        <div className="flex flex-wrap items-end justify-between gap-3" data-testid="admin-universe-monitor-scanner-engine-header">
          <div data-testid="admin-universe-monitor-scanner-engine-title-wrap">
            <p className="text-xs uppercase tracking-widest text-cyan-200" data-testid="admin-universe-monitor-scanner-engine-kicker">Scanner Engine</p>
            <h3 className="text-xl font-bold text-cyan-50" data-testid="admin-universe-monitor-scanner-engine-title">Short/Long Decoupled Scanner</h3>
            <p className="text-xs text-cyan-100/90" data-testid="admin-universe-monitor-scanner-engine-subtitle">Binance only · 1h indikatör · 15m execution</p>
          </div>
          <div className="grid gap-1 text-xs text-cyan-100" data-testid="admin-universe-monitor-scanner-engine-summary-strip">
            <p data-testid="admin-universe-monitor-scanner-engine-max-score">Max Score: {scannerEngineRun?.summary?.max_score ?? 161}</p>
            <p data-testid="admin-universe-monitor-scanner-engine-strong-long-count">Strong Long: {scannerEngineRun?.summary?.strong_long_count ?? 0}</p>
            <p data-testid="admin-universe-monitor-scanner-engine-strong-short-count">Strong Short: {scannerEngineRun?.summary?.strong_short_count ?? 0}</p>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="admin-universe-monitor-scanner-engine-config-grid">
          <label className="space-y-1" data-testid="admin-universe-monitor-scanner-engine-exchange-field">
            <span className="text-xs text-cyan-100">Market</span>
            <input
              value="BINANCE"
              disabled
              className="h-10 w-full rounded border border-cyan-700/40 bg-slate-950 px-2 text-sm text-cyan-50"
              data-testid="admin-universe-monitor-scanner-engine-exchange-input"
            />
          </label>

          <div className="space-y-1" data-testid="admin-universe-monitor-scanner-engine-market-types-field">
            <span className="text-xs text-cyan-100">Market Types</span>
            <div className="flex h-10 items-center gap-3 rounded border border-cyan-700/40 bg-slate-950 px-2" data-testid="admin-universe-monitor-scanner-engine-market-types-wrap">
              <label className="flex items-center gap-1 text-xs" data-testid="admin-universe-monitor-scanner-engine-spot-label">
                <input
                  type="checkbox"
                  checked={Boolean(scannerEngineConfig.include_spot)}
                  onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, include_spot: event.target.checked }))}
                  data-testid="admin-universe-monitor-scanner-engine-spot-checkbox"
                />
                Spot
              </label>
              <label className="flex items-center gap-1 text-xs" data-testid="admin-universe-monitor-scanner-engine-futures-label">
                <input
                  type="checkbox"
                  checked={Boolean(scannerEngineConfig.include_futures)}
                  onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, include_futures: event.target.checked }))}
                  data-testid="admin-universe-monitor-scanner-engine-futures-checkbox"
                />
                Futures
              </label>
            </div>
          </div>

          <label className="space-y-1" data-testid="admin-universe-monitor-scanner-engine-signal-mode-field">
            <span className="text-xs text-cyan-100">Signal Mode</span>
            <select
              value={scannerEngineConfig.signal_mode || "manual"}
              onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, signal_mode: event.target.value }))}
              className="h-10 w-full rounded border border-cyan-700/40 bg-slate-950 px-2 text-sm"
              data-testid="admin-universe-monitor-scanner-engine-signal-mode-select"
            >
              <option value="manual" data-testid="admin-universe-monitor-scanner-engine-signal-mode-manual">MANUAL</option>
              <option value="auto" data-testid="admin-universe-monitor-scanner-engine-signal-mode-auto">AUTO</option>
            </select>
          </label>

          <label className="space-y-1" data-testid="admin-universe-monitor-scanner-engine-scan-limit-field">
            <span className="text-xs text-cyan-100">Scan Limit</span>
            <input
              type="number"
              min={10}
              max={220}
              value={scannerEngineConfig.scan_limit || 80}
              onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, scan_limit: Number(event.target.value || 80) }))}
              className="h-10 w-full rounded border border-cyan-700/40 bg-slate-950 px-2 text-sm"
              data-testid="admin-universe-monitor-scanner-engine-scan-limit-input"
            />
          </label>

          <label className="space-y-1" data-testid="admin-universe-monitor-scanner-engine-topn-field">
            <span className="text-xs text-cyan-100">Top N</span>
            <input
              type="number"
              min={1}
              max={150}
              value={scannerEngineConfig.top_n || 20}
              onChange={(event) => setScannerEngineConfig((prev) => ({ ...prev, top_n: Number(event.target.value || 20) }))}
              className="h-10 w-full rounded border border-cyan-700/40 bg-slate-950 px-2 text-sm"
              data-testid="admin-universe-monitor-scanner-engine-topn-input"
            />
          </label>

          <label className="space-y-1 md:col-span-2 xl:col-span-3" data-testid="admin-universe-monitor-scanner-engine-manual-symbols-field">
            <span className="text-xs text-cyan-100">Manual Symbols (opsiyonel)</span>
            <input
              value={manualSymbolsInput}
              onChange={(event) => setManualSymbolsInput(event.target.value)}
              placeholder="BTCUSDT,ETHUSDT"
              className="h-10 w-full rounded border border-cyan-700/40 bg-slate-950 px-2 text-sm"
              data-testid="admin-universe-monitor-scanner-engine-manual-symbols-input"
            />
          </label>

          <div className="flex flex-wrap items-end gap-2" data-testid="admin-universe-monitor-scanner-engine-actions">
            <Button
              type="button"
              variant="outline"
              onClick={saveScannerEngineConfig}
              disabled={scannerEngineBusy}
              data-testid="admin-universe-monitor-scanner-engine-save-button"
            >
              SAVE
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={runScannerEngine}
              disabled={scannerEngineBusy}
              data-testid="admin-universe-monitor-scanner-engine-run-button"
            >
              RUN SCANNER
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={openStartBotModal}
              disabled={scannerEngineBusy || (scannerEngineRun?.results || []).length === 0}
              data-testid="admin-universe-monitor-scanner-engine-start-bot-button"
            >
              START BOT
            </Button>
          </div>
        </div>

        <div className="mt-4 grid gap-2 md:grid-cols-4" data-testid="admin-universe-monitor-scanner-engine-run-stats">
          <article className="rounded border border-cyan-700/30 bg-black/30 p-2" data-testid="admin-universe-monitor-scanner-engine-candidate-count-card">
            <p className="text-[11px] text-cyan-200">Candidate</p>
            <p className="text-base font-semibold" data-testid="admin-universe-monitor-scanner-engine-candidate-count-value">{scannerEngineRun?.summary?.candidate_count ?? 0}</p>
          </article>
          <article className="rounded border border-cyan-700/30 bg-black/30 p-2" data-testid="admin-universe-monitor-scanner-engine-scored-count-card">
            <p className="text-[11px] text-cyan-200">Scored</p>
            <p className="text-base font-semibold" data-testid="admin-universe-monitor-scanner-engine-scored-count-value">{scannerEngineRun?.summary?.scored_count ?? 0}</p>
          </article>
          <article className="rounded border border-cyan-700/30 bg-black/30 p-2" data-testid="admin-universe-monitor-scanner-engine-long-count-card">
            <p className="text-[11px] text-cyan-200">Long Signal</p>
            <p className="text-base font-semibold" data-testid="admin-universe-monitor-scanner-engine-long-count-value">{scannerEngineRun?.summary?.long_signal_count ?? 0}</p>
          </article>
          <article className="rounded border border-cyan-700/30 bg-black/30 p-2" data-testid="admin-universe-monitor-scanner-engine-short-count-card">
            <p className="text-[11px] text-cyan-200">Short Signal</p>
            <p className="text-base font-semibold" data-testid="admin-universe-monitor-scanner-engine-short-count-value">{scannerEngineRun?.summary?.short_signal_count ?? 0}</p>
          </article>
        </div>

        <div className="mt-4 overflow-auto rounded border border-cyan-700/30" data-testid="admin-universe-monitor-scanner-engine-results-wrapper">
          <table className="min-w-full text-left text-xs" data-testid="admin-universe-monitor-scanner-engine-results-table">
            <thead className="bg-black/40 text-cyan-100" data-testid="admin-universe-monitor-scanner-engine-results-head">
              <tr>
                <th className="px-2 py-2" data-testid="admin-universe-monitor-scanner-engine-results-head-symbol">Symbol</th>
                <th className="px-2 py-2" data-testid="admin-universe-monitor-scanner-engine-results-head-market">Market</th>
                <th className="px-2 py-2" data-testid="admin-universe-monitor-scanner-engine-results-head-classification">Class</th>
                <th className="px-2 py-2" data-testid="admin-universe-monitor-scanner-engine-results-head-long">Long</th>
                <th className="px-2 py-2" data-testid="admin-universe-monitor-scanner-engine-results-head-short">Short</th>
                <th className="px-2 py-2" data-testid="admin-universe-monitor-scanner-engine-results-head-breakdown">Policy Breakdown</th>
                <th className="px-2 py-2" data-testid="admin-universe-monitor-scanner-engine-results-head-execution">Execution(15m)</th>
              </tr>
            </thead>
            <tbody data-testid="admin-universe-monitor-scanner-engine-results-body">
              {(scannerEngineRun?.results || []).slice(0, 120).map((item, index) => (
                <tr key={`${item.symbol}-${item.market_type}-${index}`} className="border-t border-cyan-800/20" data-testid={`admin-universe-monitor-scanner-engine-result-row-${index}`}>
                  <td className="px-2 py-2 font-semibold" data-testid={`admin-universe-monitor-scanner-engine-result-symbol-${index}`}>{item.symbol}</td>
                  <td className="px-2 py-2" data-testid={`admin-universe-monitor-scanner-engine-result-market-${index}`}>{item.market_type}</td>
                  <td className="px-2 py-2" data-testid={`admin-universe-monitor-scanner-engine-result-class-${index}`}>
                    <span className="rounded border border-cyan-600/60 px-2 py-0.5">{item.classification}</span>
                  </td>
                  <td className="px-2 py-2" data-testid={`admin-universe-monitor-scanner-engine-result-long-score-${index}`}>{item.long_score}</td>
                  <td className="px-2 py-2" data-testid={`admin-universe-monitor-scanner-engine-result-short-score-${index}`}>{item.short_score}</td>
                  <td className="px-2 py-2" data-testid={`admin-universe-monitor-scanner-engine-result-breakdown-${index}`}>{item?.breakdown?.long || "-"} · {item?.breakdown?.short || "-"}</td>
                  <td className="px-2 py-2" data-testid={`admin-universe-monitor-scanner-engine-result-execution-${index}`}>{item?.execution_context?.change_pct?.toFixed?.(2) ?? item?.execution_context?.change_pct ?? "-"}%</td>
                </tr>
              ))}
              {(scannerEngineRun?.results || []).length === 0 && (
                <tr data-testid="admin-universe-monitor-scanner-engine-results-empty-row">
                  <td className="px-2 py-3 text-cyan-200" colSpan={7} data-testid="admin-universe-monitor-scanner-engine-results-empty">Henüz scanner sonucu yok.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-3 space-y-2" data-testid="admin-universe-monitor-scanner-engine-jobs-panel">
          <p className="text-xs uppercase tracking-widest text-cyan-200" data-testid="admin-universe-monitor-scanner-engine-jobs-title">Scanner Jobs</p>
          {(scannerEngineJobs || []).slice(0, 8).map((job, index) => (
            <div key={job.job_id || index} className="rounded border border-cyan-800/30 bg-black/30 p-2 text-xs" data-testid={`admin-universe-monitor-scanner-engine-job-${index}`}>
              <p data-testid={`admin-universe-monitor-scanner-engine-job-id-${index}`}>job_id: {job.job_id}</p>
              <p data-testid={`admin-universe-monitor-scanner-engine-job-symbol-count-${index}`}>symbol_count: {job.symbol_count}</p>
              <p data-testid={`admin-universe-monitor-scanner-engine-job-selection-${index}`}>selection_mode: {job.selection_mode} · side_filter: {job.side_filter}</p>
              <p data-testid={`admin-universe-monitor-scanner-engine-job-status-${index}`}>status: {job.status}</p>
            </div>
          ))}
          {(scannerEngineJobs || []).length === 0 && <p className="text-xs text-cyan-200" data-testid="admin-universe-monitor-scanner-engine-jobs-empty">Henüz scanner-job kaydı yok.</p>}
        </div>
      </article>

      <Dialog open={startBotModalOpen} onOpenChange={setStartBotModalOpen}>
        <DialogContent className="max-w-2xl" data-testid="admin-universe-monitor-start-bot-modal">
          <DialogHeader data-testid="admin-universe-monitor-start-bot-modal-header">
            <DialogTitle data-testid="admin-universe-monitor-start-bot-modal-title">START BOT · Scanner Job</DialogTitle>
            <DialogDescription data-testid="admin-universe-monitor-start-bot-modal-description">
              Bu işlem sadece scanner-job kaydı oluşturur, trade akışını tetiklemez.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 md:grid-cols-3" data-testid="admin-universe-monitor-start-bot-modal-form-grid">
            <label className="space-y-1" data-testid="admin-universe-monitor-start-bot-selection-mode-field">
              <span className="text-xs text-slate-400">Selection Mode</span>
              <select
                value={startBotForm.selection_mode}
                onChange={(event) => setStartBotForm((prev) => ({ ...prev, selection_mode: event.target.value }))}
                className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
                data-testid="admin-universe-monitor-start-bot-selection-mode-select"
              >
                <option value="top_n" data-testid="admin-universe-monitor-start-bot-selection-topn">Top N</option>
                <option value="manual" data-testid="admin-universe-monitor-start-bot-selection-manual">Manual</option>
              </select>
            </label>

            <label className="space-y-1" data-testid="admin-universe-monitor-start-bot-topn-field">
              <span className="text-xs text-slate-400">Top N</span>
              <input
                type="number"
                min={1}
                max={150}
                value={startBotForm.top_n}
                onChange={(event) => setStartBotForm((prev) => ({ ...prev, top_n: Number(event.target.value || 20) }))}
                className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
                data-testid="admin-universe-monitor-start-bot-topn-input"
              />
            </label>

            <label className="space-y-1" data-testid="admin-universe-monitor-start-bot-side-filter-field">
              <span className="text-xs text-slate-400">Side Filter</span>
              <select
                value={startBotForm.side_filter}
                onChange={(event) => setStartBotForm((prev) => ({ ...prev, side_filter: event.target.value }))}
                className="h-10 rounded border border-slate-700 bg-black px-2 text-sm"
                data-testid="admin-universe-monitor-start-bot-side-filter-select"
              >
                <option value="all" data-testid="admin-universe-monitor-start-bot-side-filter-all">All</option>
                <option value="long" data-testid="admin-universe-monitor-start-bot-side-filter-long">Long</option>
                <option value="short" data-testid="admin-universe-monitor-start-bot-side-filter-short">Short</option>
                <option value="strong_long" data-testid="admin-universe-monitor-start-bot-side-filter-strong-long">Strong Long</option>
                <option value="strong_short" data-testid="admin-universe-monitor-start-bot-side-filter-strong-short">Strong Short</option>
              </select>
            </label>
          </div>

          {startBotForm.selection_mode === "manual" && (
            <div className="max-h-56 space-y-1 overflow-auto rounded border border-slate-700 p-2" data-testid="admin-universe-monitor-start-bot-manual-list">
              {(scannerEngineRun?.results || []).slice(0, 120).map((item, index) => {
                const checked = (startBotForm.selected_symbols || []).includes(item.symbol);
                return (
                  <label key={`${item.symbol}-${index}`} className="flex items-center gap-2 text-xs" data-testid={`admin-universe-monitor-start-bot-manual-item-${index}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleStartBotSymbol(item.symbol)}
                      data-testid={`admin-universe-monitor-start-bot-manual-item-checkbox-${index}`}
                    />
                    <span data-testid={`admin-universe-monitor-start-bot-manual-item-symbol-${index}`}>{item.symbol}</span>
                    <span className="text-slate-500" data-testid={`admin-universe-monitor-start-bot-manual-item-score-${index}`}>L:{item.long_score} / S:{item.short_score}</span>
                  </label>
                );
              })}
            </div>
          )}

          <DialogFooter data-testid="admin-universe-monitor-start-bot-modal-footer">
            <Button type="button" variant="outline" onClick={() => setStartBotModalOpen(false)} data-testid="admin-universe-monitor-start-bot-cancel-button">Vazgeç</Button>
            <Button type="button" variant="outline" onClick={startScannerJob} disabled={scannerEngineBusy} data-testid="admin-universe-monitor-start-bot-confirm-button">
              Scanner-Job Oluştur
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {statusContract && (
        <section className="rounded border border-emerald-700/40 bg-emerald-950/20 p-3" data-testid="admin-universe-monitor-status-contract-panel">
          <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="admin-universe-monitor-status-contract-title">Unified Status Contract</p>
          <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="admin-universe-monitor-status-contract-grid">
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-scanner-ready">scanner_ready: <span className="font-semibold">{String(Boolean(statusContract.scanner_ready)).toUpperCase()}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-strategy-ready">strategy_ready: <span className="font-semibold">{String(Boolean(statusContract.strategy_ready)).toUpperCase()}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-risk-ready">risk_ready: <span className="font-semibold">{String(Boolean(statusContract.risk_ready)).toUpperCase()}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-execution-ready">execution_ready: <span className="font-semibold">{String(Boolean(statusContract.execution_ready)).toUpperCase()}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-symbols-ready">symbols_ready: <span className="font-semibold">{String(Boolean(statusContract.symbols_ready)).toUpperCase()}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-exchange-ready">exchange_ready: <span className="font-semibold">{String(Boolean(statusContract.exchange_ready)).toUpperCase()}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-bot-status">bot_status: <span className="font-semibold">{statusContract.bot_status || "-"}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-health">health: <span className="font-semibold">{statusContract.health || "-"}</span></p>
            <p className="text-xs" data-testid="admin-universe-monitor-status-contract-latest-run">latest_scanner_run_at: <span className="font-semibold">{statusContract.latest_scanner_run_at ? new Date(statusContract.latest_scanner_run_at).toLocaleString() : "-"}</span></p>
          </div>
          <div className="mt-2" data-testid="admin-universe-monitor-status-contract-blocking-reasons">
            <p className="text-xs text-emerald-100" data-testid="admin-universe-monitor-status-contract-blocking-reasons-title">blocking_reasons</p>
            {(statusContract.blocking_reasons || []).length === 0 ? (
              <p className="text-xs text-emerald-300" data-testid="admin-universe-monitor-status-contract-blocking-reasons-empty">Blokaj yok.</p>
            ) : (
              <ul className="mt-1 space-y-1" data-testid="admin-universe-monitor-status-contract-blocking-reasons-list">
                {(statusContract.blocking_reasons || []).map((reason, index) => (
                  <li key={`${reason.code || "reason"}-${index}`} className="text-xs" data-testid={`admin-universe-monitor-status-contract-blocking-reason-${index}`}>
                    <span className="font-semibold">{reason.code || "UNKNOWN"}</span>: {reason.message || "-"}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      <div className="grid gap-3 md:grid-cols-5 xl:grid-cols-10" data-testid="admin-universe-monitor-metrics-grid">
        {[
          ["total exchange symbols", summary?.total_exchange_symbols, "admin-universe-monitor-total-exchange"],
          ["active scan symbols", summary?.active_scan_symbols, "admin-universe-monitor-active-scan"],
          ["symbols evaluated this cycle", summary?.symbols_evaluated_this_cycle, "admin-universe-monitor-evaluated-this-cycle"],
          ["average cycle latency (ms)", summary?.average_cycle_latency_ms, "admin-universe-monitor-cycle-latency"],
          ["queue depth", summary?.queue_depth, "admin-universe-monitor-queue-depth"],
          ["blocked by permission", summary?.blocked_by_permission, "admin-universe-monitor-blocked-permission"],
          ["blocked by risk", summary?.blocked_by_risk, "admin-universe-monitor-blocked-risk"],
          ["blocked by liquidity", summary?.blocked_by_liquidity, "admin-universe-monitor-blocked-liquidity"],
          ["stale blocks", summary?.stale_blocks, "admin-universe-monitor-stale-blocks"],
          ["worker utilization", summary?.worker_utilization, "admin-universe-monitor-worker-utilization"],
          ["fallback active", String(summary?.fallback_active ?? false), "admin-universe-monitor-fallback-active"],
          ["fallback healthy streak", summary?.fallback_healthy_streak, "admin-universe-monitor-fallback-healthy-streak"],
        ].map(([label, value, key]) => (
          <article key={key} className="rounded border border-slate-700 bg-slate-900 p-3" data-testid={`${key}-card`}>
            <p className="text-xs text-slate-400">{label}</p>
            <p className="text-xl font-bold" data-testid={`${key}-value`}>{value ?? "-"}</p>
          </article>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="admin-runtime-risk-overview-grid">
        {[
          ["portfolio_exposure", runtimeSummary?.risk_overview?.portfolio_exposure, "admin-runtime-risk-portfolio-exposure"],
          ["symbol_exposure_count", (runtimeSummary?.risk_overview?.symbol_exposure || []).length, "admin-runtime-risk-symbol-exposure-count"],
          ["cluster_exposure_count", (runtimeSummary?.risk_overview?.cluster_exposure || []).length, "admin-runtime-risk-cluster-exposure-count"],
          ["daily_loss_pct", runtimeSummary?.risk_overview?.daily_loss?.daily_loss_pct, "admin-runtime-risk-daily-loss-pct"],
          ["execution_quality_score", runtimeSummary?.risk_overview?.execution_quality_score, "admin-runtime-risk-execution-quality-score"],
          ["fallback_state", String(runtimeSummary?.risk_overview?.fallback_state?.active ?? false), "admin-runtime-risk-fallback-state"],
          ["queue_depth", runtimeSummary?.risk_overview?.queue_depth, "admin-runtime-risk-queue-depth"],
          ["stale_reject_count", runtimeSummary?.risk_overview?.stale_reject_count, "admin-runtime-risk-stale-reject-count"],
          ["spread_reject_count", runtimeSummary?.risk_overview?.spread_reject_count, "admin-runtime-risk-spread-reject-count"],
          ["cooldown_state", Object.keys(runtimeSummary?.risk_overview?.cooldown_state || {}).length, "admin-runtime-risk-cooldown-state"],
          ["kill_switch_state", String(runtimeSummary?.risk_overview?.kill_switch_state?.pipeline_kill_switch_active ?? false), "admin-runtime-risk-kill-switch-state"],
        ].map(([label, value, key]) => (
          <article key={key} className="rounded border border-emerald-800/40 bg-emerald-950/20 p-3" data-testid={`${key}-card`}>
            <p className="text-xs uppercase tracking-widest text-emerald-200">{label}</p>
            <p className="mt-1 text-lg font-semibold" data-testid={`${key}-value`}>{value ?? "-"}</p>
          </article>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-runtime-observability-trend-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-latency-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">execution latency trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-latency-trend-list">
            {(runtimeSummary?.observability_trends?.execution_latency_trend || []).slice(-8).map((item, idx) => (
              <p key={`latency-${idx}`} data-testid={`admin-runtime-observability-latency-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-veto-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">risk veto rate trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-veto-trend-list">
            {(runtimeSummary?.observability_trends?.risk_veto_rate_trend || []).slice(-8).map((item, idx) => (
              <p key={`veto-${idx}`} data-testid={`admin-runtime-observability-veto-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-scanner-latency-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">scanner cycle latency trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-scanner-latency-trend-list">
            {(runtimeSummary?.observability_trends?.scanner_cycle_latency_trend || []).slice(-8).map((item, idx) => (
              <p key={`scanner-latency-${idx}`} data-testid={`admin-runtime-observability-scanner-latency-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-runtime-observability-fallback-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">fallback activation trend</p>
          <div className="mt-2 space-y-1 text-xs" data-testid="admin-runtime-observability-fallback-trend-list">
            {(runtimeSummary?.observability_trends?.fallback_activation_rate_trend || []).slice(-8).map((item, idx) => (
              <p key={`fallback-${idx}`} data-testid={`admin-runtime-observability-fallback-trend-item-${idx}`}>{item.ts} · {item.value}</p>
            ))}
          </div>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3 md:col-span-2" data-testid="admin-runtime-observability-pnl-trend-card">
          <p className="text-xs uppercase tracking-widest text-slate-300">PnL trend</p>
          <div className="mt-2 grid gap-1 text-xs md:grid-cols-2" data-testid="admin-runtime-observability-pnl-trend-list">
            {(runtimeSummary?.risk_overview?.pnl_trend || []).slice(-12).map((item, idx) => (
              <p key={`pnl-${idx}`} data-testid={`admin-runtime-observability-pnl-trend-item-${idx}`}>
                {item.closed_at} · {item.symbol} · pnl={item.realized_pnl}
              </p>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-universe-monitor-rollout-panels">
        <article className="rounded border border-emerald-800/50 bg-emerald-950/20 p-3" data-testid="admin-universe-monitor-rollout-status-panel">
          <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="admin-universe-monitor-rollout-status-title">Rollout Orchestrator</p>
          <p className="mt-2 text-xs" data-testid="admin-universe-monitor-rollout-current-stage">Current Stage: {rollout?.current_stage || "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-rollout-recommended-stage">Recommended Stage: {rollout?.recommended_stage || "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-rollout-approval-required">Admin Approval Required: {String(rollout?.requires_admin_approval ?? true)}</p>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="admin-universe-monitor-rollout-actions">
            <Button type="button" variant="outline" onClick={requestRolloutRecommendation} data-testid="admin-universe-monitor-rollout-recommend-button">
              KPI Recommendation Üret
            </Button>
            <Button type="button" variant="outline" onClick={approveRolloutRecommendation} data-testid="admin-universe-monitor-rollout-approve-button">
              Recommend Stage'i Onayla
            </Button>
          </div>
        </article>

        <article className="rounded border border-cyan-800/50 bg-cyan-950/20 p-3" data-testid="admin-universe-monitor-trend-summary-panel">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="admin-universe-monitor-trend-summary-title">Trend Summary ({windowSize})</p>
          <p className="mt-2 text-xs" data-testid="admin-universe-monitor-trend-summary-latency">Latest Latency: {latestTrendPoint?.average_cycle_latency_ms ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-trend-summary-stale">Latest Stale Blocks: {latestTrendPoint?.stale_blocks ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-trend-summary-dropped">Latest Dropped: {latestTrendPoint?.dropped_evaluations ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-trend-summary-points">Points: {(trend?.points || []).length}</p>
        </article>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-universe-monitor-slow-panels">
        <article className="rounded border border-slate-800 bg-slate-900 p-3" data-testid="admin-universe-monitor-top-slow-strategies-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-universe-monitor-top-slow-strategies-title">Top Slow Strategies</p>
          <div className="mt-2 space-y-1" data-testid="admin-universe-monitor-top-slow-strategies-list">
            {(summary?.top_slow_strategies || []).slice(0, 10).map((item, idx) => (
              <p key={`slow-strategy-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-top-slow-strategy-${idx}`}>
                {item.strategy_id} · avg={item.avg_ms}ms · calls={item.calls}
              </p>
            ))}
            {(summary?.top_slow_strategies || []).length === 0 && <p className="text-xs text-slate-500" data-testid="admin-universe-monitor-top-slow-strategies-empty">Veri yok.</p>}
          </div>
        </article>

        <article className="rounded border border-slate-800 bg-slate-900 p-3" data-testid="admin-universe-monitor-top-slow-symbols-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-universe-monitor-top-slow-symbols-title">Top Slow Symbols</p>
          <div className="mt-2 space-y-1" data-testid="admin-universe-monitor-top-slow-symbols-list">
            {(summary?.top_slow_symbols || []).slice(0, 10).map((item, idx) => (
              <p key={`slow-symbol-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-top-slow-symbol-${idx}`}>
                {item.symbol} · {item.elapsed_ms}ms
              </p>
            ))}
            {(summary?.top_slow_symbols || []).length === 0 && <p className="text-xs text-slate-500" data-testid="admin-universe-monitor-top-slow-symbols-empty">Veri yok.</p>}
          </div>
        </article>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-universe-monitor-breakdown-panels">
        <article className="rounded border border-fuchsia-800/50 bg-fuchsia-950/20 p-3" data-testid="admin-universe-monitor-user-breakdown-panel">
          <p className="text-xs uppercase tracking-widest text-fuchsia-300" data-testid="admin-universe-monitor-user-breakdown-title">User/Profile Breakdown</p>
          <div className="mt-2 max-h-52 space-y-1 overflow-auto" data-testid="admin-universe-monitor-user-breakdown-list">
            {(breakdown?.user_breakdown || []).slice(0, 20).map((item, idx) => (
              <p key={`user-breakdown-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-user-breakdown-item-${idx}`}>
                {item.user_id} · runs={item.runs} · eval={item.symbols_evaluated} · false_block={item.false_block_rate} · missed={item.missed_update_rate}
              </p>
            ))}
          </div>
        </article>

        <article className="rounded border border-indigo-800/50 bg-indigo-950/20 p-3" data-testid="admin-universe-monitor-regime-breakdown-panel">
          <p className="text-xs uppercase tracking-widest text-indigo-300" data-testid="admin-universe-monitor-regime-breakdown-title">Regime Breakdown</p>
          <div className="mt-2 max-h-52 space-y-1 overflow-auto" data-testid="admin-universe-monitor-regime-breakdown-list">
            {(breakdown?.regime_breakdown || []).slice(0, 20).map((item, idx) => (
              <p key={`regime-breakdown-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-regime-breakdown-item-${idx}`}>
                {item.regime} · count={item.count}
              </p>
            ))}
          </div>
        </article>
      </div>

      <article className="rounded border border-rose-800/50 bg-rose-950/20 p-3" data-testid="admin-universe-monitor-freshness-heatmap-widget">
        <p className="text-xs uppercase tracking-widest text-rose-300" data-testid="admin-universe-monitor-freshness-heatmap-title">Freshness SLA Breach Heatmap (Embedded)</p>
        <div className="mt-2 max-h-56 space-y-1 overflow-auto" data-testid="admin-universe-monitor-freshness-heatmap-list">
          {(heatmap?.items || []).slice(0, 40).map((item, idx) => (
            <p key={`heatmap-${idx}`} className="text-xs" data-testid={`admin-universe-monitor-freshness-heatmap-item-${idx}`}>
              {item.symbol}:{item.timeframe} · stale_rate={item.stale_rate} · stale={item.stale} / total={item.total} · avg_age={item.avg_snapshot_age}
            </p>
          ))}
          {(heatmap?.items || []).length === 0 && <p className="text-xs text-rose-200" data-testid="admin-universe-monitor-freshness-heatmap-empty">Heatmap verisi yok.</p>}
        </div>
      </article>

      <article className="rounded border border-amber-800/50 bg-amber-950/20 p-3" data-testid="admin-universe-monitor-fallback-events-panel">
        <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="admin-universe-monitor-fallback-events-title">Fallback Timeline</p>
        <div className="mt-2 max-h-64 space-y-1 overflow-auto" data-testid="admin-universe-monitor-fallback-events-list">
          {fallbackEvents.map((item, idx) => (
            <div key={item.id || idx} className="rounded border border-amber-700/50 p-2" data-testid={`admin-universe-monitor-fallback-event-${idx}`}>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-timestamp-${idx}`}>timestamp: {String(item.timestamp || "-")}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-trigger-metric-${idx}`}>trigger_metric: {item.trigger_metric || "-"}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-threshold-breach-${idx}`}>threshold_breach: {JSON.stringify(item.threshold_breach || {})}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-exit-reason-${idx}`}>exit_reason: {item.exit_reason || "-"}</p>
              <p className="text-xs" data-testid={`admin-universe-monitor-fallback-event-cycle-snapshot-${idx}`}>cycle_snapshot: {JSON.stringify(item.cycle_snapshot || {})}</p>
            </div>
          ))}
          {fallbackEvents.length === 0 && <p className="text-xs text-amber-200" data-testid="admin-universe-monitor-fallback-events-empty">Fallback event kaydı yok.</p>}
        </div>
      </article>

      {canShowDebug && (
        <div className="grid gap-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-universe-monitor-debug-panel">
          <p className="text-xs uppercase tracking-widest text-slate-400" data-testid="admin-universe-monitor-debug-title">Debug Effective Universe</p>
          <p className="text-xs" data-testid="admin-universe-monitor-debug-market-count">market_symbols_count: {debugPayload?.market_symbols_count ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-debug-after-blacklist">after_blacklist: {debugPayload?.after_blacklist ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-debug-after-scanner">after_scanner_mode: {debugPayload?.after_scanner_mode ?? "-"}</p>
          <p className="text-xs" data-testid="admin-universe-monitor-debug-after-liquidity">after_liquidity_filter: {debugPayload?.after_liquidity_filter ?? "-"}</p>
          <div className="max-h-52 overflow-auto rounded border border-slate-700 p-2" data-testid="admin-universe-monitor-debug-final-symbols-wrapper">
            <p className="text-xs text-slate-400" data-testid="admin-universe-monitor-debug-final-symbols-label">final_symbols</p>
            <p className="text-xs font-mono" data-testid="admin-universe-monitor-debug-final-symbols-value">{(debugPayload?.final_symbols || []).join(", ") || "-"}</p>
          </div>
        </div>
      )}

      {loading && <p className="text-xs text-slate-400" data-testid="admin-universe-monitor-loading">Yükleniyor...</p>}
    </section>
  );
};
