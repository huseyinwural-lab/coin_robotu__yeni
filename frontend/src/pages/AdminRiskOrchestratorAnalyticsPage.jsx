import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const MetricRow = ({ label, value, testId }) => (
  <div className="flex items-center justify-between text-sm" data-testid={testId}>
    <span className="text-slate-400">{label}</span>
    <span className="font-semibold text-slate-100">{value}</span>
  </div>
);

const BarList = ({ items, testIdPrefix }) => (
  <div className="space-y-2" data-testid={`${testIdPrefix}-list`}>
    {items.length === 0 && (
      <p className="text-xs text-slate-400" data-testid={`${testIdPrefix}-empty`}>
        Veri yok.
      </p>
    )}
    {items.map((item) => (
      <div key={item.label || item.date} className="space-y-1" data-testid={`${testIdPrefix}-row-${item.label || item.date}`}>
        <div className="flex items-center justify-between text-xs">
          <span>{item.label || item.date}</span>
          <span>{item.value}</span>
        </div>
        <div className="h-2 w-full rounded bg-slate-800">
          <div className="h-full rounded bg-orange-500" style={{ width: `${Math.min(item.value * 5, 100)}%` }} />
        </div>
      </div>
    ))}
  </div>
);

export const AdminRiskOrchestratorAnalyticsPage = () => {
  const [days, setDays] = useState(14);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/strategy-domain/admin/risk-orchestrator/analytics", { params: { days } });
      setAnalytics(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk analytics yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  return (
    <section className="space-y-4" data-testid="admin-risk-analytics-page">
      <header className="border border-orange-700 bg-slate-900 p-4" data-testid="admin-risk-analytics-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-risk-analytics-title">
          Risk Orchestrator Analytics
        </h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-risk-analytics-description">
          Audit tabanlı breach trendleri ve reject dağılımı.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3" data-testid="admin-risk-analytics-controls">
          <Input
            type="number"
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            className="max-w-[140px]"
            data-testid="admin-risk-analytics-days-input"
          />
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={loadAnalytics} data-testid="admin-risk-analytics-refresh">
            Refresh
          </Button>
        </div>
      </header>

      {loading && <p className="text-sm text-slate-400" data-testid="admin-risk-analytics-loading">Yükleniyor...</p>}
      {!loading && !analytics && <p className="text-sm text-slate-400" data-testid="admin-risk-analytics-empty">Veri yok.</p>}

      {analytics && (
        <div className="grid gap-4 xl:grid-cols-[1fr_1.2fr]" data-testid="admin-risk-analytics-grid">
          <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-analytics-summary">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-analytics-summary-title">Summary</p>
            <MetricRow label="Risk policy hits" value={analytics.risk_policy_hits} testId="admin-risk-analytics-hits" />
            <MetricRow label="Kill switch events" value={analytics.kill_switch_events} testId="admin-risk-analytics-kill-switch" />
            <MetricRow label="Duplicate attempts" value={analytics.duplicate_intent_attempts} testId="admin-risk-analytics-duplicates" />
            <MetricRow label="Generated at" value={new Date(analytics.generated_at).toLocaleString()} testId="admin-risk-analytics-generated" />
          </div>

          <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-analytics-reason-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-analytics-reason-title">Reject Reason Distribution</p>
            <BarList items={analytics.reject_reason_distribution || []} testIdPrefix="admin-risk-analytics-reason" />
          </div>

          <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-analytics-day-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-analytics-day-title">Breach by Day</p>
            <BarList items={analytics.breach_by_day || []} testIdPrefix="admin-risk-analytics-day" />
          </div>

          <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-analytics-strategy-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-analytics-strategy-title">Breach by Strategy</p>
            <BarList items={analytics.breach_by_strategy || []} testIdPrefix="admin-risk-analytics-strategy" />
          </div>

          <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-analytics-symbol-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-analytics-symbol-title">Breach by Symbol</p>
            <BarList items={analytics.breach_by_symbol || []} testIdPrefix="admin-risk-analytics-symbol" />
          </div>
        </div>
      )}
    </section>
  );
};
