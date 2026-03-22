import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ActiveOverridesTable } from "@/components/strategy-intelligence/ActiveOverridesTable";
import { ActionConfirmationModal } from "@/components/strategy-intelligence/ActionConfirmationModal";
import { AuditSummaryPanel } from "@/components/strategy-intelligence/AuditSummaryPanel";
import { BeforeAfterImpactCard } from "@/components/strategy-intelligence/BeforeAfterImpactCard";
import { OverrideForm } from "@/components/strategy-intelligence/OverrideForm";
import { SimulationGuardPanel } from "@/components/strategy-intelligence/SimulationGuardPanel";
import { StrategyIntelligencePageContainer } from "@/components/strategy-intelligence/StrategyIntelligencePageContainer";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const DEFAULT_FORM = {
  user_id: "",
  symbol: "BTCUSDT",
  side: "buy",
  notional: 100,
  strategy_binding: "spot_pullback_v1",
  volatility_pct: 3,
  override_action_type: "",
  override_reason: "",
  override_target_id: "",
  override_ttl_minutes: "60",
  override_expires_at: "",
};

export const AdminStrategyIntelligencePage = () => {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canSimulate = ["super_admin", "admin", "ops", "viewer", "risk_manager", "operator"].includes(role);
  const canApplyOverride = ["super_admin", "admin"].includes(role);

  const [isLoading, setIsLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [manualOverrides, setManualOverrides] = useState([]);
  const [activeOverrides, setActiveOverrides] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [lastUpdatedAt, setLastUpdatedAt] = useState("");

  const [simulationForm, setSimulationForm] = useState(DEFAULT_FORM);
  const [simulationResult, setSimulationResult] = useState(null);
  const [simulationSymbolSource, setSimulationSymbolSource] = useState("crypto");
  const [simulationSymbolMode, setSimulationSymbolMode] = useState("all_market_symbols");
  const [simulationSelectedSymbols, setSimulationSelectedSymbols] = useState(["BTCUSDT"]);

  const [isRunningSimulation, setIsRunningSimulation] = useState(false);
  const [isApplyingOverride, setIsApplyingOverride] = useState(false);
  const [revokingId, setRevokingId] = useState("");

  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if ((simulationSelectedSymbols || []).length === 0) return;
    setSimulationForm((prev) => ({ ...prev, symbol: simulationSelectedSymbols[0] }));
  }, [simulationSelectedSymbols]);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const [dashRes, overridesRes, activeRes] = await Promise.all([
        apiClient.get("/admin/strategy-intelligence"),
        apiClient.get("/admin/manual-overrides"),
        apiClient.get("/admin/active-overrides"),
      ]);
      setDashboard(dashRes.data || null);
      setManualOverrides(overridesRes.data || []);
      setActiveOverrides(activeRes.data || []);
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
      toast.error("Simulation için user_id zorunlu");
      return;
    }
    setIsRunningSimulation(true);
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
        apply_override: false,
      };
      const { data } = await apiClient.post("/admin/risk-simulation", payload);
      setSimulationResult(data || null);
      toast.success("Simulation tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simulation başarısız");
    } finally {
      setIsRunningSimulation(false);
    }
  };

  const requestApplyOverride = () => {
    if (!simulationResult?.simulation_id) {
      toast.error("Apply öncesi simulation zorunlu");
      return;
    }
    if (String(simulationForm.override_reason || "").trim().length < 12) {
      toast.error("Reason minimum 12 karakter olmalı");
      return;
    }
    if (!simulationForm.override_expires_at && Number(simulationForm.override_ttl_minutes || 0) <= 0) {
      toast.error("Expiry zorunlu (expires_at veya ttl_minutes)");
      return;
    }
    setConfirmOpen(true);
  };

  const confirmApplyOverride = async () => {
    setIsApplyingOverride(true);
    try {
      const payload = {
        scope: "strategy_intelligence",
        target_type: "user",
        target_id: simulationForm.override_target_id || simulationForm.user_id,
        action_type: simulationForm.override_action_type,
        reason: simulationForm.override_reason,
        simulation_id: simulationResult?.simulation_id,
        expires_at: simulationForm.override_expires_at ? new Date(simulationForm.override_expires_at).toISOString() : null,
        ttl_minutes: simulationForm.override_expires_at ? null : Number(simulationForm.override_ttl_minutes || 0),
        confirmation_id: `confirm_${Date.now()}`,
        previous_state: simulationResult?.before_state || {},
        next_state: simulationResult?.after_state || {},
        impact_preview: {
          projected_risk_score: simulationResult?.projected_risk_score,
          projected_gate_decision: simulationResult?.projected_gate_decision,
          risk_delta: simulationResult?.risk_delta,
          decision_delta: simulationResult?.decision_delta,
          projected_pnl: simulationResult?.projected_pnl,
          projected_drawdown: simulationResult?.projected_drawdown,
        },
        payload: {
          source: "strategy_intelligence_decision_engine",
          user_id: simulationForm.user_id,
          symbol: simulationForm.symbol,
        },
      };
      await apiClient.post("/admin/manual-overrides", payload);
      toast.success("Override uygulandı ve audit log’a yazıldı");
      setConfirmOpen(false);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override apply başarısız");
    } finally {
      setIsApplyingOverride(false);
    }
  };

  const revokeOverride = async (row) => {
    if (!canApplyOverride) {
      toast.error("Bu rol revoke yetkisine sahip değil");
      return;
    }
    const reason = window.prompt("Revoke reason (min 12 karakter):", "manual_revoke_for_safety");
    if (!reason || reason.trim().length < 12) {
      toast.error("Revoke reason minimum 12 karakter olmalı");
      return;
    }

    setRevokingId(row.override_id);
    try {
      await apiClient.post(`/admin/manual-overrides/${row.override_id}/revoke`, { reason });
      toast.success("Override revoke edildi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Override revoke başarısız");
    } finally {
      setRevokingId("");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={10} testId="strategy-intelligence-loading-skeleton" />;
  }

  if (!dashboard) {
    return (
      <section className="space-y-4" data-testid="strategy-intelligence-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="strategy-intelligence-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="strategy-intelligence-broken-title">Strategy intelligence verisi alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="strategy-intelligence-broken-message">{loadError || "Servis geçici olarak yanıt vermiyor."}</p>
        </div>
      </section>
    );
  }

  return (
    <StrategyIntelligencePageContainer
      role={role}
      lastUpdatedAt={lastUpdatedAt}
      dashboard={dashboard}
      loadError={loadError}
      onRefresh={load}
    >
      <div className="col-span-12 border border-slate-800 bg-slate-900 p-3" data-testid="strategy-intelligence-role-visibility-panel">
        <p className="text-xs text-slate-300" data-testid="strategy-intelligence-role-visibility-text">
          {canApplyOverride
            ? "admin/super_admin: simulate + confirm + apply + revoke"
            : "ops/viewer: read-only + simulation; kritik aksiyonlar kapalı"}
        </p>
      </div>

      <div className="col-span-12 lg:col-span-7 space-y-4" data-testid="strategy-intelligence-left-column">
        <SimulationGuardPanel
          form={simulationForm}
          setForm={setSimulationForm}
          canSimulate={canSimulate}
          isRunning={isRunningSimulation}
          onRun={submitSimulation}
          symbolSource={simulationSymbolSource}
          onSymbolSource={setSimulationSymbolSource}
          symbolMode={simulationSymbolMode}
          onSymbolMode={setSimulationSymbolMode}
          selectedSymbols={simulationSelectedSymbols}
          onSelectedSymbols={setSimulationSelectedSymbols}
        />
        <BeforeAfterImpactCard simulationResult={simulationResult} />
      </div>

      <div className="col-span-12 lg:col-span-5 space-y-4" data-testid="strategy-intelligence-right-column">
        <OverrideForm
          form={simulationForm}
          setForm={setSimulationForm}
          canApply={canApplyOverride}
          simulationReady={Boolean(simulationResult?.simulation_id)}
          onRequestApply={requestApplyOverride}
          isSubmitting={isApplyingOverride}
        />
        <AuditSummaryPanel manualOverrides={manualOverrides} activeOverrides={activeOverrides} />
      </div>

      <div className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-conflicts-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-conflicts-title">Strategy Conflicts</p>
        <div className="mt-2 space-y-2" data-testid="strategy-intelligence-conflicts-list">
          {conflicts.slice(0, 8).map((item, index) => (
            <article key={`${item.winning_strategy}-${index}`} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-conflict-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-conflict-winner-${index}`}>winner: {item.winning_strategy || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-conflict-loser-${index}`}>loser: {item.losing_strategy || "-"}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-conflict-reason-${index}`}>reason: {item.resolution_reason}</p>
            </article>
          ))}
          {conflicts.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-intelligence-conflicts-empty">Aktif strategy conflict bulunmuyor.</p>}
        </div>
      </div>

      <div className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-hedge-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-hedge-title">Hedge Suggestions</p>
        <div className="mt-2 space-y-2" data-testid="strategy-intelligence-hedge-list">
          {hedgeSuggestions.slice(0, 8).map((item, index) => (
            <article key={`${item.hedge_symbol || "none"}-${index}`} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-hedge-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-hedge-symbol-${index}`}>symbol: {item.hedge_symbol || "none"}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-hedge-size-${index}`}>size: {item.hedge_size}</p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-hedge-direction-${index}`}>direction: {item.hedge_direction || "-"}</p>
            </article>
          ))}
          {hedgeSuggestions.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-intelligence-hedge-empty">Aktif hedge önerisi bulunmuyor.</p>}
        </div>
      </div>

      <div className="col-span-12" data-testid="strategy-intelligence-active-overrides-wrapper">
        <ActiveOverridesTable
          rows={activeOverrides}
          canRevoke={canApplyOverride}
          revokingId={revokingId}
          onRevoke={revokeOverride}
        />
      </div>

      <ActionConfirmationModal
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        onConfirm={confirmApplyOverride}
        isSubmitting={isApplyingOverride}
        title="Override Apply Confirmation"
        description="Apply öncesi simulation impact preview zorunlu doğrulama"
        details={[
          { label: "target", value: simulationForm.override_target_id || simulationForm.user_id || "-" },
          { label: "reason", value: simulationForm.override_reason || "-" },
          { label: "expires", value: simulationForm.override_expires_at || `${simulationForm.override_ttl_minutes || 0}m` },
          { label: "risk_delta", value: simulationResult?.risk_delta ?? "-" },
          { label: "decision_delta", value: simulationResult?.decision_delta ?? "-" },
        ]}
      />
    </StrategyIntelligencePageContainer>
  );
};
