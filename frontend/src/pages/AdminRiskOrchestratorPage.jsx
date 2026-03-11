import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const policySeed = {
  reference_equity_usd: 10000,
  account_max_notional_pct: 60,
  symbol_max_notional_pct: 25,
  strategy_max_concurrent_positions: 3,
  strategy_cooldown_seconds: 60,
  max_order_frequency_per_min: 6,
  max_order_burst_per_10s: 3,
  daily_loss_limit_pct: 5,
  duplicate_suppression_window_seconds: 300,
};

export const AdminRiskOrchestratorPage = () => {
  const [policy, setPolicy] = useState(policySeed);
  const [status, setStatus] = useState(null);
  const [rejects, setRejects] = useState([]);
  const [supervisor, setSupervisor] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [policyRes, statusRes, rejectsRes] = await Promise.all([
        apiClient.get("/strategy-domain/admin/risk-orchestrator/policy"),
        apiClient.get("/strategy-domain/admin/risk-orchestrator/status"),
        apiClient.get("/strategy-domain/admin/risk-orchestrator/rejects?limit=25"),
      ]);
      setPolicy(policyRes.data || policySeed);
      setStatus(statusRes.data || null);
      setRejects(rejectsRes.data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk orchestrator verileri yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const updatePolicy = async () => {
    try {
      const payload = {
        reference_equity_usd: Number(policy.reference_equity_usd),
        account_max_notional_pct: Number(policy.account_max_notional_pct),
        symbol_max_notional_pct: Number(policy.symbol_max_notional_pct),
        strategy_max_concurrent_positions: Number(policy.strategy_max_concurrent_positions),
        strategy_cooldown_seconds: Number(policy.strategy_cooldown_seconds),
        max_order_frequency_per_min: Number(policy.max_order_frequency_per_min),
        max_order_burst_per_10s: Number(policy.max_order_burst_per_10s),
        daily_loss_limit_pct: Number(policy.daily_loss_limit_pct),
        duplicate_suppression_window_seconds: Number(policy.duplicate_suppression_window_seconds),
      };
      const { data } = await apiClient.put("/strategy-domain/admin/risk-orchestrator/policy", payload);
      setPolicy(data);
      toast.success("Risk orchestrator policy güncellendi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Policy güncellenemedi");
    }
  };

  const runSupervisor = async () => {
    try {
      const { data } = await apiClient.post("/strategy-domain/admin/risk-orchestrator/supervisor/run");
      setSupervisor(data);
      toast.success("In-trade supervisor çalıştırıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Supervisor çalıştırılamadı");
    }
  };

  const killSwitchLabel = useMemo(() => {
    if (!status) return "-";
    return status.kill_switch_active ? "ACTIVE" : "inactive";
  }, [status]);

  return (
    <section className="space-y-4" data-testid="admin-risk-orchestrator-page">
      <header className="border border-orange-700 bg-slate-900 p-4" data-testid="admin-risk-orchestrator-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-risk-orchestrator-title">
          Risk Orchestrator Control
        </h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-risk-orchestrator-description">
          Pre-trade gate + in-trade supervisor + cooldown/frequency/duplicate suppression kuralları.
        </p>
      </header>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]" data-testid="admin-risk-orchestrator-top-grid">
        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-policy-panel">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-policy-title">Policy Settings</p>
            <Button
              variant="outline"
              className="border-slate-600 text-slate-200"
              onClick={loadAll}
              data-testid="admin-risk-policy-refresh-button"
            >
              Refresh
            </Button>
          </div>
          {loading && (
            <p className="text-sm text-slate-400" data-testid="admin-risk-policy-loading">Yükleniyor...</p>
          )}
          <div className="grid gap-2 md:grid-cols-2" data-testid="admin-risk-policy-input-grid">
            <Input
              type="number"
              value={policy.reference_equity_usd}
              onChange={(e) => setPolicy((prev) => ({ ...prev, reference_equity_usd: e.target.value }))}
              placeholder="reference equity"
              data-testid="risk-policy-reference-equity-input"
            />
            <Input
              type="number"
              value={policy.account_max_notional_pct}
              onChange={(e) => setPolicy((prev) => ({ ...prev, account_max_notional_pct: e.target.value }))}
              placeholder="account max notional %"
              data-testid="risk-policy-account-max-notional-input"
            />
            <Input
              type="number"
              value={policy.symbol_max_notional_pct}
              onChange={(e) => setPolicy((prev) => ({ ...prev, symbol_max_notional_pct: e.target.value }))}
              placeholder="symbol max notional %"
              data-testid="risk-policy-symbol-max-notional-input"
            />
            <Input
              type="number"
              value={policy.strategy_max_concurrent_positions}
              onChange={(e) => setPolicy((prev) => ({ ...prev, strategy_max_concurrent_positions: e.target.value }))}
              placeholder="max concurrent positions"
              data-testid="risk-policy-max-concurrent-input"
            />
            <Input
              type="number"
              value={policy.strategy_cooldown_seconds}
              onChange={(e) => setPolicy((prev) => ({ ...prev, strategy_cooldown_seconds: e.target.value }))}
              placeholder="cooldown seconds"
              data-testid="risk-policy-cooldown-input"
            />
            <Input
              type="number"
              value={policy.max_order_frequency_per_min}
              onChange={(e) => setPolicy((prev) => ({ ...prev, max_order_frequency_per_min: e.target.value }))}
              placeholder="orders / min"
              data-testid="risk-policy-frequency-input"
            />
            <Input
              type="number"
              value={policy.max_order_burst_per_10s}
              onChange={(e) => setPolicy((prev) => ({ ...prev, max_order_burst_per_10s: e.target.value }))}
              placeholder="burst / 10s"
              data-testid="risk-policy-burst-input"
            />
            <Input
              type="number"
              value={policy.daily_loss_limit_pct}
              onChange={(e) => setPolicy((prev) => ({ ...prev, daily_loss_limit_pct: e.target.value }))}
              placeholder="daily loss %"
              data-testid="risk-policy-daily-loss-input"
            />
            <Input
              type="number"
              value={policy.duplicate_suppression_window_seconds}
              onChange={(e) => setPolicy((prev) => ({ ...prev, duplicate_suppression_window_seconds: e.target.value }))}
              placeholder="duplicate window s"
              data-testid="risk-policy-duplicate-window-input"
            />
          </div>
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={updatePolicy} data-testid="risk-policy-save-button">
            Save Policy
          </Button>
        </div>

        <div className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-status-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-status-title">Live Status</p>
          <div className="space-y-2" data-testid="admin-risk-status-metrics">
            <p className="text-sm" data-testid="admin-risk-status-open-intents">Open intents: {status?.open_intents ?? "-"}</p>
            <p className="text-sm" data-testid="admin-risk-status-kill-switch">Kill switch: {killSwitchLabel}</p>
            <p className="text-xs text-slate-400" data-testid="admin-risk-status-kill-switch-reasons">
              reasons: {status?.kill_switch_reasons?.length ? status.kill_switch_reasons.join(", ") : "-"}
            </p>
          </div>
          <div className="grid gap-2" data-testid="admin-risk-status-exposure-grid">
            <div className="border border-slate-700 p-2" data-testid="admin-risk-status-symbol-exposure">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-symbol-title">Symbol Exposure</p>
              {(status?.open_intents_by_symbol || []).map((row) => (
                <div key={row.key} className="flex items-center justify-between text-xs" data-testid={`admin-risk-symbol-row-${row.key}`}>
                  <span>{row.key}</span>
                  <span>{row.open_count} | ${row.notional.toFixed(2)}</span>
                </div>
              ))}
            </div>
            <div className="border border-slate-700 p-2" data-testid="admin-risk-status-strategy-exposure">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-strategy-title">Strategy Exposure</p>
              {(status?.open_intents_by_strategy || []).map((row) => (
                <div key={row.key} className="flex items-center justify-between text-xs" data-testid={`admin-risk-strategy-row-${row.key}`}>
                  <span>{row.key}</span>
                  <span>{row.open_count} | ${row.notional.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
          <Button
            variant="outline"
            className="border-emerald-400 text-emerald-200"
            onClick={runSupervisor}
            data-testid="admin-risk-supervisor-run-button"
          >
            Run In-Trade Supervisor
          </Button>
          {supervisor && (
            <div className="border border-slate-700 p-2" data-testid="admin-risk-supervisor-result">
              <p className="text-xs text-slate-400" data-testid="admin-risk-supervisor-timestamp">
                evaluated_at: {new Date(supervisor.evaluated_at).toLocaleString()}
              </p>
              {(supervisor.breaches || []).length === 0 && (
                <p className="text-xs text-emerald-300" data-testid="admin-risk-supervisor-empty">No breaches detected</p>
              )}
              {(supervisor.breaches || []).map((breach, index) => (
                <div key={`${breach.key}-${index}`} className="text-xs text-slate-200" data-testid={`admin-risk-supervisor-breach-${index}`}>
                  {breach.breach_type} · {breach.key} · {breach.open_count} | ${breach.notional.toFixed(2)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-risk-rejects-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-risk-rejects-title">Recent Risk Rejects</p>
        {rejects.length === 0 && (
          <p className="mt-2 text-sm text-slate-400" data-testid="admin-risk-rejects-empty">Henüz reject kaydı yok.</p>
        )}
        <div className="mt-3 space-y-2" data-testid="admin-risk-rejects-list">
          {rejects.map((row) => (
            <div key={row.id} className="border border-slate-700 p-2 text-xs" data-testid={`admin-risk-reject-row-${row.id}`}>
              <p data-testid={`admin-risk-reject-meta-${row.id}`}>{row.strategy_id || "-"} · {row.symbol || "-"}</p>
              <p className="text-slate-400" data-testid={`admin-risk-reject-reasons-${row.id}`}>
                {row.reason_codes?.join(", ") || "-"}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
