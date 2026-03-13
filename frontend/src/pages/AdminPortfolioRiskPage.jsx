import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const emptyClusterForm = {
  cluster_id: "",
  symbols: "",
  cluster_type: "custom",
  correlation_score: 0.7,
  risk_weight: 1,
};

export const AdminPortfolioRiskPage = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [limits, setLimits] = useState(null);
  const [clusters, setClusters] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [clusterForm, setClusterForm] = useState(emptyClusterForm);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const [limitsRes, clustersRes, dashboardRes] = await Promise.all([
        apiClient.get("/admin/portfolio-risk/limits"),
        apiClient.get("/admin/portfolio-risk/clusters"),
        apiClient.get("/admin/portfolio-risk"),
      ]);
      setLimits(limitsRes.data);
      setClusters(clustersRes.data || []);
      setDashboard(dashboardRes.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Portfolio risk verileri yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const riskAlertCount = useMemo(() => (dashboard?.risk_alerts || []).reduce((sum, item) => sum + Number(item.count || 0), 0), [dashboard]);

  const clusterExposureEntries = useMemo(() => Object.entries(dashboard?.cluster_exposure || {}), [dashboard]);
  const strategyExposureEntries = useMemo(() => Object.entries(dashboard?.strategy_exposure || {}), [dashboard]);
  const riskAlerts = useMemo(() => dashboard?.risk_alerts || [], [dashboard]);

  const saveLimits = async () => {
    if (!limits) {
      return;
    }
    try {
      await apiClient.put("/admin/portfolio-risk/limits", {
        max_portfolio_leverage: Number(limits.max_portfolio_leverage),
        max_symbol_exposure: Number(limits.max_symbol_exposure),
        max_cluster_exposure: Number(limits.max_cluster_exposure),
        max_strategy_exposure: Number(limits.max_strategy_exposure),
        max_single_trade_risk: Number(limits.max_single_trade_risk),
        max_intraday_drawdown: Number(limits.max_intraday_drawdown),
        max_total_drawdown: Number(limits.max_total_drawdown),
      });
      toast.success("Risk limitleri güncellendi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk limitleri güncellenemedi");
    }
  };

  const saveCluster = async () => {
    if (!clusterForm.cluster_id.trim()) {
      toast.error("Cluster ID zorunlu");
      return;
    }
    if (!clusterForm.symbols.trim()) {
      toast.error("En az bir sembol girin");
      return;
    }
    try {
      await apiClient.post("/admin/portfolio-risk/clusters", {
        cluster_id: clusterForm.cluster_id,
        symbols: clusterForm.symbols.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean),
        cluster_type: clusterForm.cluster_type,
        correlation_score: Number(clusterForm.correlation_score),
        risk_weight: Number(clusterForm.risk_weight),
      });
      toast.success("Cluster kaydedildi");
      setClusterForm(emptyClusterForm);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Cluster kaydedilemedi");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-portfolio-risk-loading-skeleton" />;
  }

  if (!limits) {
    return (
      <section className="space-y-4" data-testid="admin-portfolio-risk-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-portfolio-risk-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-portfolio-risk-broken-title">Portfolio risk verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-portfolio-risk-broken-message">{loadError || "Servis şu an yanıt vermiyor."}</p>
          <Button className="mt-3" onClick={load} data-testid="admin-portfolio-risk-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="admin-portfolio-risk-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-portfolio-risk-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-portfolio-risk-header-row">
          <div data-testid="admin-portfolio-risk-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-portfolio-risk-title">Portfolio Risk Dashboard</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-portfolio-risk-description">Total exposure, cluster exposure ve risk alert izleme paneli.</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-portfolio-risk-timestamp">Snapshot: {dashboard?.timestamp ? new Date(dashboard.timestamp).toLocaleString() : "-"}</p>
          </div>
          <Button onClick={load} data-testid="admin-portfolio-risk-refresh-button">Yenile</Button>
        </div>
      </header>

      {loadError && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-portfolio-risk-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      <div className="col-span-12 grid gap-3 md:grid-cols-3" data-testid="admin-portfolio-risk-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-portfolio-risk-total-exposure-card">
          <p className="text-xs text-slate-500">Total Exposure</p>
          <p className="text-xl font-semibold" data-testid="admin-portfolio-risk-total-exposure-value">{dashboard?.total_exposure ?? 0}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-portfolio-risk-alert-count-card">
          <p className="text-xs text-slate-500">Risk Alerts (24h)</p>
          <p className="text-xl font-semibold text-amber-400" data-testid="admin-portfolio-risk-alert-count-value">{riskAlertCount}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-portfolio-risk-cluster-count-card">
          <p className="text-xs text-slate-500">Cluster Count</p>
          <p className="text-xl font-semibold" data-testid="admin-portfolio-risk-cluster-count-value">{clusters.length}</p>
        </article>
      </div>

      <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-portfolio-risk-limits-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-portfolio-risk-limits-title">Risk Limit Registry</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="admin-portfolio-risk-limits-grid">
          {Object.keys(limits).map((key) => (
            <div key={key} data-testid={`admin-portfolio-risk-limit-field-${key}`}>
              <label className="text-xs text-slate-500" data-testid={`admin-portfolio-risk-limit-label-${key}`}>{key}</label>
              <Input type="number" value={limits[key]} onChange={(event) => setLimits((prev) => ({ ...prev, [key]: event.target.value }))} data-testid={`admin-portfolio-risk-limit-input-${key}`} />
            </div>
          ))}
        </div>
        <Button className="mt-4" onClick={saveLimits} data-testid="admin-portfolio-risk-save-limits-button">Limitleri Kaydet</Button>
      </section>

      <section className="col-span-12 lg:col-span-4 border border-slate-800 bg-slate-900 p-4" data-testid="admin-portfolio-risk-cluster-form-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-portfolio-risk-cluster-form-title">Cluster Ekle / Güncelle</p>
        <div className="mt-3 space-y-3" data-testid="admin-portfolio-risk-cluster-form-fields">
          <Input placeholder="Cluster ID (L3)" value={clusterForm.cluster_id} onChange={(event) => setClusterForm((prev) => ({ ...prev, cluster_id: event.target.value.toUpperCase() }))} data-testid="admin-portfolio-risk-cluster-id-input" />
          <Input placeholder="BTCUSDT,ETHUSDT" value={clusterForm.symbols} onChange={(event) => setClusterForm((prev) => ({ ...prev, symbols: event.target.value }))} data-testid="admin-portfolio-risk-cluster-symbols-input" />
          <Input placeholder="cluster_type" value={clusterForm.cluster_type} onChange={(event) => setClusterForm((prev) => ({ ...prev, cluster_type: event.target.value }))} data-testid="admin-portfolio-risk-cluster-type-input" />
          <Input type="number" placeholder="correlation_score" value={clusterForm.correlation_score} onChange={(event) => setClusterForm((prev) => ({ ...prev, correlation_score: event.target.value }))} data-testid="admin-portfolio-risk-cluster-correlation-input" />
          <Input type="number" placeholder="risk_weight" value={clusterForm.risk_weight} onChange={(event) => setClusterForm((prev) => ({ ...prev, risk_weight: event.target.value }))} data-testid="admin-portfolio-risk-cluster-risk-weight-input" />
          <Button onClick={saveCluster} data-testid="admin-portfolio-risk-save-cluster-button">Cluster Kaydet</Button>
        </div>
      </section>

      <section className="col-span-12 lg:col-span-8 border border-slate-800 bg-slate-900 p-4" data-testid="admin-portfolio-risk-cluster-table-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-portfolio-risk-cluster-table-title">Risk Clusters</p>
        <div className="mt-3 overflow-x-auto" data-testid="admin-portfolio-risk-cluster-table-wrapper">
          <table className="min-w-full text-sm" data-testid="admin-portfolio-risk-cluster-table">
            <thead className="bg-slate-800 text-left" data-testid="admin-portfolio-risk-cluster-table-head">
              <tr>
                <th className="px-3 py-2">Cluster</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Symbols</th>
                <th className="px-3 py-2 text-right">Correlation</th>
                <th className="px-3 py-2 text-right">Risk Weight</th>
              </tr>
            </thead>
            <tbody data-testid="admin-portfolio-risk-cluster-table-body">
              {clusters.map((item) => (
                <tr key={item.cluster_id} className="border-t border-slate-800" data-testid={`admin-portfolio-risk-cluster-row-${item.cluster_id}`}>
                  <td className="px-3 py-2" data-testid={`admin-portfolio-risk-cluster-id-${item.cluster_id}`}>{item.cluster_id}</td>
                  <td className="px-3 py-2" data-testid={`admin-portfolio-risk-cluster-type-${item.cluster_id}`}>{item.cluster_type}</td>
                  <td className="px-3 py-2" data-testid={`admin-portfolio-risk-cluster-symbols-${item.cluster_id}`}>{(item.symbols || []).join(", ")}</td>
                  <td className="px-3 py-2 text-right tabular-nums" data-testid={`admin-portfolio-risk-cluster-correlation-${item.cluster_id}`}>{item.correlation_score}</td>
                  <td className="px-3 py-2 text-right tabular-nums" data-testid={`admin-portfolio-risk-cluster-risk-weight-${item.cluster_id}`}>{item.risk_weight}</td>
                </tr>
              ))}
              {clusters.length === 0 && (
                <tr className="border-t border-slate-800" data-testid="admin-portfolio-risk-cluster-empty-row">
                  <td colSpan={5} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-portfolio-risk-cluster-empty-text">Risk cluster kaydı bulunamadı.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-portfolio-risk-exposure-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-portfolio-risk-exposure-title">Exposure Breakdown</p>
        <div className="mt-3 grid gap-4 md:grid-cols-2" data-testid="admin-portfolio-risk-exposure-grid">
          <div data-testid="admin-portfolio-risk-cluster-exposure-list">
            <p className="text-xs text-slate-500">Cluster Exposure</p>
            {clusterExposureEntries.length === 0 && <p className="text-sm text-slate-400" data-testid="admin-portfolio-risk-cluster-exposure-empty">Cluster exposure verisi yok.</p>}
            {clusterExposureEntries.map(([key, value]) => (
              <p key={key} className="text-sm" data-testid={`admin-portfolio-risk-cluster-exposure-item-${key}`}>{key}: {value}</p>
            ))}
          </div>
          <div data-testid="admin-portfolio-risk-strategy-exposure-list">
            <p className="text-xs text-slate-500">Strategy Exposure</p>
            {strategyExposureEntries.length === 0 && <p className="text-sm text-slate-400" data-testid="admin-portfolio-risk-strategy-exposure-empty">Strategy exposure verisi yok.</p>}
            {strategyExposureEntries.map(([key, value]) => (
              <p key={key} className="text-sm" data-testid={`admin-portfolio-risk-strategy-exposure-item-${key}`}>{key}: {value}</p>
            ))}
          </div>
        </div>
      </section>

      <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-portfolio-risk-alert-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-portfolio-risk-alert-title">Risk Alerts (24h)</p>
        <div className="mt-3 space-y-2" data-testid="admin-portfolio-risk-alert-list">
          {riskAlerts.length === 0 && <p className="text-sm text-slate-400" data-testid="admin-portfolio-risk-alert-empty">Son 24 saatte risk alert oluşmadı.</p>}
          {riskAlerts.map((item) => (
            <div key={item.gate_decision} className="flex items-center justify-between border border-slate-800 px-3 py-2" data-testid={`admin-portfolio-risk-alert-row-${item.gate_decision}`}>
              <span className="text-sm text-slate-300" data-testid={`admin-portfolio-risk-alert-decision-${item.gate_decision}`}>{item.gate_decision}</span>
              <span className="text-sm font-semibold" data-testid={`admin-portfolio-risk-alert-count-${item.gate_decision}`}>{item.count}</span>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
};
