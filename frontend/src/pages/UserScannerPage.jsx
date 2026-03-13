import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
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

const AUTO_SCAN_INTERVAL_SECONDS = 180;

export const UserScannerPage = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState("ASSISTED");
  const [overview, setOverview] = useState(null);
  const [scannerResults, setScannerResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);
  const [symbolSource, setSymbolSource] = useState("crypto");
  const [symbolMode, setSymbolMode] = useState("top_active_50");
  const [selectedSymbols, setSelectedSymbols] = useState([]);
  const [automationConfig, setAutomationConfig] = useState(null);
  const [isSavingAutomation, setIsSavingAutomation] = useState(false);

  const activeModeLabel = String(overview?.mode || mode || "ASSISTED").toUpperCase();
  const executionPathLabel =
    activeModeLabel === "AUTO"
      ? "BOT_AUTO_ACTIVE"
      : activeModeLabel === "ASSISTED"
        ? "SEMI_AUTO_ACTIVE"
        : "MANUAL_REVIEW_FLOW";

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

  const saveAutomationConfig = async ({ autoEnabled, withToast = true } = {}) => {
    const nextEnabled = typeof autoEnabled === "boolean" ? autoEnabled : Boolean(automationConfig?.auto_enabled ?? true);
    setIsSavingAutomation(true);
    try {
      const { data } = await apiClient.put("/user/scanner/automation", {
        auto_enabled: nextEnabled,
        interval_seconds: AUTO_SCAN_INTERVAL_SECONDS,
        max_results: 25,
        symbol_source: symbolSource,
        symbol_selection_mode: symbolMode,
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

  const load = async ({ hydrateSelection = false } = {}) => {
    setIsLoading(true);
    const [modeRes, overviewRes, resultsRes, automationRes] = await Promise.all([
      apiClient.get("/user/signal-mode"),
      apiClient.get("/user/scanner"),
      apiClient.get("/user/scanner/results", { params: { limit: 80 } }),
      apiClient.get("/user/scanner/automation"),
    ]);
    setMode(modeRes.data.mode || "ASSISTED");
    setOverview(overviewRes.data);
    setScannerResults(resultsRes.data || []);
    const automation = automationRes?.data || null;
    setAutomationConfig(automation);
    if (hydrateSelection && automation) {
      setSymbolSource(automation.symbol_source || "crypto");
      setSymbolMode(automation.symbol_selection_mode || "top_active_50");
      setSelectedSymbols(Array.isArray(automation.selected_symbols) ? automation.selected_symbols : []);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    load({ hydrateSelection: true });
  }, []);

  const runScanner = async () => {
    setIsRunning(true);
    try {
      if (automationConfig?.auto_enabled) {
        await saveAutomationConfig({ autoEnabled: true, withToast: false });
      }
      await apiClient.put("/user/signal-mode", { mode });
      const { data } = await apiClient.post("/user/scanner/run", {
        mode,
        max_results: 25,
        symbol_source: symbolSource,
        symbol_selection_mode: symbolMode,
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
    setIsRunning(true);
    try {
      await apiClient.put("/user/signal-mode", { mode: preset.mode });
      setMode(preset.mode);
      const { data } = await apiClient.post("/user/scanner/run", {
        mode: preset.mode,
        max_results: preset.maxResults,
        symbol_source: symbolSource,
        symbol_selection_mode: symbolMode,
        selected_symbols: selectedSymbols,
      });
      await load();
      if ((data?.warnings || []).length > 0) {
        toast.warning((data.warnings || []).join(","));
      }
      toast.success(`Preset çalıştı: ${preset.label}`);
      if (automationConfig?.auto_enabled) {
        await saveAutomationConfig({ autoEnabled: true, withToast: false });
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

      <section className="col-span-12 rounded border border-cyan-800/50 bg-cyan-950/20 p-4" data-testid="user-scanner-active-mode-indicator-card">
        <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="user-scanner-active-mode-indicator-title">Scanner Active Mode Indicator</p>
        <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="user-scanner-active-mode-indicator-grid">
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-mode">Active Mode: {activeModeLabel}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-path">Execution Path: {executionPathLabel}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-source">Source: {symbolSource.toUpperCase()}</p>
          <p className="text-sm" data-testid="user-scanner-active-mode-indicator-symbol-mode">Symbol Mode: {symbolMode}</p>
        </div>
      </section>

      <section className="col-span-12 rounded border border-emerald-800/50 bg-emerald-950/20 p-4" data-testid="user-scanner-automation-card">
        <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="user-scanner-automation-title">Scanner Otomasyon (3 Dakika)</p>
        <div className="mt-2 grid gap-2 md:grid-cols-4" data-testid="user-scanner-automation-grid">
          <p className="text-sm" data-testid="user-scanner-automation-status">Durum: {automationConfig?.auto_enabled ? "AKTİF" : "PASİF"}</p>
          <p className="text-sm" data-testid="user-scanner-automation-interval">Periyot: 3 dakika</p>
          <p className="text-sm" data-testid="user-scanner-automation-last-run">Son Çalışma: {formatDateLabel(automationConfig?.last_run_at)}</p>
          <p className="text-sm" data-testid="user-scanner-automation-next-run">Sonraki Çalışma: {formatDateLabel(automationConfig?.next_run_at)}</p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="user-scanner-automation-actions">
          <Button
            type="button"
            variant="outline"
            onClick={() => saveAutomationConfig({ autoEnabled: !(automationConfig?.auto_enabled ?? true) })}
            disabled={isSavingAutomation}
            data-testid="user-scanner-automation-toggle-button"
          >
            {isSavingAutomation ? "Kaydediliyor..." : automationConfig?.auto_enabled ? "Otomatik Tetiklemeyi Kapat" : "Otomatik Tetiklemeyi Aç"}
          </Button>
          <Button
            type="button"
            onClick={() => saveAutomationConfig({ autoEnabled: true })}
            disabled={isSavingAutomation}
            data-testid="user-scanner-automation-save-selection-button"
          >
            {isSavingAutomation ? "Kaydediliyor..." : "Seçimi Kaydet (Otomasyona)"}
          </Button>
        </div>
        <p className="mt-2 text-xs text-emerald-200" data-testid="user-scanner-automation-hint">
          Kaynak + seçim modu + seçili semboller bir kez kaydedilir; otomatik scanner her 3 dakikada bu kayıtlı seçimle çalışır.
        </p>
      </section>

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

      <div className="col-span-12" data-testid="user-scanner-symbol-selector-wrapper">
        <SymbolSelectorPanel
          testIdPrefix="user-scanner-symbol-selector"
          exchange="binance"
          marketType="spot"
          source={symbolSource}
          onSourceChange={setSymbolSource}
          mode={symbolMode}
          onModeChange={setSymbolMode}
          selectedSymbols={selectedSymbols}
          onSelectedSymbolsChange={setSelectedSymbols}
          multi
        />
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
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-selected-symbol-count-card"><p className="text-xs text-slate-500">Seçili Sembol</p><p className="text-lg font-semibold" data-testid="user-scanner-summary-selected-symbol-count-value">{selectedSymbols.length}</p></div>
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