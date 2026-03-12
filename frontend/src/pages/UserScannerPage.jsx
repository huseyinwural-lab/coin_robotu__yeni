import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserScannerPage = () => {
  const [mode, setMode] = useState("ASSISTED");
  const [scannerResults, setScannerResults] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);

  const load = async () => {
    const [modeRes, resultsRes] = await Promise.all([
      apiClient.get("/user/signal-mode"),
      apiClient.get("/user/scanner/results", { params: { limit: 80 } }),
    ]);
    setMode(modeRes.data.mode || "ASSISTED");
    setScannerResults(resultsRes.data || []);
  };

  useEffect(() => {
    load();
  }, []);

  const runScanner = async () => {
    setIsRunning(true);
    try {
      await apiClient.put("/user/signal-mode", { mode });
      const { data } = await apiClient.post("/user/scanner/run", {
        mode,
        max_results: 25,
      });
      setLastRun(data);
      await load();
      toast.success("Scanner çalıştırıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Scanner çalıştırılamadı");
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="user-scanner-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-scanner-title">Scanner</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-scanner-description">
          Kullanıcı bazlı tarama sonuçları ve signal queue üretimi.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-slate-800 bg-slate-900 p-4" data-testid="user-scanner-controls">
        <label className="text-xs uppercase tracking-widest text-slate-500" htmlFor="user-scanner-mode-select" data-testid="user-scanner-mode-label">
          Signal Mode
        </label>
        <select
          id="user-scanner-mode-select"
          className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          value={mode}
          onChange={(event) => setMode(event.target.value)}
          data-testid="user-scanner-mode-select"
        >
          <option value="ASSISTED">ASSISTED</option>
          <option value="AUTO">AUTO</option>
          <option value="MANUAL">MANUAL</option>
        </select>
        <Button onClick={runScanner} disabled={isRunning} data-testid="user-scanner-run-button">
          {isRunning ? "Çalışıyor..." : "Scanner Run"}
        </Button>
        <Button variant="outline" onClick={load} data-testid="user-scanner-refresh-button">Yenile</Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="user-scanner-run-summary-grid">
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-mode-card">
          <p className="text-xs text-slate-500" data-testid="user-scanner-summary-mode-label">Aktif Mode</p>
          <p className="text-lg font-semibold text-orange-400" data-testid="user-scanner-summary-mode-value">{mode}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-result-count-card">
          <p className="text-xs text-slate-500" data-testid="user-scanner-summary-result-count-label">Sonuç</p>
          <p className="text-lg font-semibold" data-testid="user-scanner-summary-result-count-value">{lastRun?.result_count ?? scannerResults.length}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-actionable-count-card">
          <p className="text-xs text-slate-500" data-testid="user-scanner-summary-actionable-count-label">Actionable</p>
          <p className="text-lg font-semibold" data-testid="user-scanner-summary-actionable-count-value">{lastRun?.actionable_count ?? "-"}</p>
        </div>
        <div className="border border-slate-800 bg-slate-900 p-3" data-testid="user-scanner-summary-pending-count-card">
          <p className="text-xs text-slate-500" data-testid="user-scanner-summary-pending-count-label">Pending Queue</p>
          <p className="text-lg font-semibold" data-testid="user-scanner-summary-pending-count-value">{lastRun?.pending_total ?? "-"}</p>
        </div>
      </div>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="user-scanner-results-table-wrapper">
        <table className="min-w-full text-sm" data-testid="user-scanner-results-table">
          <thead className="bg-slate-800 text-left" data-testid="user-scanner-results-table-head">
            <tr>
              <th className="px-3 py-2" data-testid="user-scanner-results-head-symbol">Symbol</th>
              <th className="px-3 py-2" data-testid="user-scanner-results-head-signal">Signal</th>
              <th className="px-3 py-2" data-testid="user-scanner-results-head-confidence">Confidence</th>
              <th className="px-3 py-2" data-testid="user-scanner-results-head-score">Score</th>
              <th className="px-3 py-2" data-testid="user-scanner-results-head-strategy">Strategy</th>
            </tr>
          </thead>
          <tbody data-testid="user-scanner-results-table-body">
            {scannerResults.map((item) => (
              <tr key={item.id} className="border-t border-slate-800" data-testid="user-scanner-results-table-row">
                <td className="px-3 py-2" data-testid="user-scanner-results-row-symbol">{item.symbol}</td>
                <td className="px-3 py-2" data-testid="user-scanner-results-row-signal">{item.signal}</td>
                <td className="px-3 py-2" data-testid="user-scanner-results-row-confidence">{item.confidence}</td>
                <td className="px-3 py-2" data-testid="user-scanner-results-row-score">{item.signal_score}</td>
                <td className="px-3 py-2" data-testid="user-scanner-results-row-strategy">{item.strategy_code}</td>
              </tr>
            ))}
            {scannerResults.length === 0 && (
              <tr data-testid="user-scanner-results-empty-row">
                <td colSpan={5} className="px-3 py-8 text-center text-slate-400" data-testid="user-scanner-results-empty-state">
                  Henüz scanner sonucu yok.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};