import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { MetricCard } from "@/components/MetricCard";
import { ResponsiveMiniLineChart } from "@/components/ResponsiveMiniLineChart";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const computeRiskPolicyHealth = (policy) => {
  if (!policy) {
    return { score: 0, level: "UNKNOWN", message: "Risk policy bulunamadı" };
  }

  let score = 0;
  const positionSize = Number(policy.position_size_pct || 0);
  const dailyLoss = Number(policy.daily_loss_cutoff_pct || 0);
  const maxOpen = Number(policy.max_open_positions || 0);
  const maxLeverage = Number(policy.max_leverage || 0);
  const spreadLimit = Number(policy.spread_limit_bps || 0);
  const slippageLimit = Number(policy.slippage_limit_bps || 0);
  const minLiquidity = Number(policy.min_liquidity_usdt || 0);

  score += positionSize <= 1.5 ? 25 : positionSize <= 2.5 ? 18 : positionSize <= 4 ? 10 : 4;
  score += dailyLoss <= 3 ? 25 : dailyLoss <= 5 ? 18 : dailyLoss <= 8 ? 10 : 4;
  score += maxOpen <= 2 ? 20 : maxOpen <= 4 ? 14 : maxOpen <= 6 ? 8 : 4;
  score += maxLeverage <= 2 ? 15 : maxLeverage <= 3 ? 10 : maxLeverage <= 5 ? 6 : 2;
  score += spreadLimit <= 30 && slippageLimit <= 40 && minLiquidity >= 100000 ? 15 : 8;

  const normalized = Math.max(0, Math.min(100, score));
  if (normalized >= 80) {
    return { score: normalized, level: "SAFE", message: "Koruyucu ve dengeli" };
  }
  if (normalized >= 60) {
    return { score: normalized, level: "BALANCED", message: "Dengeli fakat optimize edilebilir" };
  }
  return { score: normalized, level: "AGGRESSIVE", message: "Risk seviyesi yüksek" };
};

export const UserDashboardPage = () => {
  const [dashboard, setDashboard] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [riskPolicies, setRiskPolicies] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [wizardForm, setWizardForm] = useState(null);
  const [isSavingWizard, setIsSavingWizard] = useState(false);
  const [wizardDismissed, setWizardDismissed] = useState(false);

  const load = async () => {
    setIsLoading(true);
    try {
      const [dashboardRes, portfolioRes, performanceRes, riskPoliciesRes] = await Promise.all([
        apiClient.get("/user/dashboard"),
        apiClient.get("/user/portfolio"),
        apiClient.get("/user/performance"),
        apiClient.get("/risk-policies"),
      ]);
      setDashboard(dashboardRes.data);
      setPortfolio(portfolioRes.data);
      setPerformance(performanceRes.data);
      setRiskPolicies(riskPoliciesRes.data || []);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const defaultPolicy = useMemo(() => {
    const auto = (riskPolicies || []).find((item) => String(item.name || "").toLowerCase().includes("starter safe (auto)"));
    return auto || (riskPolicies || [])[0] || null;
  }, [riskPolicies]);

  const riskHealth = useMemo(() => computeRiskPolicyHealth(defaultPolicy), [defaultPolicy]);

  const wizardStorageKey = useMemo(() => (defaultPolicy ? `risk-policy-onboarding-dismissed-${defaultPolicy.id}` : ""), [defaultPolicy]);

  useEffect(() => {
    if (!defaultPolicy) {
      setWizardForm(null);
      return;
    }
    setWizardForm({
      name: defaultPolicy.name,
      position_size_pct: defaultPolicy.position_size_pct,
      daily_loss_cutoff_pct: defaultPolicy.daily_loss_cutoff_pct,
      max_open_positions: defaultPolicy.max_open_positions,
      max_leverage: defaultPolicy.max_leverage,
      risk_reward_ratio: defaultPolicy.risk_reward_ratio,
    });
  }, [defaultPolicy?.id]);

  useEffect(() => {
    if (!wizardStorageKey) {
      setWizardDismissed(false);
      return;
    }
    setWizardDismissed(localStorage.getItem(wizardStorageKey) === "true");
  }, [wizardStorageKey]);

  const saveOnboardingPolicy = async () => {
    if (!defaultPolicy || !wizardForm) {
      return;
    }
    setIsSavingWizard(true);
    try {
      await apiClient.put(`/risk-policies/${defaultPolicy.id}`, {
        name: String(wizardForm.name || defaultPolicy.name).trim() || defaultPolicy.name,
        position_size_pct: Number(wizardForm.position_size_pct || defaultPolicy.position_size_pct),
        atr_stop_multiplier: Number(defaultPolicy.atr_stop_multiplier || 1.5),
        risk_reward_ratio: Number(wizardForm.risk_reward_ratio || defaultPolicy.risk_reward_ratio),
        daily_loss_cutoff_pct: Number(wizardForm.daily_loss_cutoff_pct || defaultPolicy.daily_loss_cutoff_pct),
        max_open_positions: Number(wizardForm.max_open_positions || defaultPolicy.max_open_positions),
        max_leverage: Number(wizardForm.max_leverage || defaultPolicy.max_leverage),
        spread_limit_bps: Number(defaultPolicy.spread_limit_bps || 30),
        slippage_limit_bps: Number(defaultPolicy.slippage_limit_bps || 40),
        min_liquidity_usdt: Number(defaultPolicy.min_liquidity_usdt || 100000),
      });
      toast.success("Onboarding risk policy güncellendi");
      if (wizardStorageKey) {
        localStorage.setItem(wizardStorageKey, "true");
      }
      setWizardDismissed(true);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk policy güncellenemedi");
    } finally {
      setIsSavingWizard(false);
    }
  };

  const dismissWizard = () => {
    if (wizardStorageKey) {
      localStorage.setItem(wizardStorageKey, "true");
    }
    setWizardDismissed(true);
  };

  const chartData = useMemo(
    () => [
      { metric: "Capital", value: dashboard?.current_capital ?? 0 },
      { metric: "Balance", value: dashboard?.available_balance ?? 0 },
      { metric: "PnL", value: portfolio?.closed_pnl ?? 0 },
      { metric: "Win", value: performance?.win_rate ?? 0 },
    ],
    [dashboard, performance, portfolio],
  );

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-dashboard-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-dashboard-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-dashboard-title">User Dashboard</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-dashboard-description">
          Responsive ve erişilebilir özet görünümü. Assisted kuyruk, portföy ve performans tek ekranda.
        </p>
      </header>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-dashboard-metrics-grid" aria-label="Dashboard metrikleri">
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Bot" value={dashboard?.bot_count ?? "-"} testId="user-dashboard-metric-bot-count" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Running" value={dashboard?.running_bot_count ?? "-"} testId="user-dashboard-metric-running-bot-count" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Risk Policy" value={dashboard?.risk_policy_count ?? "-"} testId="user-dashboard-metric-risk-policy-count" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Open Positions" value={dashboard?.open_positions_count ?? "-"} tone="orange" testId="user-dashboard-metric-open-positions" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Pending" value={dashboard?.pending_signals_count ?? "-"} tone="orange" testId="user-dashboard-metric-pending-signals" /></div>
        <div className="col-span-6 md:col-span-4 xl:col-span-2"><MetricCard label="Heartbeat" value={dashboard?.heartbeat ?? "-"} tone="blue" testId="user-dashboard-metric-heartbeat" /></div>
      </div>

      <div className="col-span-12 lg:col-span-8" data-testid="user-dashboard-chart-col">
        <ResponsiveMiniLineChart
          data={chartData}
          xKey="metric"
          yKey="value"
          title="Dashboard Snapshot"
          testId="user-dashboard-responsive-chart"
        />
      </div>

      <div className="col-span-12 lg:col-span-4 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-dashboard-summary-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-dashboard-summary-title">Quick Summary</p>
        <p className="mt-2 text-sm" data-testid="user-dashboard-current-capital">Current Capital: {dashboard?.current_capital ?? "-"}</p>
        <p className="mt-1 text-sm" data-testid="user-dashboard-available-balance">Available Balance: {dashboard?.available_balance ?? "-"}</p>
        <p className="mt-1 text-sm" data-testid="user-dashboard-closed-pnl">Closed PnL: {portfolio?.closed_pnl ?? "-"}</p>
        <p className="mt-1 text-sm" data-testid="user-dashboard-win-rate">Win Rate: {performance?.win_rate ?? "-"}</p>
        <div className="mt-3 rounded border border-cyan-900/40 bg-cyan-950/20 p-3" data-testid="user-dashboard-risk-policy-health-card">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="user-dashboard-risk-policy-health-title">Risk Policy Health Score</p>
          <p className="mt-1 text-2xl font-black" data-testid="user-dashboard-risk-policy-health-score">{riskHealth.score}</p>
          <p className="text-xs text-cyan-100" data-testid="user-dashboard-risk-policy-health-level">level: {riskHealth.level}</p>
          <p className="text-xs text-cyan-100" data-testid="user-dashboard-risk-policy-health-message">{riskHealth.message}</p>
        </div>
      </div>

      {defaultPolicy && wizardForm && !wizardDismissed && (
        <section className="col-span-12 rounded border border-amber-500/40 bg-amber-950/10 p-4" data-testid="user-dashboard-risk-onboarding-wizard">
          <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="user-dashboard-risk-onboarding-title">Onboarding Risk Wizard</p>
          <p className="mt-1 text-sm text-amber-100" data-testid="user-dashboard-risk-onboarding-description">Başlangıç policy değerlerini hızlıca özelleştir, sonra istersen Risk Policy sayfasından detaylandır.</p>
          <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="user-dashboard-risk-onboarding-grid">
            <label className="space-y-1" data-testid="user-dashboard-risk-onboarding-name-field">
              <span className="text-xs text-amber-200">Policy Name</span>
              <Input value={wizardForm.name} onChange={(event) => setWizardForm((prev) => ({ ...prev, name: event.target.value }))} data-testid="user-dashboard-risk-onboarding-name-input" />
            </label>
            <label className="space-y-1" data-testid="user-dashboard-risk-onboarding-position-field">
              <span className="text-xs text-amber-200">Position Size %</span>
              <Input type="number" step="0.1" value={wizardForm.position_size_pct} onChange={(event) => setWizardForm((prev) => ({ ...prev, position_size_pct: event.target.value }))} data-testid="user-dashboard-risk-onboarding-position-input" />
            </label>
            <label className="space-y-1" data-testid="user-dashboard-risk-onboarding-daily-loss-field">
              <span className="text-xs text-amber-200">Daily Loss %</span>
              <Input type="number" step="0.1" value={wizardForm.daily_loss_cutoff_pct} onChange={(event) => setWizardForm((prev) => ({ ...prev, daily_loss_cutoff_pct: event.target.value }))} data-testid="user-dashboard-risk-onboarding-daily-loss-input" />
            </label>
            <label className="space-y-1" data-testid="user-dashboard-risk-onboarding-max-open-field">
              <span className="text-xs text-amber-200">Max Open</span>
              <Input type="number" value={wizardForm.max_open_positions} onChange={(event) => setWizardForm((prev) => ({ ...prev, max_open_positions: event.target.value }))} data-testid="user-dashboard-risk-onboarding-max-open-input" />
            </label>
            <label className="space-y-1" data-testid="user-dashboard-risk-onboarding-max-leverage-field">
              <span className="text-xs text-amber-200">Max Leverage</span>
              <Input type="number" value={wizardForm.max_leverage} onChange={(event) => setWizardForm((prev) => ({ ...prev, max_leverage: event.target.value }))} data-testid="user-dashboard-risk-onboarding-max-leverage-input" />
            </label>
            <label className="space-y-1" data-testid="user-dashboard-risk-onboarding-rr-field">
              <span className="text-xs text-amber-200">Risk Reward Ratio</span>
              <Input type="number" step="0.1" value={wizardForm.risk_reward_ratio} onChange={(event) => setWizardForm((prev) => ({ ...prev, risk_reward_ratio: event.target.value }))} data-testid="user-dashboard-risk-onboarding-rr-input" />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="user-dashboard-risk-onboarding-actions">
            <Button onClick={saveOnboardingPolicy} disabled={isSavingWizard} data-testid="user-dashboard-risk-onboarding-save-button">
              {isSavingWizard ? "Kaydediliyor..." : "Kaydet ve Tamamla"}
            </Button>
            <Button variant="outline" onClick={dismissWizard} data-testid="user-dashboard-risk-onboarding-dismiss-button">Sonra Yap</Button>
          </div>
        </section>
      )}
    </section>
  );
};