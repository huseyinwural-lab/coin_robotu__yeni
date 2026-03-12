import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const UserReportsPage = () => {
  const [report, setReport] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = async () => {
    setIsLoading(true);
    try {
      const { data } = await apiClient.get("/user/reports/weekly", {
        params: { include_artifacts: true },
      });
      setReport(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rapor alınamadı");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-reports-loading-skeleton" />;
  }

  const summary = report?.summary || {};
  const links = report?.download_links || {};

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-reports-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-reports-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-reports-title">Weekly Reports</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-reports-description">Haftalık performans özeti ve artefact indirmeleri.</p>
      </header>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-reports-summary-grid">
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-pnl-card"><p className="text-xs text-slate-500">PnL</p><p className="text-lg font-semibold">{report?.pnl ?? 0}</p></div>
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-winrate-card"><p className="text-xs text-slate-500">Win Rate</p><p className="text-lg font-semibold">{report?.win_rate ?? 0}%</p></div>
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-drawdown-card"><p className="text-xs text-slate-500">Max Drawdown</p><p className="text-lg font-semibold">{report?.max_drawdown ?? 0}</p></div>
        <div className="col-span-6 md:col-span-3 rounded border border-slate-800 bg-slate-900 p-3" data-testid="user-reports-status-card"><p className="text-xs text-slate-500">Status</p><p className="text-lg font-semibold">{report?.status ?? "-"}</p></div>
      </div>

      <div className="col-span-12 lg:col-span-6 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-reports-strategy-contribution-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-reports-strategy-contribution-title">Strategy Contribution</p>
        <div className="mt-3 space-y-2" data-testid="user-reports-strategy-contribution-list">
          {Object.keys(report?.strategy_contribution || {}).length === 0 && <p className="text-sm text-slate-400" data-testid="user-reports-empty-strategy">Bu hafta strateji katkısı yok.</p>}
          {Object.entries(report?.strategy_contribution || {}).map(([key, value]) => (
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