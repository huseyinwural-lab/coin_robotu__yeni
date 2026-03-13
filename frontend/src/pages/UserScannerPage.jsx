import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { saveExecutionContext } from "@/lib/userFlowContext";

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

export const UserScannerPage = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState("ASSISTED");
  const [overview, setOverview] = useState(null);
  const [scannerResults, setScannerResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);

  const load = async () => {
    setIsLoading(true);
    const [modeRes, overviewRes, resultsRes] = await Promise.all([
      apiClient.get("/user/signal-mode"),
      apiClient.get("/user/scanner"),
      apiClient.get("/user/scanner/results", { params: { limit: 80 } }),
    ]);
    setMode(modeRes.data.mode || "ASSISTED");
    setOverview(overviewRes.data);
    setScannerResults(resultsRes.data || []);
    setIsLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const runScanner = async () => {
    setIsRunning(true);
    try {
      await apiClient.put("/user/signal-mode", { mode });
      await apiClient.post("/user/scanner/run", { mode, max_results: 25 });
      await load();
      toast.success("Scanner çalıştırıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Scanner çalıştırılamadı");
    } finally {
      setIsRunning(false);
    }
  };

  const runPreset = async (preset) => {
    setIsRunning(true);
    try {
      await apiClient.put("/user/signal-mode", { mode: preset.mode });
      setMode(preset.mode);
      await apiClient.post("/user/scanner/run", { mode: preset.mode, max_results: preset.maxResults });
      await load();
      toast.success(`Preset çalıştı: ${preset.label}`);
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
    });
    navigate(`/user/execute?source=scanner&symbol=${encodeURIComponent(item.symbol)}&side=${encodeURIComponent(side)}&market_type=${encodeURIComponent(marketType)}&preset=spot_basic`);
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
  });

  const previewIntentFromScanner = async (item) => {
    try {
      const { data } = await apiClient.post("/user/execution/intent/preview", buildIntentPayload(item));
      toast.success(`Preview: ${data.validation_status}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preview başarısız");
    }
  };

  const queueIntentFromScanner = async (item) => {
    try {
      const { data } = await apiClient.post("/user/execution/intent/preview", buildIntentPayload(item));
      if (data.validation_status !== "valid") {
        toast.error("Policy preview reddetti");
        return;
      }
      await apiClient.post("/user/execution/intent/submit", {
        intent_token: data.intent_token,
        preview_hash: data.preview_hash,
      });
      toast.success("Queue Assisted Order gönderildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Queue başarısız");
    }
  };

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-scanner-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-scanner-title">Scanner</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-scanner-description">Responsive scanner + compact table + mobile card yapısı.</p>
      </header>

      <div className="col-span-12 flex flex-wrap items-center gap-3 border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-controls">
        <label className="text-xs uppercase tracking-widest text-slate-500" htmlFor="user-scanner-mode-select" data-testid="user-scanner-mode-label">Signal Mode</label>
        <select
          id="user-scanner-mode-select"
          className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={mode}
          onChange={(event) => setMode(event.target.value)}
          data-testid="user-scanner-mode-select"
          aria-label="Signal modu"
        >
          <option value="ASSISTED">ASSISTED</option>
          <option value="AUTO">AUTO</option>
          <option value="MANUAL">MANUAL</option>
        </select>
        <Button onClick={runScanner} disabled={isRunning} data-testid="user-scanner-run-button" aria-label="Scanner çalıştır">
          {isRunning ? "Çalışıyor..." : "Scanner Run"}
        </Button>
        <Button variant="outline" onClick={load} data-testid="user-scanner-refresh-button" aria-label="Scanner verisini yenile">Yenile</Button>
        <Button variant="outline" onClick={() => setCompactMode((previous) => !previous)} data-testid="user-scanner-compact-mode-toggle" aria-label="Compact mode aç/kapat">
          {compactMode ? "Compact: ON" : "Compact: OFF"}
        </Button>
      </div>

      <section className="col-span-12 grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="user-scanner-quick-preset-section">
        {scannerQuickPresets.map((preset) => (
          <article key={preset.id} className="rounded border border-slate-700 bg-slate-950 p-3" data-testid={`user-scanner-quick-preset-card-${preset.id}`}>
            <p className="text-sm font-semibold text-slate-100" data-testid={`user-scanner-quick-preset-title-${preset.id}`}>{preset.label}</p>
            <p className="mt-1 text-xs text-slate-400" data-testid={`user-scanner-quick-preset-note-${preset.id}`}>{preset.note}</p>
            <Button className="mt-3" variant="outline" onClick={() => runPreset(preset)} disabled={isRunning} data-testid={`user-scanner-quick-preset-run-button-${preset.id}`}>
              {isRunning ? "Çalışıyor..." : "Preset Çalıştır"}
            </Button>
          </article>
        ))}
      </section>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-scanner-run-summary-grid">
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-mode-card"><p className="text-xs text-slate-500">Aktif Mode</p><p className="text-lg font-semibold text-orange-400" data-testid="user-scanner-summary-mode-value">{overview?.mode ?? mode}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-result-count-card"><p className="text-xs text-slate-500">Toplam Sonuç</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-result-count-value">{overview?.total_results ?? scannerResults.length}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-actionable-count-card"><p className="text-xs text-slate-500">Son Run ID</p><p className="text-sm font-semibold" data-testid="user-scanner-summary-actionable-count-value">{overview?.latest_run_id ?? "-"}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-pending-count-card"><p className="text-xs text-slate-500">Pending Queue</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-pending-count-value">{overview?.pending_signals ?? "-"}</p></div>
      </div>

      <div className="col-span-12 grid gap-3 md:hidden" data-testid="user-scanner-mobile-cards">
        {scannerResults.map((item) => (
          <article key={item.id} className="rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-mobile-card">
            <p className="text-sm font-semibold" data-testid="user-scanner-mobile-symbol">{item.symbol}</p>
            <p className="text-xs text-slate-500" data-testid="user-scanner-mobile-signal">Signal: {item.signal}</p>
            <p className="text-xs text-slate-500" data-testid="user-scanner-mobile-confidence">Confidence: {item.confidence}</p>
            <div className="mt-2 flex gap-2" data-testid="user-scanner-mobile-actions">
              <Button variant="outline" onClick={() => openExecuteFromScanner(item)} data-testid="user-scanner-open-execute-button">Open in Execute</Button>
              <Button variant="outline" onClick={() => previewIntentFromScanner(item)} data-testid="user-scanner-preview-intent-button">Preview Intent</Button>
              <Button variant="outline" onClick={() => queueIntentFromScanner(item)} data-testid="user-scanner-queue-intent-button">Queue Order</Button>
            </div>
          </article>
        ))}
      </div>

      <div className="col-span-12 hidden overflow-x-auto border border-slate-800 bg-slate-900 md:block" data-testid="user-scanner-results-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-scanner-results-table" aria-label="Scanner sonuç tablosu">
          <thead className="bg-slate-800 text-left" data-testid="user-scanner-results-table-head">
            <tr>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Symbol</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Signal</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Confidence</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Score</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Strategy</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Actions</th>
            </tr>
          </thead>
          <tbody data-testid="user-scanner-results-table-body">
            {scannerResults.map((item) => (
              <tr key={item.id} className="border-t border-slate-800" data-testid="user-scanner-results-table-row">
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{item.symbol}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{item.signal}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{item.confidence}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{item.signal_score}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>{item.strategy_code}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"}>
                  <div className="flex gap-2" data-testid="user-scanner-table-actions">
                    <Button variant="outline" onClick={() => openExecuteFromScanner(item)} data-testid="user-scanner-table-open-execute-button">Open in Execute</Button>
                    <Button variant="outline" onClick={() => previewIntentFromScanner(item)} data-testid="user-scanner-table-preview-intent-button">Preview Intent</Button>
                    <Button variant="outline" onClick={() => queueIntentFromScanner(item)} data-testid="user-scanner-table-queue-intent-button">Queue Order</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};