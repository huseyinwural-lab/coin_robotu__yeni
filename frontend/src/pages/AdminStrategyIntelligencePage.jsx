import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const AdminStrategyIntelligencePage = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [manualOverrides, setManualOverrides] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");
  const [simulationForm, setSimulationForm] = useState({
    user_id: "",
    symbol: "BTCUSDT",
    side: "buy",
    notional: 100,
    strategy_binding: "spot_pullback_v1",
    volatility_pct: 3,
    apply_override: false,
    override_action_type: "",
    override_reason: "",
  });
  const [simulationResult, setSimulationResult] = useState(null);
  const [simulationSymbolSource, setSimulationSymbolSource] = useState("crypto");
  const [simulationSymbolMode, setSimulationSymbolMode] = useState("all_market_symbols");
  const [simulationSelectedSymbols, setSimulationSelectedSymbols] = useState(["BTCUSDT"]);

  useEffect(() => {
    if ((simulationSelectedSymbols || []).length === 0) {
      return;
    }
    setSimulationForm((prev) => ({ ...prev, symbol: simulationSelectedSymbols[0] }));
  }, [simulationSelectedSymbols]);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const [dashRes, overridesRes] = await Promise.all([
        apiClient.get("/admin/strategy-intelligence"),
        apiClient.get("/admin/manual-overrides"),
      ]);
      setDashboard(dashRes.data || null);
      setManualOverrides(overridesRes.data || []);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      const message = error?.response?.data?.detail || "Strategy intelligence verisi yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const conflicts = useMemo(() => dashboard?.strategy_conflicts || [], [dashboard]);
  const hedgeSuggestions = useMemo(() => dashboard?.hedge_suggestions || [], [dashboard]);

  const submitSimulation = async () => {
    if (!simulationForm.user_id.trim()) {
      toast.error("Risk simulation için user_id zorunlu");
      return;
    }
    try {
      const payload = {
        user_id: simulationForm.user_id,
        intent_payload: {
          symbol: simulationForm.symbol,
          side: simulationForm.side,
          notional: Number(simulationForm.notional),
          strategy_binding: simulationForm.strategy_binding,
          volatility_pct: Number(simulationForm.volatility_pct),
          position_size_value: Number(simulationForm.notional),
        },
        apply_override: Boolean(simulationForm.apply_override),
        override_action_type: simulationForm.override_action_type || null,
        override_reason: simulationForm.override_reason || null,
      };
      const { data } = await apiClient.post("/admin/risk-simulation", payload);
      setSimulationResult(data || null);
      toast.success("Risk simulation tamamlandı");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk simulation başarısız");
    }
  };

  const createManualOverride = async () => {
    if (!simulationForm.override_action_type.trim() || !simulationForm.override_reason.trim()) {
      toast.error("Manual override için action type ve reason zorunlu");
      return;
    }
    try {
      await apiClient.post("/admin/manual-overrides", {
        action_type: simulationForm.override_action_type,
        reason: simulationForm.override_reason,
        payload: {
          source: "admin_strategy_intelligence_panel",
          user_id: simulationForm.user_id || null,
        },
      });
      toast.success("Manual override loglandı");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Manual override kaydedilemedi");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={10} testId="admin-strategy-intelligence-loading-skeleton" />;
  }

  if (!dashboard) {
    return (
      <section className="space-y-4" data-testid="admin-strategy-intelligence-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-strategy-intelligence-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-strategy-intelligence-broken-title">Strategy intelligence verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-strategy-intelligence-broken-message">{loadError || "Servis geçici olarak yanıt vermiyor."}</p>
          <Button className="mt-3" onClick={load} data-testid="admin-strategy-intelligence-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="admin-strategy-intelligence-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-intelligence-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-strategy-intelligence-header-row">
          <div data-testid="admin-strategy-intelligence-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-strategy-intelligence-title">Strategy Intelligence</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-strategy-intelligence-description">Conflict resolver, dynamic rebalance, hedge suggestions ve simulation mode paneli.</p>
            <p className="mt-1 text-xs text-slate-500" data-testid="admin-strategy-intelligence-last-updated">Son güncelleme: {lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "-"}</p>
          </div>
          <Button onClick={load} data-testid="admin-strategy-intelligence-refresh-button">Yenile</Button>
        </div>
      </header>

      {loadError && (
        <div className="col-span-12 border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-strategy-intelligence-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      <div className="col-span-12 grid gap-3 md:grid-cols-4" data-testid="admin-strategy-intelligence-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-intelligence-conflict-count-card">
          <p className="text-xs text-slate-500">Strategy Conflicts</p>
          <p className="text-xl font-semibold" data-testid="admin-strategy-intelligence-conflict-count-value">{(dashboard.strategy_conflicts || []).length}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-intelligence-rebalance-count-card">
          <p className="text-xs text-slate-500">Rebalance Events</p>
          <p className="text-xl font-semibold" data-testid="admin-strategy-intelligence-rebalance-count-value">{(dashboard.capital_rebalance_events || []).length}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-intelligence-drift-card">
          <p className="text-xs text-slate-500">Allocation Drift</p>
          <p className="text-xl font-semibold" data-testid="admin-strategy-intelligence-drift-value">{dashboard.allocation_drift}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-strategy-intelligence-rar-card">
          <p className="text-xs text-slate-500">Risk Adjusted Return</p>
          <p className="text-xl font-semibold" data-testid="admin-strategy-intelligence-rar-value">{dashboard.risk_adjusted_return}</p>
        </article>
      </div>

      <section className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-intelligence-conflicts-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-intelligence-conflicts-title">Strategy Conflicts</p>
        <div className="mt-2 space-y-2" data-testid="admin-strategy-intelligence-conflicts-list">
          {conflicts.slice(0, 8).map((item, index) => (
            <article key={`${item.winning_strategy}-${index}`} className="border border-slate-800 p-2" data-testid={`admin-strategy-intelligence-conflict-item-${index}`}>
              <p className="text-sm" data-testid={`admin-strategy-intelligence-conflict-winner-${index}`}>winner: {item.winning_strategy || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`admin-strategy-intelligence-conflict-loser-${index}`}>loser: {item.losing_strategy || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`admin-strategy-intelligence-conflict-reason-${index}`}>reason: {item.resolution_reason}</p>
            </article>
          ))}
          {conflicts.length === 0 && <p className="text-sm text-slate-400" data-testid="admin-strategy-intelligence-conflicts-empty">Aktif strategy conflict bulunmuyor.</p>}
        </div>
      </section>

      <section className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-intelligence-hedge-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-intelligence-hedge-title">Hedge Suggestions</p>
        <div className="mt-2 space-y-2" data-testid="admin-strategy-intelligence-hedge-list">
          {hedgeSuggestions.slice(0, 8).map((item, index) => (
            <article key={`${item.hedge_symbol || "none"}-${index}`} className="border border-slate-800 p-2" data-testid={`admin-strategy-intelligence-hedge-item-${index}`}>
              <p className="text-sm" data-testid={`admin-strategy-intelligence-hedge-symbol-${index}`}>symbol: {item.hedge_symbol || "none"}</p>
              <p className="text-xs text-slate-400" data-testid={`admin-strategy-intelligence-hedge-size-${index}`}>size: {item.hedge_size}</p>
              <p className="text-xs text-slate-400" data-testid={`admin-strategy-intelligence-hedge-direction-${index}`}>direction: {item.hedge_direction || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`admin-strategy-intelligence-hedge-risk-score-${index}`}>risk_reduction_score: {item.risk_reduction_score}</p>
            </article>
          ))}
          {hedgeSuggestions.length === 0 && <p className="text-sm text-slate-400" data-testid="admin-strategy-intelligence-hedge-empty">Aktif hedge önerisi bulunmuyor.</p>}
        </div>
      </section>

      <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-intelligence-simulation-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-intelligence-simulation-title">Risk Simulation Mode</p>
        <div className="mt-3 grid gap-3 md:grid-cols-3" data-testid="admin-strategy-intelligence-simulation-form-grid">
          <Input placeholder="user_id" value={simulationForm.user_id} onChange={(event) => setSimulationForm((prev) => ({ ...prev, user_id: event.target.value }))} data-testid="admin-strategy-intelligence-simulation-user-id-input" />
          <Input placeholder="symbol" value={simulationForm.symbol} onChange={(event) => setSimulationForm((prev) => ({ ...prev, symbol: event.target.value.toUpperCase() }))} data-testid="admin-strategy-intelligence-simulation-symbol-input" />
          <Input placeholder="side" value={simulationForm.side} onChange={(event) => setSimulationForm((prev) => ({ ...prev, side: event.target.value }))} data-testid="admin-strategy-intelligence-simulation-side-input" />
          <Input type="number" placeholder="notional" value={simulationForm.notional} onChange={(event) => setSimulationForm((prev) => ({ ...prev, notional: event.target.value }))} data-testid="admin-strategy-intelligence-simulation-notional-input" />
          <Input placeholder="strategy_binding" value={simulationForm.strategy_binding} onChange={(event) => setSimulationForm((prev) => ({ ...prev, strategy_binding: event.target.value }))} data-testid="admin-strategy-intelligence-simulation-strategy-input" />
          <Input type="number" placeholder="volatility_pct" value={simulationForm.volatility_pct} onChange={(event) => setSimulationForm((prev) => ({ ...prev, volatility_pct: event.target.value }))} data-testid="admin-strategy-intelligence-simulation-volatility-input" />
          <Input placeholder="override_action_type" value={simulationForm.override_action_type} onChange={(event) => setSimulationForm((prev) => ({ ...prev, override_action_type: event.target.value }))} data-testid="admin-strategy-intelligence-override-action-input" />
          <Input placeholder="override_reason" value={simulationForm.override_reason} onChange={(event) => setSimulationForm((prev) => ({ ...prev, override_reason: event.target.value }))} data-testid="admin-strategy-intelligence-override-reason-input" />
          <label className="flex items-center gap-2 text-sm" data-testid="admin-strategy-intelligence-apply-override-toggle-wrapper">
            <input type="checkbox" checked={simulationForm.apply_override} onChange={(event) => setSimulationForm((prev) => ({ ...prev, apply_override: event.target.checked }))} data-testid="admin-strategy-intelligence-apply-override-toggle" />
            apply_override
          </label>
        </div>
        <div className="mt-3" data-testid="admin-strategy-intelligence-symbol-selector-wrapper">
          <SymbolSelectorPanel
            testIdPrefix="admin-strategy-intelligence-symbol-selector"
            exchange="binance"
            marketType="spot"
            source={simulationSymbolSource}
            onSourceChange={setSimulationSymbolSource}
            mode={simulationSymbolMode}
            onModeChange={setSimulationSymbolMode}
            selectedSymbols={simulationSelectedSymbols}
            onSelectedSymbolsChange={setSimulationSelectedSymbols}
            multi={false}
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="admin-strategy-intelligence-simulation-actions">
          <Button onClick={submitSimulation} data-testid="admin-strategy-intelligence-run-simulation-button">Run Simulation</Button>
          <Button variant="outline" onClick={createManualOverride} data-testid="admin-strategy-intelligence-create-override-button">Log Manual Override</Button>
        </div>

        {simulationResult && (
          <div className="mt-3 border border-slate-800 p-3" data-testid="admin-strategy-intelligence-simulation-result-panel">
            <p className="text-sm" data-testid="admin-strategy-intelligence-simulation-risk-score">projected_risk_score: {simulationResult.projected_risk_score}</p>
            <p className="text-sm" data-testid="admin-strategy-intelligence-simulation-gate-decision">projected_gate_decision: {simulationResult.projected_gate_decision}</p>
            <p className="text-xs text-slate-400" data-testid="admin-strategy-intelligence-simulation-conflict">strategy_conflict: {simulationResult.strategy_conflict?.resolution_reason || "none"}</p>
            <p className="text-xs text-slate-400" data-testid="admin-strategy-intelligence-simulation-allocation">allocation_notice: {simulationResult.allocation_adjustment?.notice || "none"}</p>
            <p className="text-xs text-slate-400" data-testid="admin-strategy-intelligence-simulation-hedge">hedge: {simulationResult.hedge_suggestion?.hedge_symbol || "none"}</p>
          </div>
        )}
      </section>

      <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-intelligence-manual-overrides-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-intelligence-manual-overrides-title">Manual Override Audit</p>
        <div className="mt-2 space-y-2" data-testid="admin-strategy-intelligence-manual-overrides-list">
          {manualOverrides.slice(0, 10).map((item) => (
            <article key={item.override_id} className="border border-slate-800 p-2" data-testid={`admin-strategy-intelligence-manual-override-item-${item.override_id}`}>
              <p className="text-sm" data-testid={`admin-strategy-intelligence-manual-override-action-${item.override_id}`}>{item.action_type}</p>
              <p className="text-xs text-slate-400" data-testid={`admin-strategy-intelligence-manual-override-reason-${item.override_id}`}>{item.reason}</p>
              <p className="text-xs text-slate-500" data-testid={`admin-strategy-intelligence-manual-override-time-${item.override_id}`}>{new Date(item.timestamp).toLocaleString()}</p>
            </article>
          ))}
          {manualOverrides.length === 0 && <p className="text-sm text-slate-400" data-testid="admin-strategy-intelligence-manual-overrides-empty">Manual override kaydı bulunmuyor.</p>}
        </div>
      </section>
    </section>
  );
};
