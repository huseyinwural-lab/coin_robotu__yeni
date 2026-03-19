import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const UserReportsPage = () => {
  const [report, setReport] = useState(null);
  const [previousReport, setPreviousReport] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [weekOverride, setWeekOverride] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [compareEnabled, setCompareEnabled] = useState(true);

  const isIsoDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""));

  const load = useCallback(async (requestedWeek = "") => {
    setIsLoading(true);
    try {
      const safeWeek = requestedWeek && isIsoDate(requestedWeek) ? requestedWeek : undefined;
      const { data } = await apiClient.get("/user/reports/weekly", {
        params: { include_artifacts: true, week: safeWeek },
      });
      setReport(data);

      if (compareEnabled) {
        const startCandidate = String(data?.week || "").split("->")[0]?.trim();
        const previousStart = startCandidate ? new Date(startCandidate) : null;
        if (previousStart && Number.isFinite(previousStart.getTime())) {
          previousStart.setDate(previousStart.getDate() - 7);
          const weekParam = previousStart.toISOString().slice(0, 10);
          try {
            const previous = await apiClient.get("/user/reports/weekly", {
              params: { include_artifacts: false, week: weekParam },
            });
            setPreviousReport(previous.data || null);
          } catch {
            setPreviousReport(null);
          }
        } else {
          setPreviousReport(null);
        }
      } else {
        setPreviousReport(null);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rapor alınamadı");
    } finally {
      setIsLoading(false);
    }
  }, [compareEnabled]);

  useEffect(() => {
    load();
  }, [load]);

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-reports-loading-skeleton" />;
  }

  const summary = report?.summary || {};
  const links = report?.download_links || {};
  const strategyRows = Object.entries(report?.strategy_contribution || {}).filter(([key]) => strategyFilter === "all" || key === strategyFilter);
  const strategyKeys = Object.keys(report?.strategy_contribution || {});
  const pnlDelta = previousReport ? Number(report?.pnl || 0) - Number(previousReport?.pnl || 0) : null;

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-reports-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-reports-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-reports-title">Weekly Reports</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-reports-description">Haftalık performans özeti ve artefact indirmeleri.</p>
        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="user-reports-control-grid">
          <Input value={weekOverride} onChange={(event) => setWeekOverride(event.target.value)} placeholder="Week override (YYYY-MM-DD)" data-testid="user-reports-week-override-input" />
          <select className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)} data-testid="user-reports-strategy-filter-select">
            <option value="all">all strategies</option>
            {strategyKeys.map((key) => (
              <option key={key} value={key}>{key}</option>
            ))}
          </select>
          <label className="inline-flex items-center gap-2 text-xs text-slate-300" data-testid="user-reports-compare-toggle-wrapper">
            <input type="checkbox" checked={compareEnabled} onChange={(event) => setCompareEnabled(event.target.checked)} data-testid="user-reports-compare-toggle" />
            önceki hafta ile karşılaştır
          </label>
          <Button
            variant="outline"
            onClick={() => {
              if (weekOverride && !isIsoDate(weekOverride)) {
                toast.error("Week override formatı YYYY-MM-DD olmalı");
                return;
              }
              load(weekOverride);
            }}
            data-testid="user-reports-apply-filter-button"
          >
            Uygula
          </Button>
        </div>
      </header>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-reports-summary-grid">
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-pnl-card"><p className="text-xs text-slate-500">PnL</p><p className="text-lg font-semibold">{report?.pnl ?? 0}</p></div>
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-winrate-card"><p className="text-xs text-slate-500">Win Rate</p><p className="text-lg font-semibold">{report?.win_rate ?? 0}%</p></div>
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-drawdown-card"><p className="text-xs text-slate-500">Max Drawdown</p><p className="text-lg font-semibold">{report?.max_drawdown ?? 0}</p></div>
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-status-card"><p className="text-xs text-slate-500">Status</p><p className="text-lg font-semibold">{report?.status ?? "-"}</p></div>
      </div>

      {compareEnabled && (
        <div className="col-span-12 rounded border border-emerald-500/40 bg-emerald-500/10 p-3" data-testid="user-reports-compare-summary-banner">
          <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="user-reports-compare-summary-title">Haftalık Karşılaştırma</p>
          <p className="mt-1 text-sm text-emerald-100" data-testid="user-reports-compare-summary-text">
            PnL Delta: {pnlDelta === null ? "-" : pnlDelta.toFixed(2)}
          </p>
        </div>
      )}

      <div className="col-span-12 lg:col-span-6 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-reports-strategy-contribution-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-reports-strategy-contribution-title">Strategy Contribution</p>
        <div className="mt-3 space-y-2" data-testid="user-reports-strategy-contribution-list">
          {strategyRows.length === 0 && <p className="text-sm text-slate-400" data-testid="user-reports-empty-strategy">Filtreye uygun strateji katkısı yok.</p>}
          {strategyRows.map(([key, value]) => (
            <div key={key} className="flex items-center justify-between text-sm" data-testid="user-reports-strategy-row">
              <span data-testid="user-reports-strategy-key">{key}</span>
              <span data-testid="user-reports-strategy-value">{value}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="col-span-12 lg:col-span-6 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-reports-download-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-reports-download-title">Downloads</p>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="user-reports-download-actions">
          {Object.keys(links).length === 0 && <p className="text-sm text-slate-400" data-testid="user-reports-no-links">İndirilebilir dosya yok.</p>}
          {Object.entries(links).map(([name, url]) => (
            <Button key={name} asChild variant="outline" data-testid="user-reports-download-button">
              <a href={url} target="_blank" rel="noreferrer" aria-label={`${name} indir`}>{name}</a>
            </Button>
          ))}
        </div>
        <div className="mt-4 text-xs text-slate-500" data-testid="user-reports-week-summary">Week: {report?.week}</div>
        <div className="mt-2 text-xs text-slate-500" data-testid="user-reports-trades-count">Trades Count: {summary?.trades_count ?? 0}</div>
      </div>
    </section>
  );
};