import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminUniverseMonitorPage = () => {
  const [mode, setMode] = useState("ALL_MARKET_SYMBOLS");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [debugPayload, setDebugPayload] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [{ data: summaryData }, { data: debugData }] = await Promise.all([
        apiClient.get("/admin/universe-monitor", { params: { market_type: "spot", scanner_mode: mode, top_n: 300 } }),
        apiClient.get("/debug/effective-universe", { params: { market_type: "spot", scanner_mode: mode, top_n: 300 } }),
      ]);
      setSummary(summaryData || null);
      setDebugPayload(debugData || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Universe monitor verisi alınamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [mode]);

  return (
    <section className="space-y-4" data-testid="admin-universe-monitor-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="admin-universe-monitor-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="admin-universe-monitor-title">Universe Monitor</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-universe-monitor-description">
          Exchange evreni, aktif scan kapsamı ve blok dağılımını tek panelde izleyin.
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
        <Button type="button" variant="outline" onClick={load} data-testid="admin-universe-monitor-refresh-button">
          Yenile
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-5" data-testid="admin-universe-monitor-metrics-grid">
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-universe-monitor-total-exchange-card">
          <p className="text-xs text-slate-400">total exchange symbols</p>
          <p className="text-xl font-bold" data-testid="admin-universe-monitor-total-exchange-value">{summary?.total_exchange_symbols ?? "-"}</p>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-universe-monitor-active-scan-card">
          <p className="text-xs text-slate-400">active scan symbols</p>
          <p className="text-xl font-bold" data-testid="admin-universe-monitor-active-scan-value">{summary?.active_scan_symbols ?? "-"}</p>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-universe-monitor-blocked-permission-card">
          <p className="text-xs text-slate-400">blocked by permission</p>
          <p className="text-xl font-bold" data-testid="admin-universe-monitor-blocked-permission-value">{summary?.blocked_by_permission ?? "-"}</p>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-universe-monitor-blocked-risk-card">
          <p className="text-xs text-slate-400">blocked by risk</p>
          <p className="text-xl font-bold" data-testid="admin-universe-monitor-blocked-risk-value">{summary?.blocked_by_risk ?? "-"}</p>
        </article>
        <article className="rounded border border-slate-700 bg-slate-900 p-3" data-testid="admin-universe-monitor-blocked-liquidity-card">
          <p className="text-xs text-slate-400">blocked by liquidity</p>
          <p className="text-xl font-bold" data-testid="admin-universe-monitor-blocked-liquidity-value">{summary?.blocked_by_liquidity ?? "-"}</p>
        </article>
      </div>

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

      {loading && <p className="text-xs text-slate-400" data-testid="admin-universe-monitor-loading">Yükleniyor...</p>}
    </section>
  );
};
