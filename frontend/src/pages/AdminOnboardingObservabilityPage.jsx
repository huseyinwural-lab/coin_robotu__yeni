import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export default function AdminOnboardingObservabilityPage() {
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/onboarding/observability/summary", { params: { days } });
      setPayload(data || null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const funnelRows = useMemo(() => {
    const funnel = payload?.kpis?.funnel || {};
    return [
      ["signup", funnel.signup ?? 0],
      ["kyc_started", funnel.kyc_started ?? 0],
      ["kyc_verified", funnel.kyc_verified ?? 0],
      ["approved", funnel.approved ?? 0],
      ["activated", funnel.activated ?? 0],
    ];
  }, [payload]);
  const kpis = payload?.kpis || {};

  return (
    <section className="space-y-4" data-testid="admin-onboarding-observability-page">
      <header className="border border-black/40 bg-cyan-200 p-4" data-testid="admin-onboarding-observability-header">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-onboarding-observability-header-row">
          <div data-testid="admin-onboarding-observability-header-text">
            <h1 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-onboarding-observability-title">Onboarding Observability</h1>
            <p className="mt-1 text-sm text-black/70" data-testid="admin-onboarding-observability-description">Approval rate, funnel, reject dağılımı, SLA breach ve reconcile görünümü.</p>
          </div>
          <div className="flex items-center gap-2" data-testid="admin-onboarding-observability-header-actions">
            <select
              className="border border-black/40 bg-white px-3 py-2 text-sm"
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
              data-testid="admin-onboarding-observability-window-select"
            >
              <option value={7}>7 gün</option>
              <option value={30}>30 gün</option>
              <option value={90}>90 gün</option>
            </select>
            <Button onClick={load} data-testid="admin-onboarding-observability-refresh-button">{loading ? "Yükleniyor..." : "Yenile"}</Button>
            <Button variant="outline" onClick={() => navigate("/admin/user-approvals")} data-testid="admin-onboarding-observability-back-approvals-button">Approvals'a dön</Button>
          </div>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-onboarding-observability-kpi-grid">
        <article className="border border-black/30 bg-cyan-50 p-3" data-testid="admin-onboarding-observability-kpi-approval-rate-card">
          <p className="text-xs uppercase text-black/60">approval_rate</p>
          <p className="text-2xl font-semibold" data-testid="admin-onboarding-observability-kpi-approval-rate-value">{kpis.approval_rate ?? 0}%</p>
        </article>
        <article className="border border-black/30 bg-cyan-50 p-3" data-testid="admin-onboarding-observability-kpi-avg-approval-time-card">
          <p className="text-xs uppercase text-black/60">avg_approval_time</p>
          <p className="text-2xl font-semibold" data-testid="admin-onboarding-observability-kpi-avg-approval-time-value">{kpis.avg_approval_time ?? 0} dk</p>
        </article>
        <article className="border border-black/30 bg-cyan-50 p-3" data-testid="admin-onboarding-observability-kpi-dropoff-rate-card">
          <p className="text-xs uppercase text-black/60">drop_off_rate</p>
          <p className="text-2xl font-semibold" data-testid="admin-onboarding-observability-kpi-dropoff-rate-value">{kpis.drop_off_rate ?? 0}%</p>
        </article>
        <article className="border border-black/30 bg-cyan-50 p-3" data-testid="admin-onboarding-observability-kpi-sla-breach-rate-card">
          <p className="text-xs uppercase text-black/60">sla_breach_rate</p>
          <p className="text-2xl font-semibold" data-testid="admin-onboarding-observability-kpi-sla-breach-rate-value">{kpis.sla_breach_rate ?? 0}%</p>
        </article>
      </div>

      <div className="grid gap-3 md:grid-cols-2" data-testid="admin-onboarding-observability-detail-grid">
        <article className="border border-black/30 bg-white p-3" data-testid="admin-onboarding-observability-funnel-card">
          <p className="text-xs uppercase text-black/60" data-testid="admin-onboarding-observability-funnel-title">Funnel</p>
          <div className="mt-2 space-y-1" data-testid="admin-onboarding-observability-funnel-list">
            {funnelRows.map(([key, value]) => (
              <div key={key} className="flex items-center justify-between text-sm" data-testid={`admin-onboarding-observability-funnel-row-${key}`}>
                <span>{key}</span>
                <span data-testid={`admin-onboarding-observability-funnel-value-${key}`}>{value}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="border border-black/30 bg-white p-3" data-testid="admin-onboarding-observability-reject-distribution-card">
          <p className="text-xs uppercase text-black/60" data-testid="admin-onboarding-observability-reject-distribution-title">Reject Distribution</p>
          <div className="mt-2 space-y-1" data-testid="admin-onboarding-observability-reject-distribution-list">
            {(kpis.reject_distribution || []).length === 0 && (
              <p className="text-sm text-black/60" data-testid="admin-onboarding-observability-reject-distribution-empty">Veri yok</p>
            )}
            {(kpis.reject_distribution || []).map((row, index) => (
              <div key={`${row.reason}-${index}`} className="flex items-center justify-between text-sm" data-testid={`admin-onboarding-observability-reject-distribution-row-${index}`}>
                <span data-testid={`admin-onboarding-observability-reject-distribution-reason-${index}`}>{row.reason}</span>
                <span data-testid={`admin-onboarding-observability-reject-distribution-count-${index}`}>{row.count} ({row.ratio}%)</span>
              </div>
            ))}
          </div>
        </article>
      </div>

      <article className="border border-black/30 bg-white p-3" data-testid="admin-onboarding-observability-reconcile-card">
        <p className="text-xs uppercase text-black/60" data-testid="admin-onboarding-observability-reconcile-title">Truth Layer / Reconcile</p>
        <p className="mt-1 text-sm" data-testid="admin-onboarding-observability-reconcile-status">status: {payload?.status || "-"}</p>
        <p className="text-sm" data-testid="admin-onboarding-observability-reconcile-mismatch">
          mismatch: {(payload?.reconcile?.mismatch_reasons || []).join(", ") || "none"}
        </p>
        <p className="mt-2 text-sm" data-testid="admin-onboarding-observability-telemetry-percentiles">
          telemetry p50/p95/p99: {payload?.telemetry?.percentiles_ms?.p50 ?? 0} / {payload?.telemetry?.percentiles_ms?.p95 ?? 0} / {payload?.telemetry?.percentiles_ms?.p99 ?? 0} ms
        </p>
      </article>
    </section>
  );
}
