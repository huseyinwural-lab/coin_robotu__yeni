import { useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const criticalActions = [
  { key: "stop_all_bots", label: "STOP ALL BOTS" },
  { key: "disable_futures", label: "Disable Futures" },
  { key: "force_close", label: "Force Close All Positions" },
  { key: "risk_mode", label: "Emergency Risk Mode" },
];

export const AdminDashboardPage = () => {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    const fetchSummary = async () => {
      const { data } = await apiClient.get("/dashboard/summary");
      setSummary(data);
    };
    fetchSummary();
  }, []);

  const runCriticalAction = (label) => {
    const firstCheck = window.confirm(`${label} aksiyonunu başlatmak istediğine emin misin?`);
    if (!firstCheck) return;
    const secondCheck = window.confirm("Bu işlem canlı sistemler için kritik olabilir. Tekrar onaylıyor musun?");
    if (secondCheck) {
      toast.warning(`${label} komutu kontrol yüzeyinde tetiklendi (skeleton).`);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-dashboard-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="admin-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="admin-dashboard-title">Admin Dashboard Shell</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-dashboard-description">
          Normal alanlar mavi, kritik alanlar kırmızı. Double-confirm pattern aktif.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="admin-dashboard-metrics-grid">
        <MetricCard label="Kullanıcı" value={summary?.metrics?.users ?? "-"} tone="blue" testId="admin-metric-users" />
        <MetricCard label="Aktif Bot" value={summary?.metrics?.active_bots ?? "-"} tone="blue" testId="admin-metric-active-bots" />
        <MetricCard label="Risk Policy" value={summary?.metrics?.risk_policies ?? "-"} tone="blue" testId="admin-metric-risk-policies" />
        <MetricCard label="Template" value={summary?.metrics?.strategy_templates ?? "-"} tone="blue" testId="admin-metric-strategies" />
        <MetricCard label="Critical Audit" value={summary?.metrics?.critical_audits ?? "-"} tone="red" testId="admin-metric-critical-audits" />
      </div>

      <div className="border border-red-500/50 bg-red-950/20 p-4" data-testid="admin-critical-actions-panel">
        <p className="text-xs uppercase tracking-widest text-red-300" data-testid="admin-critical-actions-title">Kritik Kontrol Alanı</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2" data-testid="admin-critical-actions-grid">
          {criticalActions.map((action) => (
            <Button
              key={action.key}
              variant="outline"
              className="border-red-400 bg-transparent text-red-300 hover:bg-red-900/40 hover:text-red-100"
              onClick={() => runCriticalAction(action.label)}
              data-testid={`admin-critical-action-${action.key}`}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>
    </section>
  );
};
