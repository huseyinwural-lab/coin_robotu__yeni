import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const OnboardingObservabilitySnapshot = ({ onOpenDetail }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get("/admin/onboarding/observability/summary", { params: { days: 30 } });
      setData(response.data || null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const kpis = data?.kpis || {};

  return (
    <article className="border border-cyan-800/40 bg-slate-900 p-4" data-testid="admin-dashboard-onboarding-observability-snapshot">
      <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-dashboard-onboarding-observability-snapshot-header">
        <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="admin-dashboard-onboarding-observability-snapshot-title">
          Onboarding Observability Snapshot
        </p>
        <div className="flex gap-2" data-testid="admin-dashboard-onboarding-observability-snapshot-actions">
          <Button variant="outline" size="sm" onClick={load} data-testid="admin-dashboard-onboarding-observability-refresh-button">
            {loading ? "Yükleniyor..." : "Yenile"}
          </Button>
          <Button variant="outline" size="sm" onClick={onOpenDetail} data-testid="admin-dashboard-onboarding-observability-open-detail-button">
            Detaya Git
          </Button>
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="admin-dashboard-onboarding-observability-kpi-grid">
        <div className="border border-cyan-900/40 bg-slate-950 p-2" data-testid="admin-dashboard-onboarding-observability-approval-rate-card">
          <p className="text-[11px] text-slate-400">approval_rate</p>
          <p className="text-sm font-semibold text-cyan-200" data-testid="admin-dashboard-onboarding-observability-approval-rate-value">{kpis.approval_rate ?? 0}%</p>
        </div>
        <div className="border border-cyan-900/40 bg-slate-950 p-2" data-testid="admin-dashboard-onboarding-observability-avg-approval-time-card">
          <p className="text-[11px] text-slate-400">avg_approval_time</p>
          <p className="text-sm font-semibold text-cyan-200" data-testid="admin-dashboard-onboarding-observability-avg-approval-time-value">{kpis.avg_approval_time ?? 0} dk</p>
        </div>
        <div className="border border-cyan-900/40 bg-slate-950 p-2" data-testid="admin-dashboard-onboarding-observability-dropoff-rate-card">
          <p className="text-[11px] text-slate-400">drop_off_rate</p>
          <p className="text-sm font-semibold text-cyan-200" data-testid="admin-dashboard-onboarding-observability-dropoff-rate-value">{kpis.drop_off_rate ?? 0}%</p>
        </div>
        <div className="border border-cyan-900/40 bg-slate-950 p-2" data-testid="admin-dashboard-onboarding-observability-sla-breach-rate-card">
          <p className="text-[11px] text-slate-400">sla_breach_rate</p>
          <p className="text-sm font-semibold text-cyan-200" data-testid="admin-dashboard-onboarding-observability-sla-breach-rate-value">{kpis.sla_breach_rate ?? 0}%</p>
        </div>
      </div>
    </article>
  );
};
